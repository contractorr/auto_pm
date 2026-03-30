import shutil
from datetime import UTC, datetime
from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.existing_issues import ExistingIssuesAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    CodebaseAgentOutput,
    Evidence,
    ExistingIssuesAgentOutput,
    Finding,
    FindingKind,
    JourneyRun,
    JourneyStepResult,
    Severity,
    Trigger,
)
from pm_agent.orchestration.live import LiveCollectionRunner
from pm_agent.orchestration.locks import FileRunLock


class FakeGitHubClient:
    def list_open_issues(self, owner: str, repo: str, max_pages: int = 1):
        return []

    def list_recent_closed_issues(self, owner: str, repo: str, max_pages: int = 1):
        return []

    def list_open_pull_requests(self, owner: str, repo: str, max_pages: int = 1):
        return []


class FakeDogfoodingAgent:
    def run(self, context):
        from pm_agent.models.contracts import AgentName, AgentStatus, DogfoodingAgentOutput

        return DogfoodingAgentOutput(
            agent=AgentName.DOGFOODING,
            status=AgentStatus.SUCCESS,
            started_at=context.run.started_at,
            ended_at=context.run.started_at,
            findings=[],
            runtime_mode=context.config.runtime.mode.value,
            base_url=context.config.runtime.service_urls[0],
            journeys=[
                JourneyRun(
                    journey_id="home",
                    persona="guest",
                    success=True,
                    started_at=datetime(2026, 3, 30, tzinfo=UTC),
                    ended_at=datetime(2026, 3, 30, tzinfo=UTC),
                    steps=[
                        JourneyStepResult(
                            step_id="landing",
                            action="visit",
                            url=f"{context.config.runtime.service_urls[0]}/",
                            success=True,
                            screenshot_path=".pm-agent-artifacts/run-1/dogfooding/home/landing.png",
                            accessibility_snapshot_path=".pm-agent-artifacts/run-1/dogfooding/home/landing.a11y.json",
                        )
                    ],
                )
            ],
        )


class FakeResearchAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, context):
        from pm_agent.models.contracts import AgentName, AgentStatus, ResearchAgentOutput

        self.calls += 1

        return ResearchAgentOutput(
            agent=AgentName.RESEARCH,
            status=AgentStatus.SUCCESS,
            started_at=context.run.started_at,
            ended_at=context.run.started_at,
            findings=[],
            competitors=[],
            papers=[],
        )


class FakeCodebaseAgent:
    def run(self, context: AgentExecutionContext) -> CodebaseAgentOutput:
        findings = [
            Finding(
                finding_id="finding-1",
                agent=AgentName.CODEBASE,
                kind=FindingKind.TECHNICAL_RISK,
                title="First push finding",
                problem_statement="First change needs attention.",
                user_impact="Could affect users.",
                severity=Severity.HIGH,
                raw_confidence=0.9,
                novelty_key="push-finding-1",
                dedup_keys=["push-finding-1"],
                evidence=[Evidence(summary="one")],
            ),
            Finding(
                finding_id="finding-2",
                agent=AgentName.CODEBASE,
                kind=FindingKind.TECHNICAL_RISK,
                title="Second push finding",
                problem_statement="Second change needs attention.",
                user_impact="Could affect users.",
                severity=Severity.HIGH,
                raw_confidence=0.9,
                novelty_key="push-finding-2",
                dedup_keys=["push-finding-2"],
                evidence=[Evidence(summary="two")],
            ),
        ]
        return CodebaseAgentOutput(
            agent=AgentName.CODEBASE,
            status=AgentStatus.SUCCESS,
            started_at=context.run.started_at,
            ended_at=context.run.started_at,
            findings=findings,
            repo_summary="fake summary",
            components=[],
            changed_files=context.changed_files,
            hotspot_files=[],
        )


class FakeExistingIssuesAgent:
    def run(self, context: AgentExecutionContext) -> ExistingIssuesAgentOutput:
        return ExistingIssuesAgentOutput(
            agent=AgentName.EXISTING_ISSUES,
            status=AgentStatus.SUCCESS,
            started_at=context.run.started_at,
            ended_at=context.run.started_at,
            findings=[],
            open_issues=[],
            recent_closed_issues=[],
            open_prs=[],
        )


def test_live_collection_runner_executes_without_network():
    config = load_pm_config(Path("pm-config.example.yml"))
    repo_root = Path("tests/fixtures/repos/sample-app")
    runner = LiveCollectionRunner(
        research_agent=FakeResearchAgent(),  # type: ignore[arg-type]
        dogfooding_agent=FakeDogfoodingAgent(),  # type: ignore[arg-type]
        existing_issues_agent=ExistingIssuesAgent(client=FakeGitHubClient()),
    )

    report = runner.run(repo_root, config)

    assert {output.agent.value for output in report.agent_outputs} == {
        "research",
        "codebase",
        "dogfooding",
        "existing_issues",
    }
    assert len(report.artifacts) == 2
    assert report.events[0].code == "run_started"
    assert len(report.synthesis.proposals) == 0


def test_live_collection_runner_persists_memory_when_enabled(tmp_path):
    config = load_pm_config(Path("pm-config.example.yml"))
    repo_root = tmp_path / "sample-app"
    shutil.copytree(Path("tests/fixtures/repos/sample-app"), repo_root)
    runner = LiveCollectionRunner(
        research_agent=FakeResearchAgent(),  # type: ignore[arg-type]
        dogfooding_agent=FakeDogfoodingAgent(),  # type: ignore[arg-type]
        existing_issues_agent=ExistingIssuesAgent(client=FakeGitHubClient()),
    )

    runner.run(repo_root, config, persist_memory=True)

    assert (repo_root / config.repo.memory_file).exists()


def test_live_collection_runner_push_trigger_skips_research_and_limits_issue_budget():
    config = load_pm_config(Path("pm-config.example.yml"))
    repo_root = Path("tests/fixtures/repos/sample-app")
    research = FakeResearchAgent()
    runner = LiveCollectionRunner(
        research_agent=research,  # type: ignore[arg-type]
        codebase_agent=FakeCodebaseAgent(),  # type: ignore[arg-type]
        dogfooding_agent=FakeDogfoodingAgent(),  # type: ignore[arg-type]
        existing_issues_agent=FakeExistingIssuesAgent(),  # type: ignore[arg-type]
    )

    report = runner.run(repo_root, config, trigger=Trigger.PUSH)

    research_output = next(output for output in report.agent_outputs if output.agent.value == "research")
    assert research.calls == 0
    assert research_output.status.value == "skipped"
    assert len(report.synthesis.proposals) == 1


def test_live_collection_runner_returns_skipped_report_when_repo_is_locked(tmp_path):
    config = load_pm_config(Path("pm-config.example.yml"))
    repo_root = tmp_path / "sample-app"
    shutil.copytree(Path("tests/fixtures/repos/sample-app"), repo_root)
    lock = FileRunLock()
    lease = lock.acquire(
        lock_path=repo_root / ".pm-agent-run.lock",
        run_id="run-1",
        repo=config.repo.full_name,
        trigger="schedule",
    )
    try:
        runner = LiveCollectionRunner(
            research_agent=FakeResearchAgent(),  # type: ignore[arg-type]
            dogfooding_agent=FakeDogfoodingAgent(),  # type: ignore[arg-type]
            existing_issues_agent=ExistingIssuesAgent(client=FakeGitHubClient()),
            run_lock=lock,
        )

        report = runner.run(repo_root, config)
    finally:
        lease.release()

    assert all(output.status.value == "skipped" for output in report.agent_outputs)
    assert report.synthesis.warnings
    assert report.synthesis.warnings[0].startswith("run_locked:")
    assert report.events[0].code == "run_locked"
