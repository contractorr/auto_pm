"""Portfolio-level synthesis selection and budgeting."""

from __future__ import annotations

from dataclasses import dataclass

from pm_agent.config.models import IssuePolicyConfig
from pm_agent.models.contracts import ICEBreakdown, IssueAction, IssueProposal, ProductContext
from pm_agent.models.runtime import FindingCluster, SuppressedCluster
from pm_agent.synthesis.enhancer import AnthropicAdapterError, AnthropicSynthesisEnhancer


@dataclass(frozen=True)
class PortfolioCandidate:
    cluster: FindingCluster
    ice: ICEBreakdown
    proposal: IssueProposal


def apply_issue_budget(
    candidates: list[PortfolioCandidate],
    *,
    product: ProductContext,
    memory_digest: str,
    issue_policy: IssuePolicyConfig,
    enhancer: AnthropicSynthesisEnhancer | None,
) -> tuple[list[IssueProposal], list[SuppressedCluster], list[str]]:
    warnings: list[str] = []
    suppressed: list[SuppressedCluster] = []

    non_create_candidates = [
        candidate
        for candidate in candidates
        if candidate.proposal.dedup.action != IssueAction.CREATE
    ]
    create_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.proposal.dedup.action == IssueAction.CREATE
        ),
        key=_portfolio_sort_key,
        reverse=True,
    )

    if len(create_candidates) <= issue_policy.max_new_issues_per_run:
        kept_candidates = non_create_candidates + create_candidates
        return _sorted_proposals(kept_candidates), suppressed, warnings

    selected_cluster_ids: list[str] | None = None
    suppressed_reasons: dict[str, str] = {}
    if enhancer is not None and enhancer.is_configured and enhancer.portfolio_review_enabled:
        try:
            review = enhancer.review_portfolio(
                product=product,
                memory_digest=memory_digest,
                max_new_issues_per_run=issue_policy.max_new_issues_per_run,
                proposals=[
                    {
                        "cluster_id": candidate.cluster.cluster_id,
                        "title": candidate.proposal.title,
                        "priority_score": candidate.proposal.ice.priority_score,
                        "confidence": candidate.proposal.ice.confidence,
                        "impact": candidate.proposal.ice.impact,
                        "convergence_count": candidate.cluster.convergence_count,
                        "source_agents": [
                            agent.value for agent in candidate.cluster.source_agents
                        ],
                        "affected_surfaces": candidate.proposal.affected_surfaces,
                        "labels": candidate.proposal.labels,
                        "summary": candidate.proposal.summary,
                    }
                    for candidate in create_candidates
                ],
            )
            allowed_ids = {candidate.cluster.cluster_id for candidate in create_candidates}
            selected_cluster_ids = [
                cluster_id
                for cluster_id in review.keep_cluster_ids
                if cluster_id in allowed_ids
            ][: issue_policy.max_new_issues_per_run]
            suppressed_reasons = {
                cluster_id: reason
                for cluster_id, reason in review.suppressed_reasons.items()
                if cluster_id in allowed_ids
            }
        except AnthropicAdapterError as exc:
            warnings.append(f"anthropic_portfolio_fallback: {exc}")

    if selected_cluster_ids is None:
        kept_create_candidates = create_candidates[: issue_policy.max_new_issues_per_run]
        dropped_create_candidates = create_candidates[issue_policy.max_new_issues_per_run :]
    else:
        selected_id_set = set(selected_cluster_ids)
        kept_create_candidates = [
            candidate
            for candidate in create_candidates
            if candidate.cluster.cluster_id in selected_id_set
        ]
        dropped_create_candidates = [
            candidate
            for candidate in create_candidates
            if candidate.cluster.cluster_id not in selected_id_set
        ]
        if len(kept_create_candidates) < issue_policy.max_new_issues_per_run:
            backfill = [
                candidate
                for candidate in create_candidates
                if candidate.cluster.cluster_id not in selected_id_set
            ][: issue_policy.max_new_issues_per_run - len(kept_create_candidates)]
            kept_create_candidates.extend(backfill)
            dropped_ids = {candidate.cluster.cluster_id for candidate in backfill}
            dropped_create_candidates = [
                candidate
                for candidate in dropped_create_candidates
                if candidate.cluster.cluster_id not in dropped_ids
            ]

    for candidate in dropped_create_candidates:
        suppressed.append(
            SuppressedCluster(
                cluster_id=candidate.cluster.cluster_id,
                title=candidate.proposal.title,
                reason=suppressed_reasons.get(
                    candidate.cluster.cluster_id,
                    "issue_budget_exceeded",
                ),
            )
        )

    kept_candidates = non_create_candidates + kept_create_candidates
    return _sorted_proposals(kept_candidates), suppressed, warnings


def _sorted_proposals(candidates: list[PortfolioCandidate]) -> list[IssueProposal]:
    return [
        candidate.proposal
        for candidate in sorted(candidates, key=_proposal_sort_key, reverse=True)
    ]


def _proposal_sort_key(candidate: PortfolioCandidate) -> tuple[float, float, int]:
    action_bias = 1.0 if candidate.proposal.dedup.action != IssueAction.CREATE else 0.0
    return (
        action_bias,
        candidate.proposal.ice.priority_score,
        candidate.cluster.convergence_count,
    )


def _portfolio_sort_key(candidate: PortfolioCandidate) -> tuple[float, float, float, int]:
    return (
        candidate.proposal.ice.priority_score,
        candidate.proposal.ice.confidence,
        candidate.proposal.ice.impact,
        candidate.cluster.convergence_count,
    )
