"""Render deterministic issue proposals."""

from __future__ import annotations

from pm_agent.models.contracts import DedupDecision, ICEBreakdown, IssueProposal
from pm_agent.models.runtime import FindingCluster


def _evidence_lines(cluster: FindingCluster) -> list[str]:
    lines: list[str] = []
    for finding in cluster.findings:
        for evidence in finding.evidence:
            lines.append(f"- {evidence.summary}")
            for source_ref in evidence.source_refs:
                source_bits = [source_ref.source_type.value, source_ref.title or source_ref.source_id]
                if source_ref.locator:
                    source_bits.append(source_ref.locator)
                lines.append(f"  - source: {' | '.join(source_bits)}")
    return lines or ["- No structured evidence provided."]


def render_issue_markdown(
    cluster: FindingCluster,
    ice: ICEBreakdown,
    dedup: DedupDecision,
) -> str:
    metadata = (
        f"<!-- pm-agent: cluster_id={cluster.cluster_id}; "
        f"source_agents={','.join(agent.value for agent in cluster.source_agents)}; "
        f"convergence={cluster.convergence_count} -->"
    )
    evidence = "\n".join(_evidence_lines(cluster))
    surfaces = ", ".join(cluster.affected_surfaces) or "unspecified"
    sources = ", ".join(agent.value for agent in cluster.source_agents)

    return "\n".join(
        [
            "## Summary",
            cluster.title,
            "",
            "## User Problem",
            cluster.problem_statement,
            "",
            "## Why This Matters",
            cluster.user_impact,
            "",
            "## Evidence",
            evidence,
            "",
            "## Affected Surfaces",
            surfaces,
            "",
            "## ICE Score",
            (
                f"Impact {ice.impact:.2f}, Confidence {ice.confidence:.2f}, "
                f"Ease {ice.ease:.2f}, Priority {ice.priority_score:.2f}"
            ),
            "",
            "## Source Convergence",
            f"{cluster.convergence_count} source families: {sources}",
            "",
            "## Deduplication",
            f"{dedup.action.value}: {dedup.rationale}",
            "",
            metadata,
        ]
    )


def build_issue_proposal(
    cluster: FindingCluster,
    ice: ICEBreakdown,
    dedup: DedupDecision,
    labels: list[str],
) -> IssueProposal:
    return IssueProposal(
        cluster_id=cluster.cluster_id,
        title=cluster.title,
        summary=cluster.problem_statement,
        user_problem=cluster.user_impact,
        evidence_summary="; ".join(
            evidence.summary for finding in cluster.findings for evidence in finding.evidence
        ),
        affected_surfaces=cluster.affected_surfaces,
        labels=labels,
        ice=ice,
        dedup=dedup,
        issue_body_markdown=render_issue_markdown(cluster, ice, dedup),
    )
