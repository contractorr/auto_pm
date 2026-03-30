"""Deterministic lifecycle planning and memory updates."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from pm_agent.config.models import GitHubConfig, IssuePolicyConfig
from pm_agent.memory.store import create_memory
from pm_agent.models.contracts import (
    AgentName,
    DedupDecision,
    ExistingIssueRecord,
    ExistingIssuesAgentOutput,
    ICEBreakdown,
    IssueAction,
    IssueProposal,
    IssueStateMemory,
    MemoryOutcome,
    PMAgentMemory,
)
from pm_agent.models.runtime import FindingCluster, SynthesisReport, WritebackReport

POSITIVE_OUTCOME_SCORES = {
    "fixed": 1.0,
    "obsolete": 0.35,
    "stale": 0.25,
    "duplicate": 0.1,
    "wontfix": 0.0,
}


def _normalize_title(text: str) -> str:
    return " ".join(text.lower().split())


def _infer_disposition(record: ExistingIssueRecord) -> str:
    labels = {label.lower() for label in record.labels}
    if "duplicate" in labels:
        return "duplicate"
    if "wontfix" in labels:
        return "wontfix"
    if "obsolete" in labels:
        return "obsolete"
    if "stale" in labels:
        return "stale"
    return "fixed"


def _cluster_map(synthesis: SynthesisReport) -> dict[str, FindingCluster]:
    return {cluster.cluster_id: cluster for cluster in synthesis.clusters}


def _has_covering_open_pr(record: ExistingIssueRecord, open_prs: list[ExistingIssueRecord]) -> bool:
    normalized_title = _normalize_title(record.title)
    for pr in open_prs:
        if record.cluster_id and pr.cluster_id == record.cluster_id:
            return True
        if record.cluster_id and record.cluster_id in pr.body_summary:
            return True
        if normalized_title and _normalize_title(pr.title) == normalized_title:
            return True
    return False


def _record_timestamp(record: ExistingIssueRecord) -> datetime | None:
    return record.updated_at or record.created_at


def _is_stale(
    record: ExistingIssueRecord,
    *,
    now: datetime,
    stale_days: int,
    last_escalated_at: datetime | None,
) -> bool:
    timestamp = _record_timestamp(record)
    if timestamp is None:
        return False
    cutoff = now - timedelta(days=stale_days)
    if timestamp > cutoff:
        return False
    if last_escalated_at is not None and last_escalated_at > cutoff:
        return False
    return True


def _source_agents_for_cluster(
    cluster_id: str,
    *,
    active_clusters: dict[str, FindingCluster],
    fallback: IssueStateMemory | None,
) -> list[AgentName]:
    if cluster_id in active_clusters:
        return active_clusters[cluster_id].source_agents
    if fallback is not None:
        return fallback.source_agents
    return []


def _record_outcome(
    memory: PMAgentMemory,
    *,
    record: ExistingIssueRecord,
    previous_state: IssueStateMemory | None,
    now: datetime,
) -> None:
    existing_numbers = {outcome.issue_number for outcome in memory.recent_outcomes}
    if record.number in existing_numbers:
        return

    memory.recent_outcomes.append(
        MemoryOutcome(
            issue_number=record.number,
            cluster_id=record.cluster_id
            or (previous_state.cluster_id if previous_state is not None else f"issue-{record.number}"),
            disposition=_infer_disposition(record),  # type: ignore[arg-type]
            components=previous_state.components if previous_state is not None else [],
            source_agents=previous_state.source_agents if previous_state is not None else [],
            maintainer_reason=record.body_summary[:200] or None,
            closed_at=now,
        )
    )


def _recompute_priors(memory: PMAgentMemory) -> None:
    recent = memory.recent_outcomes[-200:]
    source_scores: dict[str, list[float]] = {}
    component_scores: dict[str, list[float]] = {}

    for outcome in recent:
        score = POSITIVE_OUTCOME_SCORES[outcome.disposition]
        for agent in outcome.source_agents:
            source_scores.setdefault(agent.value, []).append(score)
        for component in outcome.components:
            component_scores.setdefault(component, []).append(score)

    memory.source_priors = {
        key: round(sum(values) / len(values), 2)
        for key, values in sorted(source_scores.items())
        if values
    }
    memory.component_priors = {
        key: round(sum(values) / len(values), 2)
        for key, values in sorted(component_scores.items())
        if values
    }


def _build_stale_comment_proposal(
    record: ExistingIssueRecord,
    *,
    state: IssueStateMemory,
    stale_days: int,
    now: datetime,
    base_labels: list[str],
) -> IssueProposal:
    timestamp = _record_timestamp(record)
    stale_for_days = stale_days
    if timestamp is not None:
        stale_for_days = max(stale_days, int((now - timestamp).days))
    rationale = (
        f"AI-authored issue cluster {state.cluster_id} is still active but has not been updated "
        f"for at least {stale_for_days} days"
    )
    ice = ICEBreakdown(
        impact=2.0,
        confidence=4.0,
        ease=5.0,
        ice_score=40.0,
        convergence_multiplier=1.0,
        strategic_multiplier=1.0,
        calibration_multiplier=1.0,
        priority_score=40.0,
        rationale=rationale,
    )
    dedup = DedupDecision(
        action=IssueAction.COMMENT_EXISTING,
        matched_issue_number=record.number,
        rationale=rationale,
    )
    issue_body = "\n".join(
        [
            "## Lifecycle Escalation",
            "This AI-authored issue is still active and appears stale.",
            "",
            "## Why",
            rationale,
            "",
            "## Suggested Follow-up",
            "- Reconfirm ownership or priority.",
            "- Close as wontfix/obsolete if it is no longer relevant.",
            "",
            (
                f"<!-- pm-agent: lifecycle=stale; cluster_id={state.cluster_id or f'issue-{record.number}'}; "
                f"stale_days={stale_for_days} -->"
            ),
        ]
    )
    return IssueProposal(
        cluster_id=state.cluster_id or f"issue-{record.number}",
        title=record.title,
        summary="AI-authored issue remains active but appears stale.",
        user_problem="The underlying product problem is still being detected without issue movement.",
        evidence_summary=rationale,
        affected_surfaces=state.components,
        labels=sorted({*base_labels, "lifecycle", "stale"}),
        ice=ice,
        dedup=dedup,
        issue_body_markdown=issue_body,
    )


def _update_open_issue_state(
    memory: PMAgentMemory,
    *,
    record: ExistingIssueRecord,
    active_clusters: dict[str, FindingCluster],
    now: datetime,
    issue_policy: IssuePolicyConfig,
) -> None:
    if issue_policy.auto_close_ai_issues_only and not record.ai_authored:
        return

    key = str(record.number)
    previous = memory.issue_state.get(key)
    state = previous.model_copy(deep=True) if previous is not None else IssueStateMemory(issue_number=record.number)
    state.issue_number = record.number
    state.cluster_id = record.cluster_id or state.cluster_id
    state.ai_authored = record.ai_authored
    state.last_seen_open_at = now

    if state.cluster_id and state.cluster_id in active_clusters:
        cluster = active_clusters[state.cluster_id]
        state.absent_runs = 0
        state.last_seen_cluster_at = now
        state.components = cluster.affected_surfaces
        state.source_agents = cluster.source_agents
    elif state.cluster_id:
        state.absent_runs += 1
    else:
        state.absent_runs = 0

    memory.issue_state[key] = state


def _build_close_proposal(
    record: ExistingIssueRecord,
    *,
    state: IssueStateMemory,
    base_labels: list[str],
    rationale: str | None = None,
    summary: str | None = None,
    metadata_reason: str = "close",
) -> IssueProposal:
    confidence = min(5.0, 2.0 + state.absent_runs)
    priority_score = round(confidence * 5.0, 2)
    resolved_rationale = rationale or (
        f"AI-authored issue cluster {state.cluster_id} has been absent for "
        f"{state.absent_runs} consecutive runs"
    )
    ice = ICEBreakdown(
        impact=1.0,
        confidence=confidence,
        ease=5.0,
        ice_score=round(confidence * 5.0, 2),
        convergence_multiplier=1.0,
        strategic_multiplier=1.0,
        calibration_multiplier=1.0,
        priority_score=priority_score,
        rationale=resolved_rationale,
    )
    dedup = DedupDecision(
        action=IssueAction.CLOSE_EXISTING,
        matched_issue_number=record.number,
        rationale=resolved_rationale,
    )
    labels = sorted({*base_labels, "lifecycle", "obsolete"})
    issue_body = "\n".join(
        [
            "## Lifecycle Decision",
            "This AI-authored issue is being proposed for closure.",
            "",
            "## Why",
            resolved_rationale,
            "",
            "## Guardrails",
            "- Only AI-authored issues are auto-closed.",
            "- No active cluster was observed for this issue in the current run.",
            "",
            (
                f"<!-- pm-agent: lifecycle={metadata_reason}; cluster_id={state.cluster_id or f'issue-{record.number}'}; "
                f"absent_runs={state.absent_runs} -->"
            ),
        ]
    )
    return IssueProposal(
        cluster_id=state.cluster_id or f"issue-{record.number}",
        title=record.title,
        summary=summary or "AI-authored issue appears resolved or obsolete based on repeated absence.",
        user_problem="The original problem has not been re-observed in recent runs.",
        evidence_summary=resolved_rationale,
        affected_surfaces=state.components,
        labels=labels,
        ice=ice,
        dedup=dedup,
        issue_body_markdown=issue_body,
    )


def _superseded_records(
    records: list[ExistingIssueRecord],
    *,
    auto_close_ai_issues_only: bool,
) -> list[tuple[ExistingIssueRecord, ExistingIssueRecord]]:
    groups: dict[str, list[ExistingIssueRecord]] = defaultdict(list)
    for record in records:
        if auto_close_ai_issues_only and not record.ai_authored:
            continue
        if not record.cluster_id:
            continue
        groups[record.cluster_id].append(record)

    superseded: list[tuple[ExistingIssueRecord, ExistingIssueRecord]] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda record: record.number)
        canonical = ordered[0]
        for duplicate in ordered[1:]:
            superseded.append((duplicate, canonical))
    return superseded


def plan_issue_lifecycle(
    *,
    synthesis: SynthesisReport,
    existing_issues: ExistingIssuesAgentOutput,
    issue_policy: IssuePolicyConfig,
    github_config: GitHubConfig,
    memory: PMAgentMemory | None,
    run_started_at: datetime | None = None,
    base_labels: list[str] | None = None,
) -> tuple[list[IssueProposal], PMAgentMemory]:
    now = run_started_at or datetime.now(UTC)
    working_memory = memory.model_copy(deep=True) if memory is not None else create_memory(now=now)
    active_clusters = _cluster_map(synthesis)

    for record in existing_issues.open_issues:
        _update_open_issue_state(
            working_memory,
            record=record,
            active_clusters=active_clusters,
            now=now,
            issue_policy=issue_policy,
        )

    for record in existing_issues.recent_closed_issues:
        if issue_policy.auto_close_ai_issues_only and not record.ai_authored:
            continue
        key = str(record.number)
        previous_state = working_memory.issue_state.pop(key, None)
        if record.ai_authored or previous_state is not None:
            _record_outcome(
                working_memory,
                record=record,
                previous_state=previous_state,
                now=now,
            )

    proposals: list[IssueProposal] = []
    superseded_issue_numbers: set[int] = set()
    for duplicate, canonical in _superseded_records(
        existing_issues.open_issues,
        auto_close_ai_issues_only=issue_policy.auto_close_ai_issues_only,
    ):
        superseded_issue_numbers.add(duplicate.number)
        state = working_memory.issue_state.get(str(duplicate.number))
        if state is None:
            state = IssueStateMemory(
                issue_number=duplicate.number,
                cluster_id=duplicate.cluster_id,
                ai_authored=duplicate.ai_authored,
                last_seen_open_at=now,
            )
        proposals.append(
            _build_close_proposal(
                duplicate,
                state=state,
                base_labels=[*(base_labels or []), "superseded"],
                rationale=(
                    f"AI-authored issue #{duplicate.number} is superseded by "
                    f"AI-authored issue #{canonical.number} for cluster {state.cluster_id}"
                ),
                summary="AI-authored duplicate issue is superseded by an older canonical issue.",
                metadata_reason="superseded",
            )
        )

    for record in existing_issues.open_issues:
        if issue_policy.auto_close_ai_issues_only and not record.ai_authored:
            continue
        if record.number in superseded_issue_numbers:
            continue
        key = str(record.number)
        state = working_memory.issue_state.get(key)
        if state is None or not state.cluster_id:
            continue
        if state.cluster_id in active_clusters:
            if _is_stale(
                record,
                now=now,
                stale_days=github_config.stale_days,
                last_escalated_at=state.last_escalated_at,
            ):
                proposals.append(
                    _build_stale_comment_proposal(
                        record,
                        state=state,
                        stale_days=github_config.stale_days,
                        now=now,
                        base_labels=base_labels or [],
                    )
                )
            continue
        if state.absent_runs < issue_policy.auto_close_absent_runs:
            continue
        if _has_covering_open_pr(record, existing_issues.open_prs):
            continue
        proposals.append(
            _build_close_proposal(record, state=state, base_labels=base_labels or [])
        )

    working_memory.recent_outcomes = working_memory.recent_outcomes[-200:]
    _recompute_priors(working_memory)
    working_memory.updated_at = now
    return proposals, working_memory


def apply_writeback_results_to_memory(
    *,
    memory: PMAgentMemory,
    synthesis: SynthesisReport,
    proposals: list[IssueProposal],
    writeback: WritebackReport,
    now: datetime | None = None,
) -> PMAgentMemory:
    updated_memory = memory.model_copy(deep=True)
    current_time = now or datetime.now(UTC)
    proposal_map = {proposal.cluster_id: proposal for proposal in proposals}
    active_clusters = _cluster_map(synthesis)

    for result in writeback.results:
        proposal = proposal_map.get(result.cluster_id)
        if proposal is None:
            continue

        if result.outcome == "created" and result.target_number is not None:
            cluster = active_clusters.get(result.cluster_id)
            updated_memory.issue_state[str(result.target_number)] = IssueStateMemory(
                issue_number=result.target_number,
                cluster_id=result.cluster_id,
                ai_authored=True,
                absent_runs=0,
                last_seen_open_at=current_time,
                last_seen_cluster_at=current_time,
                components=proposal.affected_surfaces,
                source_agents=cluster.source_agents if cluster is not None else [],
            )
            continue

        if result.outcome == "updated" and result.target_number is not None:
            state = updated_memory.issue_state.get(str(result.target_number))
            if state is None:
                state = IssueStateMemory(
                    issue_number=result.target_number,
                    cluster_id=result.cluster_id,
                    ai_authored=True,
                )
            state.cluster_id = result.cluster_id
            state.last_seen_open_at = current_time
            state.last_seen_cluster_at = current_time
            state.components = proposal.affected_surfaces
            state.source_agents = _source_agents_for_cluster(
                result.cluster_id,
                active_clusters=active_clusters,
                fallback=state,
            )
            updated_memory.issue_state[str(result.target_number)] = state
            continue

        if result.outcome == "commented" and result.target_number is not None and "stale" in proposal.labels:
            state = updated_memory.issue_state.get(str(result.target_number))
            if state is not None:
                state.last_escalated_at = current_time
            continue

        if result.outcome == "closed" and result.target_number is not None:
            previous_state = updated_memory.issue_state.pop(str(result.target_number), None)
            updated_memory.recent_outcomes.append(
                MemoryOutcome(
                    issue_number=result.target_number,
                    cluster_id=result.cluster_id,
                    disposition="obsolete",
                    components=proposal.affected_surfaces,
                    source_agents=_source_agents_for_cluster(
                        result.cluster_id,
                        active_clusters=active_clusters,
                        fallback=previous_state,
                    ),
                    maintainer_reason=proposal.evidence_summary[:200] or None,
                    closed_at=current_time,
                )
            )

    updated_memory.recent_outcomes = updated_memory.recent_outcomes[-200:]
    _recompute_priors(updated_memory)
    updated_memory.updated_at = current_time
    return updated_memory
