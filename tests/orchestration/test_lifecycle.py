from datetime import UTC, datetime

from pm_agent.config.models import GitHubConfig, IssuePolicyConfig
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    DedupDecision,
    ExistingIssuesAgentOutput,
    ICEBreakdown,
    IssueAction,
    IssueProposal,
    IssueStateMemory,
    PMAgentMemory,
    Severity,
)
from pm_agent.models.runtime import (
    FindingCluster,
    SynthesisReport,
    WritebackActionResult,
    WritebackReport,
)
from pm_agent.orchestration.lifecycle import (
    apply_writeback_results_to_memory,
    plan_issue_lifecycle,
)


def _existing_issues(
    *,
    open_issues: list[dict] | None = None,
    recent_closed_issues: list[dict] | None = None,
    open_prs: list[dict] | None = None,
) -> ExistingIssuesAgentOutput:
    now = datetime(2026, 3, 30, tzinfo=UTC)
    return ExistingIssuesAgentOutput(
        agent=AgentName.EXISTING_ISSUES,
        status=AgentStatus.SUCCESS,
        started_at=now,
        ended_at=now,
        open_issues=open_issues or [],
        recent_closed_issues=recent_closed_issues or [],
        open_prs=open_prs or [],
    )


def _cluster(cluster_id: str) -> FindingCluster:
    return FindingCluster(
        cluster_id=cluster_id,
        title="Onboarding clarity gap",
        problem_statement="Users do not know what to do first.",
        user_impact="New users churn before activation.",
        affected_surfaces=["home"],
        tags=["onboarding"],
        source_agents=[AgentName.DOGFOODING],
        findings=[],
        convergence_count=1,
        severity=Severity.MEDIUM,
        average_confidence=0.8,
        novelty_keys=["onboarding-clarity-gap"],
    )


def test_plan_issue_lifecycle_emits_close_after_absence_threshold():
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                absent_runs=1,
                components=["home"],
                source_agents=[AgentName.DOGFOODING],
            )
        },
    )

    proposals, updated_memory = plan_issue_lifecycle(
        synthesis=SynthesisReport(),
        existing_issues=_existing_issues(
            open_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "AI issue body",
                    "labels": ["ai-generated", "pm-agent"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                }
            ]
        ),
        issue_policy=IssuePolicyConfig(auto_close_absent_runs=2),
        github_config=GitHubConfig(stale_days=21),
        memory=memory,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
        base_labels=["ai-generated", "pm-agent"],
    )

    assert len(proposals) == 1
    assert proposals[0].dedup.action.value == "close_existing"
    assert proposals[0].dedup.matched_issue_number == 42
    assert updated_memory.issue_state["42"].absent_runs == 2


def test_plan_issue_lifecycle_resets_absence_when_cluster_is_active():
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                absent_runs=3,
            )
        },
    )
    synthesis = SynthesisReport(clusters=[_cluster("cluster-1")])

    proposals, updated_memory = plan_issue_lifecycle(
        synthesis=synthesis,
        existing_issues=_existing_issues(
            open_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "AI issue body",
                    "labels": ["ai-generated"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                }
            ]
        ),
        issue_policy=IssuePolicyConfig(),
        github_config=GitHubConfig(stale_days=21),
        memory=memory,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
    )

    assert proposals == []
    assert updated_memory.issue_state["42"].absent_runs == 0
    assert updated_memory.issue_state["42"].components == ["home"]
    assert updated_memory.issue_state["42"].source_agents == [AgentName.DOGFOODING]


def test_plan_issue_lifecycle_records_closed_ai_issue_outcome_and_priors():
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                components=["home"],
                source_agents=[AgentName.RESEARCH],
            )
        },
    )

    proposals, updated_memory = plan_issue_lifecycle(
        synthesis=SynthesisReport(),
        existing_issues=_existing_issues(
            recent_closed_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "closed",
                    "body_summary": "Closed as duplicate",
                    "labels": ["ai-generated", "duplicate"],
                    "ai_authored": True,
                }
            ]
        ),
        issue_policy=IssuePolicyConfig(),
        github_config=GitHubConfig(stale_days=21),
        memory=memory,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
    )

    assert proposals == []
    assert "42" not in updated_memory.issue_state
    assert updated_memory.recent_outcomes[0].disposition == "duplicate"
    assert updated_memory.source_priors["research"] == 0.1
    assert updated_memory.component_priors["home"] == 0.1


def test_plan_issue_lifecycle_skips_close_when_matching_open_pr_exists():
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                absent_runs=2,
            )
        },
    )

    proposals, updated_memory = plan_issue_lifecycle(
        synthesis=SynthesisReport(),
        existing_issues=_existing_issues(
            open_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "AI issue body",
                    "labels": ["ai-generated"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                }
            ],
            open_prs=[
                {
                    "number": 77,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "Fixes cluster-1",
                    "labels": [],
                    "ai_authored": False,
                    "cluster_id": "cluster-1",
                }
            ],
        ),
        issue_policy=IssuePolicyConfig(auto_close_absent_runs=2),
        github_config=GitHubConfig(stale_days=21),
        memory=memory,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
    )

    assert proposals == []
    assert updated_memory.issue_state["42"].absent_runs == 3


def test_plan_issue_lifecycle_emits_stale_comment_for_active_old_issue():
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                components=["home"],
                source_agents=[AgentName.DOGFOODING],
            )
        },
    )
    synthesis = SynthesisReport(clusters=[_cluster("cluster-1")])

    proposals, _ = plan_issue_lifecycle(
        synthesis=synthesis,
        existing_issues=_existing_issues(
            open_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "AI issue body",
                    "labels": ["ai-generated"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                    "updated_at": datetime(2026, 3, 1, tzinfo=UTC),
                }
            ]
        ),
        issue_policy=IssuePolicyConfig(),
        github_config=GitHubConfig(stale_days=21),
        memory=memory,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
    )

    assert len(proposals) == 1
    assert proposals[0].dedup.action == IssueAction.COMMENT_EXISTING
    assert "stale" in proposals[0].labels


def test_plan_issue_lifecycle_closes_superseded_duplicate_ai_issue():
    proposals, _ = plan_issue_lifecycle(
        synthesis=SynthesisReport(),
        existing_issues=_existing_issues(
            open_issues=[
                {
                    "number": 42,
                    "title": "Onboarding clarity gap",
                    "state": "open",
                    "body_summary": "AI issue body",
                    "labels": ["ai-generated"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                },
                {
                    "number": 55,
                    "title": "Onboarding clarity gap duplicate",
                    "state": "open",
                    "body_summary": "AI issue duplicate body",
                    "labels": ["ai-generated"],
                    "ai_authored": True,
                    "cluster_id": "cluster-1",
                },
            ]
        ),
        issue_policy=IssuePolicyConfig(auto_close_absent_runs=5),
        github_config=GitHubConfig(stale_days=21),
        memory=None,
        run_started_at=datetime(2026, 3, 30, tzinfo=UTC),
        base_labels=["ai-generated"],
    )

    assert len(proposals) == 1
    assert proposals[0].dedup.action == IssueAction.CLOSE_EXISTING
    assert proposals[0].dedup.matched_issue_number == 55
    assert "superseded" in proposals[0].labels


def test_apply_writeback_results_to_memory_tracks_created_and_escalated_issue():
    now = datetime(2026, 3, 30, tzinfo=UTC)
    proposal = IssueProposal(
        cluster_id="cluster-1",
        title="Onboarding clarity gap",
        summary="summary",
        user_problem="problem",
        evidence_summary="evidence",
        affected_surfaces=["home"],
        labels=["ai-generated", "stale"],
        ice=ICEBreakdown(
            impact=2.0,
            confidence=4.0,
            ease=5.0,
            ice_score=40.0,
            convergence_multiplier=1.0,
            strategic_multiplier=1.0,
            calibration_multiplier=1.0,
            priority_score=40.0,
            rationale="test",
        ),
        dedup=DedupDecision(
            action=IssueAction.COMMENT_EXISTING,
            matched_issue_number=42,
            rationale="test",
        ),
        issue_body_markdown="body",
    )
    synthesis = SynthesisReport(clusters=[_cluster("cluster-1")])
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
            )
        },
    )

    updated_memory = apply_writeback_results_to_memory(
        memory=memory,
        synthesis=synthesis,
        proposals=[proposal],
        writeback=WritebackReport(
            mode="apply",
            results=[
                WritebackActionResult(
                    cluster_id="cluster-1",
                    proposal_title="Onboarding clarity gap",
                    action="comment_existing",
                    outcome="commented",
                    target_number=42,
                    message="commented",
                ),
                WritebackActionResult(
                    cluster_id="cluster-1",
                    proposal_title="Onboarding clarity gap",
                    action="create",
                    outcome="created",
                    target_number=88,
                    message="created",
                ),
            ],
        ),
        now=now,
    )

    assert updated_memory.issue_state["42"].last_escalated_at == now
    assert updated_memory.issue_state["88"].cluster_id == "cluster-1"
    assert updated_memory.issue_state["88"].source_agents == [AgentName.DOGFOODING]


def test_apply_writeback_results_to_memory_records_immediate_close_outcome():
    proposal = IssueProposal(
        cluster_id="cluster-1",
        title="Onboarding clarity gap",
        summary="summary",
        user_problem="problem",
        evidence_summary="became obsolete",
        affected_surfaces=["home"],
        labels=["ai-generated", "obsolete"],
        ice=ICEBreakdown(
            impact=1.0,
            confidence=4.0,
            ease=5.0,
            ice_score=20.0,
            convergence_multiplier=1.0,
            strategic_multiplier=1.0,
            calibration_multiplier=1.0,
            priority_score=20.0,
            rationale="test",
        ),
        dedup=DedupDecision(
            action=IssueAction.CLOSE_EXISTING,
            matched_issue_number=42,
            rationale="test",
        ),
        issue_body_markdown="body",
    )
    memory = PMAgentMemory(
        updated_at=datetime(2026, 3, 29, tzinfo=UTC),
        issue_state={
            "42": IssueStateMemory(
                issue_number=42,
                cluster_id="cluster-1",
                ai_authored=True,
                components=["home"],
                source_agents=[AgentName.DOGFOODING],
            )
        },
    )

    updated_memory = apply_writeback_results_to_memory(
        memory=memory,
        synthesis=SynthesisReport(clusters=[_cluster("cluster-1")]),
        proposals=[proposal],
        writeback=WritebackReport(
            mode="apply",
            results=[
                WritebackActionResult(
                    cluster_id="cluster-1",
                    proposal_title="Onboarding clarity gap",
                    action="close_existing",
                    outcome="closed",
                    target_number=42,
                    message="closed",
                )
            ],
        ),
        now=datetime(2026, 3, 30, tzinfo=UTC),
    )

    assert "42" not in updated_memory.issue_state
    assert updated_memory.recent_outcomes[-1].disposition == "obsolete"
