"""Local codebase agent using manifest-based repository retrieval."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pm_agent.adapters.anthropic import AnthropicAdapterError, AnthropicMessagesClient
from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.agents.codebase_enhancer import (
    AnthropicCodebaseEnhancer,
    CodebaseFindingReview,
    CodebaseReviewResponse,
)
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    AgentWarning,
    CodebaseAgentOutput,
    ComponentSummary,
    Evidence,
    Finding,
    FindingKind,
    Severity,
    SourceRef,
    SourceType,
)
from pm_agent.repo.manifest import RepoManifest, build_repo_manifest
from pm_agent.repo.retrieval import hotspot_files, representative_file_context
from pm_agent.repo.summarizer import summarize_components, summarize_repo


def _build_findings(context: AgentExecutionContext, manifest: RepoManifest) -> list[Finding]:
    findings: list[Finding] = []
    caps = context.capabilities
    timestamp = context.run.run_id

    if caps is not None and not caps.product_file_exists:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-product",
                agent=AgentName.CODEBASE,
                kind=FindingKind.PRODUCT_GAP,
                title="Repo is missing PRODUCT.md strategy context",
                problem_statement="The repository does not include the configured PRODUCT.md file.",
                user_impact="The PM agent cannot align prioritization to product strategy.",
                severity=Severity.MEDIUM,
                raw_confidence=0.95,
                novelty_key="missing-product-context",
                dedup_keys=["missing-product-context"],
                tags=["strategy", "config"],
                evidence=[
                    Evidence(
                        summary="Configured product context file was not found in the repo.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_DOC,
                                source_id="product-file",
                                repo_path=str(context.config.repo.product_file).replace("\\", "/"),
                            )
                        ],
                    )
                ],
                proposed_direction="Add and maintain PRODUCT.md so synthesis can reason against strategy.",
            )
        )

    if context.config.runtime.mode.value == "docker_compose" and caps is not None and not caps.docker_compose_ready:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-compose",
                agent=AgentName.CODEBASE,
                kind=FindingKind.RELIABILITY,
                title="Configured Docker Compose runtime is missing",
                problem_statement="The PM agent is configured to use Docker Compose, but the compose file is absent.",
                user_impact="Dogfooding and repeatable local validation will fail.",
                severity=Severity.HIGH,
                raw_confidence=0.96,
                novelty_key="missing-docker-compose",
                dedup_keys=["missing-docker-compose"],
                tags=["runtime", "dogfooding"],
                evidence=[
                    Evidence(
                        summary="Configured compose file was not found in the repo.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_FILE,
                                source_id="compose-file",
                                repo_path=str(context.config.runtime.compose_file).replace("\\", "/")
                                if context.config.runtime.compose_file
                                else None,
                            )
                        ],
                    )
                ],
                proposed_direction="Either add the compose file or switch runtime mode in pm-config.yml.",
            )
        )

    if not manifest.test_files:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-tests",
                agent=AgentName.CODEBASE,
                kind=FindingKind.TECHNICAL_RISK,
                title="Repo has no detectable test coverage",
                problem_statement="No files matching common test naming conventions were found.",
                user_impact="The PM agent cannot reliably distinguish regressions from intended changes.",
                severity=Severity.MEDIUM,
                raw_confidence=0.75,
                novelty_key="missing-tests",
                dedup_keys=["missing-tests"],
                tags=["testing"],
                evidence=[
                    Evidence(
                        summary="Repository manifest found no test, spec, or e2e files.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_FILE,
                                source_id="repo-manifest",
                                locator=context.repo_root.as_posix(),
                            )
                        ],
                    )
                ],
                proposed_direction="Add at least a smoke test layer before enabling autonomous lifecycle actions.",
            )
        )

    if manifest.source_files and not manifest.doc_files:
        findings.append(
            Finding(
                finding_id=f"{timestamp}-missing-docs",
                agent=AgentName.CODEBASE,
                kind=FindingKind.PRODUCT_GAP,
                title="Repo has little or no supporting documentation",
                problem_statement="The repository has source files but no markdown documentation beyond config-level metadata.",
                user_impact="Agents and maintainers have less context for prioritization, onboarding, and issue triage.",
                severity=Severity.LOW,
                raw_confidence=0.7,
                novelty_key="missing-repo-docs",
                dedup_keys=["missing-repo-docs"],
                tags=["docs"],
                evidence=[
                    Evidence(
                        summary="Repository manifest found source files but no markdown docs.",
                        source_refs=[
                            SourceRef(
                                source_type=SourceType.REPO_DOC,
                                source_id="repo-manifest",
                                locator=context.repo_root.as_posix(),
                            )
                        ],
                    )
                ],
                proposed_direction="Add lightweight technical docs or feature notes for primary components.",
            )
        )

    return findings


FINDING_KIND_MAP = {
    "product_gap": FindingKind.PRODUCT_GAP,
    "technical_risk": FindingKind.TECHNICAL_RISK,
    "reliability": FindingKind.RELIABILITY,
    "performance": FindingKind.PERFORMANCE,
    "content": FindingKind.CONTENT,
    "strategic_opportunity": FindingKind.STRATEGIC_OPPORTUNITY,
}

SEVERITY_MAP = {
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "codebase-review"


def _review_findings(
    context: AgentExecutionContext,
    reviews: list[CodebaseFindingReview],
) -> list[Finding]:
    findings: list[Finding] = []
    for review in reviews:
        slug = _slug(review.title)
        source_refs = [
            SourceRef(
                source_type=SourceType.REPO_FILE,
                source_id=path,
                repo_path=path,
            )
            for path in review.relevant_paths
        ] or [
            SourceRef(
                source_type=SourceType.REPO_FILE,
                source_id="repo-review",
                locator=context.repo_root.as_posix(),
            )
        ]
        findings.append(
            Finding(
                finding_id=f"{context.run.run_id}-codebase-{slug}",
                agent=AgentName.CODEBASE,
                kind=FINDING_KIND_MAP.get(review.kind, FindingKind.TECHNICAL_RISK),
                title=review.title,
                problem_statement=review.problem_statement,
                user_impact=review.user_impact,
                affected_surfaces=review.affected_surfaces,
                affected_personas=context.product.target_users,
                severity=SEVERITY_MAP.get(review.severity, Severity.LOW),
                raw_confidence=max(0.0, min(1.0, review.confidence)),
                novelty_key=f"codebase-review-{slug}",
                dedup_keys=[f"codebase-review-{slug}"],
                tags=["codebase", *review.tags],
                evidence=[
                    Evidence(
                        summary=review.summary,
                        source_refs=source_refs,
                    )
                ],
                proposed_direction=review.proposed_direction,
            )
        )
    return findings


class CodebaseAgent(BaseAgent):
    name = AgentName.CODEBASE

    def __init__(
        self,
        *,
        enhancer: AnthropicCodebaseEnhancer | None = None,
    ) -> None:
        self._enhancer = enhancer

    def run(self, context: AgentExecutionContext) -> CodebaseAgentOutput:
        started_at = datetime.now(UTC)
        warnings: list[AgentWarning] = []
        manifest = build_repo_manifest(
            context.repo_root,
            project_roots=context.config.repo.project_roots,
            ignore_paths=context.config.repo.ignore_paths,
        )
        components = summarize_components(manifest)
        findings = _build_findings(context, manifest)
        hotspots = hotspot_files(manifest)
        repo_summary = summarize_repo(manifest, components=components)
        enhancer = self._enhancer_for_context(context, warnings)
        if enhancer is not None:
            review = self._review_codebase(
                context,
                manifest,
                repo_summary,
                components,
                hotspots,
                enhancer,
                warnings,
            )
            if review is not None:
                repo_summary = review.repo_summary or repo_summary
                if review.components:
                    components = [
                        ComponentSummary(
                            name=component.name,
                            paths=component.paths,
                            responsibilities=component.responsibilities,
                            risks=component.risks,
                        )
                        for component in review.components
                    ]
                findings.extend(_review_findings(context, review.findings))
        return CodebaseAgentOutput(
            agent=AgentName.CODEBASE,
            status=AgentStatus.SUCCESS,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=warnings,
            findings=findings,
            repo_summary=repo_summary,
            components=components,
            changed_files=context.changed_files,
            hotspot_files=hotspots,
        )

    def _enhancer_for_context(
        self,
        context: AgentExecutionContext,
        warnings: list[AgentWarning],
    ) -> AnthropicCodebaseEnhancer | None:
        if self._enhancer is not None:
            return self._enhancer
        if (
            not context.config.anthropic.enabled
            or not context.config.anthropic.codebase_review_enabled
        ):
            return None
        client = AnthropicMessagesClient(config=context.config.anthropic)
        if not client.is_configured:
            warnings.append(
                AgentWarning(
                    code="anthropic_codebase_disabled",
                    message=f"{context.config.anthropic.api_key_env} is not set",
                )
            )
            return None
        return AnthropicCodebaseEnhancer(
            client,
            codebase_review_enabled=context.config.anthropic.codebase_review_enabled,
        )

    def _review_codebase(
        self,
        context: AgentExecutionContext,
        manifest: RepoManifest,
        repo_summary: str,
        components: list[ComponentSummary],
        hotspots: list[str],
        enhancer: AnthropicCodebaseEnhancer,
        warnings: list[AgentWarning],
    ) -> CodebaseReviewResponse | None:
        if not enhancer.is_configured:
            return None
        try:
            return enhancer.review_codebase(
                product=context.product,
                manifest=manifest,
                repo_summary=repo_summary,
                components=[component.model_dump(mode="json") for component in components],
                changed_files=context.changed_files,
                hotspot_files=hotspots,
                file_context=representative_file_context(context.repo_root, manifest),
            )
        except AnthropicAdapterError as exc:
            warnings.append(
                AgentWarning(
                    code="anthropic_codebase_fallback",
                    message=f"codebase review fallback: {exc}",
                )
            )
            return None
