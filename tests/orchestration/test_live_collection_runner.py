import shutil
from pathlib import Path

from pm_agent.agents.existing_issues import ExistingIssuesAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.orchestration.live import LiveCollectionRunner


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
            journeys=[],
        )


class FakeResearchAgent:
    def run(self, context):
        from pm_agent.models.contracts import AgentName, AgentStatus, ResearchAgentOutput

        return ResearchAgentOutput(
            agent=AgentName.RESEARCH,
            status=AgentStatus.SUCCESS,
            started_at=context.run.started_at,
            ended_at=context.run.started_at,
            findings=[],
            competitors=[],
            papers=[],
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
    assert len(report.synthesis.proposals) == 1
    assert report.synthesis.proposals[0].title == "Repo has no detectable test coverage"


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
