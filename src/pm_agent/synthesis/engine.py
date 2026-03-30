"""Deterministic synthesis engine."""

from __future__ import annotations

from pm_agent.config.models import IssuePolicyConfig
from pm_agent.models.contracts import (
    DedupDecision,
    IssueAction,
    PMAgentMemory,
    SynthesisInput,
)
from pm_agent.models.runtime import SuppressedCluster, SynthesisReport
from pm_agent.synthesis.cluster import build_clusters
from pm_agent.synthesis.dedup import deduplicate_cluster
from pm_agent.synthesis.normalize import collect_findings
from pm_agent.synthesis.score import score_cluster
from pm_agent.synthesis.writer import build_issue_proposal


class SynthesisEngine:
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
            proposals.append(build_issue_proposal(cluster, ice, final_dedup, proposal_labels))

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

        return SynthesisReport(clusters=clusters, proposals=proposals, suppressed=suppressed)
