from datetime import UTC, datetime
from pathlib import Path

from pm_agent.adapters.research import ArxivEntry, PageSummary
from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.research import ResearchAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import ProductContext, Trigger
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context


class FakeCompetitorClient:
    def fetch_page_summary(self, url: str) -> PageSummary:
        return PageSummary(
            url=url,
            title="Example AI Workflow",
            description="Automation and onboarding assistance for teams.",
            text_excerpt="Automation and onboarding assistance for teams.",
        )


class FakeArxivClient:
    def fetch_category_entries(self, category: str):
        return [
            ArxivEntry(
                arxiv_id="2501.12345v1",
                title="Agentic onboarding systems",
                summary="Improving onboarding workflows with agents.",
                published_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                category=category,
                link="http://arxiv.org/abs/2501.12345v1",
            )
        ]


def test_research_agent_emits_overlap_findings():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(
            vision="Improve onboarding clarity and automation.",
            strategic_priorities=["onboarding automation"],
            target_users=["solo builders"],
        ),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )
    agent = ResearchAgent(
        competitor_client=FakeCompetitorClient(),
        arxiv_client=FakeArxivClient(),
    )

    output = agent.run(context)

    assert output.status.value == "success"
    assert output.competitors
    assert output.papers
    assert any(finding.kind.value == "strategic_opportunity" for finding in output.findings)
