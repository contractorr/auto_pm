"""Deterministic synthesis engine with optional model-backed refinement."""

from __future__ import annotations

from pm_agent.adapters.anthropic import AnthropicAdapterError, AnthropicMessagesClient
from pm_agent.config.models import IssuePolicyConfig, PMConfig
from pm_agent.models.contracts import (
    DedupDecision,
    IssueAction,
    PMAgentMemory,
    SynthesisInput,
)
from pm_agent.models.runtime import SuppressedCluster, SynthesisReport
from pm_agent.synthesis.cluster import build_clusters
from pm_agent.synthesis.dedup import deduplicate_cluster
from pm_agent.synthesis.enhancer import AnthropicSynthesisEnhancer
from pm_agent.synthesis.normalize import collect_findings
from pm_agent.synthesis.score import score_cluster
from pm_agent.synthesis.writer import build_issue_proposal


class SynthesisEngine:
    def __init__(
        self,
        enhancer: AnthropicSynthesisEnhancer | None = None,
        *,
        default_warnings: list[str] | None = None,
    ) -> None:
        self._enhancer = enhancer
        self._default_warnings = default_warnings or []

    @classmethod
    def from_config(cls, config: PMConfig) -> "SynthesisEngine":
        if not config.anthropic.enabled:
            return cls()
        client = AnthropicMessagesClient(config=config.anthropic)
        if not client.is_configured:
            return cls(
                default_warnings=[
                    (
                        "anthropic_synthesis_disabled: "
                        f"{config.anthropic.api_key_env} is not set"
                    )
                ]
            )
        return cls(
            AnthropicSynthesisEnhancer(
                client,
                cluster_review_enabled=config.anthropic.cluster_review_enabled,
                issue_writer_enabled=config.anthropic.issue_writer_enabled,
            )
        )

    def run(
        self,
        synthesis_input: SynthesisInput,
        issue_policy: IssuePolicyConfig,
        memory: PMAgentMemory | None = None,
        base_labels: list[str] | None = None,
    ) -> SynthesisReport:
        findings = collect_findings(synthesis_input)
        if not findings:
            return SynthesisReport()

        clusters = build_clusters(findings)
        proposals = []
        suppressed = []
        warnings: list[str] = list(self._default_warnings)

        for cluster in clusters:
            ice = score_cluster(cluster, synthesis_input.product, memory)
            dedup = deduplicate_cluster(
                cluster,
                synthesis_input.existing_issues.open_issues,
                synthesis_input.existing_issues.recent_closed_issues,
                synthesis_input.existing_issues.open_prs,
            )

            final_action = dedup.action
            if dedup.action == IssueAction.NOOP:
                if ice.confidence < issue_policy.min_confidence:
                    suppressed.append(
                        SuppressedCluster(
                            cluster_id=cluster.cluster_id,
                            title=cluster.title,
                            reason="low_confidence",
                        )
                    )
                    continue
                if ice.priority_score < issue_policy.min_priority_score:
                    suppressed.append(
                        SuppressedCluster(
                            cluster_id=cluster.cluster_id,
                            title=cluster.title,
                            reason="low_priority",
                        )
                    )
                    continue
                final_action = IssueAction.CREATE

            proposal_labels = sorted(
                {*(base_labels or []), cluster.findings[0].kind.value, *cluster.tags}
            )
            final_dedup = DedupDecision(
                action=final_action,
                matched_issue_number=dedup.matched_issue_number,
                rationale=dedup.rationale,
            )
            proposal_title = cluster.title
            proposal_summary = cluster.problem_statement
            proposal_user_problem = cluster.user_impact
            proposal_evidence_summary = "; ".join(
                evidence.summary for finding in cluster.findings for evidence in finding.evidence
            )
            proposal_body = None

            if self._enhancer is not None and self._enhancer.cluster_review_enabled:
                try:
                    review = self._enhancer.review_cluster(
                        product=synthesis_input.product,
                        memory_digest=synthesis_input.memory_digest,
                        cluster=cluster,
                        ice=ice,
                        dedup=final_dedup,
                        labels=proposal_labels,
                    )
                    if dedup.action == IssueAction.NOOP and review.action == "noop":
                        suppressed.append(
                            SuppressedCluster(
                                cluster_id=cluster.cluster_id,
                                title=cluster.title,
                                reason=review.suppression_reason or "llm_suppressed",
                            )
                        )
                        continue
                    proposal_title = review.title or proposal_title
                    proposal_summary = review.summary or proposal_summary
                    proposal_user_problem = review.user_problem or proposal_user_problem
                    proposal_evidence_summary = (
                        review.evidence_summary or proposal_evidence_summary
                    )
                    proposal_labels = sorted({*proposal_labels, *review.labels})

                    if self._enhancer.is_configured and self._enhancer.issue_writer_enabled:
                        proposal_body = self._enhancer.write_issue(
                            product=synthesis_input.product,
                            cluster=cluster,
                            ice=ice,
                            dedup=final_dedup,
                            title=proposal_title,
                            summary=proposal_summary,
                            user_problem=proposal_user_problem,
                            evidence_summary=proposal_evidence_summary,
                            labels=proposal_labels,
                        )
                except AnthropicAdapterError as exc:
                    warnings.append(f"anthropic_synthesis_fallback: {exc}")

            proposals.append(
                build_issue_proposal(
                    cluster,
                    ice,
                    final_dedup,
                    proposal_labels,
                    title=proposal_title,
                    summary=proposal_summary,
                    user_problem=proposal_user_problem,
                    evidence_summary=proposal_evidence_summary,
                    issue_body_markdown=proposal_body,
                )
            )

        proposals = sorted(proposals, key=lambda proposal: proposal.ice.priority_score, reverse=True)
        if len(proposals) > issue_policy.max_new_issues_per_run:
            kept = proposals[: issue_policy.max_new_issues_per_run]
            for proposal in proposals[issue_policy.max_new_issues_per_run :]:
                suppressed.append(
                    SuppressedCluster(
                        cluster_id=proposal.cluster_id,
                        title=proposal.title,
                        reason="issue_budget_exceeded",
                    )
                )
            proposals = kept

        return SynthesisReport(
            clusters=clusters,
            proposals=proposals,
            suppressed=suppressed,
            warnings=warnings,
        )
