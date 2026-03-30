"""Deterministic research agent using competitor pages and arXiv feeds."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pm_agent.adapters.research import (
    ArxivEntry,
    ArxivResearchClient,
    CompetitorResearchClient,
    PageSummary,
    ResearchAdapterError,
)
from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    AgentWarning,
    CompetitorSnapshot,
    Evidence,
    Finding,
    FindingKind,
    PaperSnapshot,
    ResearchAgentOutput,
    Severity,
    SourceRef,
    SourceType,
)


def _priority_keywords(texts: list[str]) -> set[str]:
    keywords: set[str] = set()
    for text in texts:
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if len(token) >= 4:
                keywords.add(token)
    return keywords


def _overlap(keywords: set[str], text: str) -> set[str]:
    haystack = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 4}
    return keywords & haystack


class ResearchAgent(BaseAgent):
    name = AgentName.RESEARCH

    def __init__(
        self,
        *,
        competitor_client: CompetitorResearchClient | None = None,
        arxiv_client: ArxivResearchClient | None = None,
    ) -> None:
        self._competitor_client = competitor_client or CompetitorResearchClient()
        self._arxiv_client = arxiv_client or ArxivResearchClient()

    def run(self, context: AgentExecutionContext) -> ResearchAgentOutput:
        started_at = datetime.now(UTC)
        warnings: list[AgentWarning] = []
        findings: list[Finding] = []
        competitors: list[CompetitorSnapshot] = []
        papers: list[PaperSnapshot] = []
        status = AgentStatus.SUCCESS

        strategy_texts = [context.product.vision, *context.product.strategic_priorities]
        strategy_keywords = _priority_keywords(strategy_texts)

        for url in context.config.research.competitors:
            try:
                summary = self._competitor_client.fetch_page_summary(url)
                competitors.append(self._to_competitor_snapshot(summary))
                findings.extend(self._competitor_findings(context, summary, strategy_keywords))
            except ResearchAdapterError as exc:
                status = AgentStatus.PARTIAL
                warnings.append(AgentWarning(code="competitor_fetch_failed", message=str(exc)))

        for category in context.config.research.arxiv_categories:
            try:
                entries = self._arxiv_client.fetch_category_entries(category)
                for entry in entries:
                    papers.append(self._to_paper_snapshot(entry, strategy_keywords))
                findings.extend(self._paper_findings(context, entries, strategy_keywords))
            except ResearchAdapterError as exc:
                status = AgentStatus.PARTIAL
                warnings.append(AgentWarning(code="arxiv_fetch_failed", message=str(exc)))

        return ResearchAgentOutput(
            agent=AgentName.RESEARCH,
            status=status,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=warnings,
            findings=findings,
            competitors=competitors,
            papers=papers,
        )

    def _to_competitor_snapshot(self, summary: PageSummary) -> CompetitorSnapshot:
        notes = []
        if summary.description:
            notes.append(summary.description[:200])
        return CompetitorSnapshot(
            url=summary.url,
            product_summary=summary.description or summary.text_excerpt[:220],
            notable_capabilities=_capability_hints(summary.description + " " + summary.text_excerpt),
            comparison_notes=notes,
        )

    def _to_paper_snapshot(
        self,
        entry: ArxivEntry,
        strategy_keywords: set[str],
    ) -> PaperSnapshot:
        overlap = _overlap(strategy_keywords, f"{entry.title} {entry.summary}")
        relevance_reason = (
            f"Overlaps product priorities via: {', '.join(sorted(overlap))}"
            if overlap
            else f"Falls under tracked category {entry.category}"
        )
        implication = (
            "Potential future product opportunity."
            if overlap
            else "Monitor for later synthesis if reinforced by other sources."
        )
        return PaperSnapshot(
            arxiv_id=entry.arxiv_id,
            title=entry.title,
            published_at=entry.published_at,
            relevance_reason=relevance_reason,
            implication=implication,
        )

    def _competitor_findings(
        self,
        context: AgentExecutionContext,
        summary: PageSummary,
        strategy_keywords: set[str],
    ) -> list[Finding]:
        overlap = _overlap(strategy_keywords, f"{summary.title} {summary.description} {summary.text_excerpt}")
        if not overlap:
            return []
        slug = _slug(summary.url)
        return [
            Finding(
                finding_id=f"{context.run.run_id}-competitor-{slug}",
                agent=AgentName.RESEARCH,
                kind=FindingKind.STRATEGIC_OPPORTUNITY,
                title=f"Competitor messaging overlaps current priorities: {summary.title}",
                problem_statement=(
                    "A tracked competitor emphasizes themes that overlap with the current product strategy."
                ),
                user_impact=(
                    "Users may see more concrete value framing elsewhere if strategic themes are not expressed clearly."
                ),
                affected_surfaces=["strategy", "positioning"],
                affected_personas=context.product.target_users,
                severity=Severity.LOW,
                raw_confidence=0.62,
                novelty_key=f"competitor-overlap-{slug}",
                dedup_keys=[f"competitor-overlap-{slug}"],
                tags=["research", "competitor", *sorted(overlap)],
                evidence=[
                    Evidence(
                        summary=f"Competitor page overlaps priorities via: {', '.join(sorted(overlap))}.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.COMPETITOR_PAGE,
                                source_id=slug,
                                title=summary.title,
                                locator=summary.url,
                                excerpt=summary.description or summary.text_excerpt[:200],
                            )
                        ],
                    )
                ],
                proposed_direction="Review whether these strategic themes should be made more explicit in product positioning or UX.",
            )
        ]

    def _paper_findings(
        self,
        context: AgentExecutionContext,
        entries: list[ArxivEntry],
        strategy_keywords: set[str],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for entry in entries:
            overlap = _overlap(strategy_keywords, f"{entry.title} {entry.summary}")
            if not overlap:
                continue
            findings.append(
                Finding(
                    finding_id=f"{context.run.run_id}-paper-{entry.arxiv_id}",
                    agent=AgentName.RESEARCH,
                    kind=FindingKind.STRATEGIC_OPPORTUNITY,
                    title=f"Relevant recent paper for current priorities: {entry.title}",
                    problem_statement="A tracked recent paper aligns with current product priorities.",
                    user_impact="Relevant product or UX approaches may be missed if recent research is ignored.",
                    affected_surfaces=["research"],
                    affected_personas=context.product.target_users,
                    severity=Severity.LOW,
                    raw_confidence=0.55,
                    novelty_key=f"paper-overlap-{entry.arxiv_id}",
                    dedup_keys=[f"paper-overlap-{entry.arxiv_id}"],
                    tags=["research", "arxiv", *sorted(overlap)],
                    evidence=[
                        Evidence(
                            summary=f"Paper aligns via: {', '.join(sorted(overlap))}.",
                            source_refs=[
                                SourceRef(
                                    source_type=SourceType.ARXIV_PAPER,
                                    source_id=entry.arxiv_id,
                                    title=entry.title,
                                    locator=entry.link,
                                    excerpt=entry.summary[:220],
                                )
                            ],
                        )
                    ],
                    proposed_direction="Review whether the paper suggests a roadmap or UX experiment worth tracking.",
                )
            )
        return findings


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:48]


def _capability_hints(text: str) -> list[str]:
    hints: list[str] = []
    lowered = text.lower()
    for keyword in (
        "search",
        "assistant",
        "agent",
        "workflow",
        "automation",
        "research",
        "knowledge",
        "writing",
    ):
        if keyword in lowered:
            hints.append(keyword)
    return hints[:6]
