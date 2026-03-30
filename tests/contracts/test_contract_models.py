from datetime import UTC, datetime

from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    ExistingIssuesAgentOutput,
    FindingKind,
    ProductContext,
    ResearchAgentOutput,
    RunContext,
    SynthesisInput,
    Trigger,
)


def test_research_output_parses_with_finding():
    output = ResearchAgentOutput.model_validate(
        {
            "agent": "research",
            "status": "success",
            "started_at": "2026-03-30T10:00:00Z",
            "ended_at": "2026-03-30T10:05:00Z",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "agent": "research",
                    "kind": "competitive_gap",
                    "title": "Activation messaging is weak",
                    "problem_statement": "The app does not frame first-session value concretely.",
                    "user_impact": "New users may churn before seeing value.",
                    "severity": "medium",
                    "raw_confidence": 0.84,
                    "novelty_key": "activation-value-framing",
                    "tags": ["activation"],
                }
            ],
            "competitors": [],
            "papers": [],
        }
    )
    assert output.agent == AgentName.RESEARCH
    assert output.status == AgentStatus.SUCCESS
    assert output.findings[0].kind == FindingKind.COMPETITIVE_GAP


def test_synthesis_input_accepts_partial_agent_outputs():
    run = RunContext(
        run_id="run-1",
        repo="contractorr/stewardme",
        branch="main",
        trigger=Trigger.SCHEDULE,
        started_at=datetime(2026, 3, 30, tzinfo=UTC),
        config_hash="abc123",
    )
    product = ProductContext(
        vision="Improve activation.",
        strategic_priorities=["onboarding"],
    )
    existing_issues = ExistingIssuesAgentOutput(
        agent=AgentName.EXISTING_ISSUES,
        status=AgentStatus.SUCCESS,
        started_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 3, 30, 10, 1, tzinfo=UTC),
        open_issues=[],
        recent_closed_issues=[],
        open_prs=[],
    )
    synthesis = SynthesisInput(
        run=run,
        product=product,
        memory_digest="No strong priors yet.",
        existing_issues=existing_issues,
    )
    assert synthesis.research is None
    assert synthesis.product.vision == "Improve activation."
