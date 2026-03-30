from datetime import UTC, datetime
from pathlib import Path

from pm_agent.adapters.research import ArxivEntry, PageSummary
from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.research import ResearchAgent
from pm_agent.agents.research_enhancer import CompetitorReviewResponse, PaperReviewResponse
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


class FakeResearchEnhancer:
    is_configured = True

    def review_competitor(self, **kwargs):
        return CompetitorReviewResponse(
            issue_worthy=True,
            finding_kind="competitive_gap",
            title="Competitor onboarding guidance is sharper",
            problem_statement="Competitor positioning makes the first useful action clearer.",
            user_impact="Users may understand value faster elsewhere.",
            severity="medium",
            confidence=0.78,
            summary="Competitor messaging clearly explains first-session value.",
            notable_capabilities=["guided onboarding", "automation"],
            comparison_notes=["Clearer first-session framing than the target product."],
            tags=["onboarding", "positioning"],
            proposed_direction="Clarify first-session value in the product and landing experience.",
        )

    def review_paper(self, **kwargs):
        return PaperReviewResponse(
            issue_worthy=True,
            title="Recent paper suggests onboarding experiment opportunity",
            problem_statement="Recent research indicates the onboarding flow could be more adaptive.",
            user_impact="The team may miss a useful onboarding experiment.",
            severity="low",
            confidence=0.64,
            relevance_reason="The paper directly discusses agent-assisted onboarding decisions.",
            implication="Worth tracking as a roadmap experiment.",
            tags=["research", "onboarding"],
            proposed_direction="Track a lightweight onboarding experiment informed by the paper.",
        )


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


def test_research_agent_uses_model_backed_reviews_when_enhancer_is_available():
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
        enhancer=FakeResearchEnhancer(),  # type: ignore[arg-type]
    )

    output = agent.run(context)

    assert output.status.value == "success"
    assert output.competitors[0].product_summary == "Competitor messaging clearly explains first-session value."
    assert output.papers[0].relevance_reason == "The paper directly discusses agent-assisted onboarding decisions."
    assert any(finding.kind.value == "competitive_gap" for finding in output.findings)
    assert any(
        finding.title == "Recent paper suggests onboarding experiment opportunity"
        for finding in output.findings
    )


def test_research_agent_warns_when_anthropic_is_enabled_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    config.anthropic.enabled = True
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

    assert any(warning.code == "anthropic_research_disabled" for warning in output.warnings)
    assert output.findings
