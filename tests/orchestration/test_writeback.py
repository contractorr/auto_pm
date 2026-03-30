from datetime import UTC, datetime

from pm_agent.config.models import GitHubConfig, GitHubWriteMode
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    DedupDecision,
    ExistingIssuesAgentOutput,
    ICEBreakdown,
    IssueAction,
    IssueProposal,
)
from pm_agent.orchestration.writeback import GitHubWritebackApplier


class FakeGitHubClient:
    def __init__(self) -> None:
        self.created_issues: list[dict] = []
        self.updated_issues: list[tuple[int, dict]] = []
        self.comments: list[tuple[int, str]] = []

    def create_issue(self, owner: str, repo: str, *, title: str, body: str, labels: list[str]):
        issue = {"number": 101, "title": title, "body": body, "labels": labels}
        self.created_issues.append(issue)
        return issue

    def update_issue(self, owner: str, repo: str, issue_number: int, **data):
        self.updated_issues.append((issue_number, data))
        return {"number": issue_number, **data}

    def create_issue_comment(self, owner: str, repo: str, issue_number: int, *, body: str):
        self.comments.append((issue_number, body))
        return {"id": 1, "body": body}


def _proposal(action: IssueAction, matched_issue_number: int | None = None) -> IssueProposal:
    return IssueProposal(
        cluster_id="cluster-1",
        title="Improve onboarding clarity",
        summary="The app should explain the first useful action after login.",
        user_problem="Users do not know what to do first.",
        evidence_summary="Evidence summary",
        affected_surfaces=["login", "home"],
        labels=["ai-generated", "pm-agent", "ux"],
        ice=ICEBreakdown(
            impact=4.0,
            confidence=4.0,
            ease=3.0,
            ice_score=48.0,
            convergence_multiplier=1.3,
            strategic_multiplier=1.25,
            calibration_multiplier=1.0,
            priority_score=78.0,
            rationale="test",
        ),
        dedup=DedupDecision(
            action=action,
            matched_issue_number=matched_issue_number,
            rationale="test rationale",
        ),
        issue_body_markdown="## Summary\nTest body\n<!-- pm-agent: cluster_id=cluster-1 -->",
    )


def _existing(ai_authored: bool = True) -> ExistingIssuesAgentOutput:
    return ExistingIssuesAgentOutput(
        agent=AgentName.EXISTING_ISSUES,
        status=AgentStatus.SUCCESS,
        started_at=datetime(2026, 3, 30, tzinfo=UTC),
        ended_at=datetime(2026, 3, 30, tzinfo=UTC),
        open_issues=[
            {
                "number": 42,
                "title": "Existing issue",
                "state": "open",
                "body_summary": "Existing issue body",
                "labels": ["pm-agent"] if ai_authored else ["bug"],
                "ai_authored": ai_authored,
            }
        ],
        recent_closed_issues=[],
        open_prs=[],
    )


def test_writeback_comment_only_skips_create():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.CREATE)],
        existing_issues=_existing(),
        github_config=GitHubConfig(),
        mode=GitHubWriteMode.COMMENT_ONLY,
    )
    assert report.results[0].outcome == "skipped"
    assert client.created_issues == []


def test_writeback_apply_creates_issue():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.CREATE)],
        existing_issues=_existing(),
        github_config=GitHubConfig(),
        mode=GitHubWriteMode.APPLY,
    )
    assert report.results[0].outcome == "created"
    assert client.created_issues[0]["title"] == "Improve onboarding clarity"


def test_writeback_updates_ai_authored_issue_in_apply_mode():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.UPDATE_EXISTING, matched_issue_number=42)],
        existing_issues=_existing(ai_authored=True),
        github_config=GitHubConfig(update_ai_authored_issues_only=True),
        mode=GitHubWriteMode.APPLY,
    )
    assert report.results[0].outcome == "updated"
    assert client.updated_issues[0][0] == 42


def test_writeback_comments_on_human_issue_even_in_apply_mode():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.UPDATE_EXISTING, matched_issue_number=42)],
        existing_issues=_existing(ai_authored=False),
        github_config=GitHubConfig(update_ai_authored_issues_only=True),
        mode=GitHubWriteMode.APPLY,
    )
    assert report.results[0].outcome == "commented"
    assert client.comments[0][0] == 42


def test_writeback_apply_closes_ai_authored_issue():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.CLOSE_EXISTING, matched_issue_number=42)],
        existing_issues=_existing(ai_authored=True),
        github_config=GitHubConfig(update_ai_authored_issues_only=True),
        mode=GitHubWriteMode.APPLY,
    )
    assert report.results[0].outcome == "closed"
    assert client.updated_issues[0] == (42, {"state": "closed"})


def test_writeback_refuses_to_close_human_issue():
    client = FakeGitHubClient()
    report = GitHubWritebackApplier(client=client).apply(
        owner="contractorr",
        repo="stewardme",
        proposals=[_proposal(IssueAction.CLOSE_EXISTING, matched_issue_number=42)],
        existing_issues=_existing(ai_authored=False),
        github_config=GitHubConfig(update_ai_authored_issues_only=True),
        mode=GitHubWriteMode.APPLY,
    )
    assert report.results[0].outcome == "skipped"
    assert client.updated_issues == []
