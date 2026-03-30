from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.existing_issues import ExistingIssuesAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import ProductContext, Trigger
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context


class FakeGitHubClient:
    def list_open_issues(self, owner: str, repo: str, max_pages: int = 1):
        return [
            {
                "number": 12,
                "title": "Onboarding guidance gap",
                "body": "Users do not know what to do first. <!-- pm-agent: cluster_id=abc123 -->",
                "labels": [{"name": "ai-generated"}, {"name": "onboarding"}],
            }
        ]

    def list_recent_closed_issues(self, owner: str, repo: str, max_pages: int = 1):
        return [
            {
                "number": 10,
                "title": "Old AI issue",
                "body": "Closed previously.",
                "labels": [{"name": "ai-generated"}],
            }
        ]

    def list_open_pull_requests(self, owner: str, repo: str, max_pages: int = 1):
        return [
            {
                "number": 44,
                "title": "Fix onboarding guidance gap",
                "body": "PR body",
                "labels": [],
            }
        ]


def test_existing_issues_agent_maps_records_from_client():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )

    output = ExistingIssuesAgent(client=FakeGitHubClient()).run(context)

    assert output.status.value == "success"
    assert output.open_issues[0].ai_authored is True
    assert output.open_issues[0].cluster_id == "abc123"
    assert output.open_prs[0].number == 44
