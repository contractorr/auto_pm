from datetime import UTC, datetime

from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import IssuePolicyConfig
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    ExistingIssuesAgentOutput,
    ProductContext,
    ResearchAgentOutput,
    RunContext,
    SynthesisInput,
    Trigger,
)
from pm_agent.synthesis.engine import SynthesisEngine
from pm_agent.synthesis.enhancer import ClusterReviewResponse


def _run_context() -> RunContext:
    return RunContext(
        run_id="run-001",
        repo="contractorr/stewardme",
        branch="main",
        trigger=Trigger.SCHEDULE,
        started_at=datetime(2026, 3, 30, tzinfo=UTC),
        config_hash="cfg-1",
    )


def _empty_existing_issues() -> ExistingIssuesAgentOutput:
    return ExistingIssuesAgentOutput(
        agent=AgentName.EXISTING_ISSUES,
        status=AgentStatus.SUCCESS,
        started_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 3, 30, 10, 1, tzinfo=UTC),
        open_issues=[],
        recent_closed_issues=[],
        open_prs=[],
    )


def test_engine_creates_issue_for_high_signal_cluster():
    research = ResearchAgentOutput.model_validate(
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
                    "title": "Onboarding does not explain next step",
                    "problem_statement": "New users are not told what to do immediately after login.",
                    "user_impact": "Activation suffers because users do not see early value.",
                    "affected_surfaces": ["login", "home"],
                    "severity": "high",
                    "raw_confidence": 0.9,
                    "novelty_key": "onboarding-guidance-gap",
                    "dedup_keys": ["onboarding-guidance-gap"],
                    "tags": ["onboarding", "activation"],
                    "evidence": [
                        {
                            "summary": "Competitor messaging is more concrete about first-session value.",
                            "source_refs": [
                                {
                                    "source_type": "competitor_page",
                                    "source_id": "notion-ai",
                                }
                            ],
                        }
                    ],
                }
            ],
            "competitors": [],
            "papers": [],
        }
    )
    synthesis_input = SynthesisInput(
        run=_run_context(),
        product=ProductContext(
            vision="Improve activation.",
            strategic_priorities=["Improve onboarding clarity"],
        ),
        memory_digest="none",
        research=research,
        existing_issues=_empty_existing_issues(),
    )

    report = SynthesisEngine().run(synthesis_input, IssuePolicyConfig())

    assert len(report.clusters) == 1
    assert len(report.proposals) == 1
    assert report.proposals[0].dedup.action.value == "create"
    assert "cluster_id=" in report.proposals[0].issue_body_markdown


def test_engine_updates_existing_issue_when_match_found():
    research = ResearchAgentOutput.model_validate(
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
                    "title": "Onboarding guidance gap",
                    "problem_statement": "The onboarding guidance gap is hurting activation.",
                    "user_impact": "Users fail to reach value quickly.",
                    "severity": "medium",
                    "raw_confidence": 0.8,
                    "novelty_key": "onboarding-guidance-gap",
                    "dedup_keys": ["onboarding-guidance-gap"],
                    "tags": ["onboarding"],
                }
            ],
            "competitors": [],
            "papers": [],
        }
    )
    existing_issues = ExistingIssuesAgentOutput(
        agent=AgentName.EXISTING_ISSUES,
        status=AgentStatus.SUCCESS,
        started_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 3, 30, 10, 1, tzinfo=UTC),
        open_issues=[
            {
                "number": 42,
                "title": "Onboarding guidance gap",
                "state": "open",
                "body_summary": "Users do not know what to do first.",
                "labels": ["onboarding"],
            }
        ],
        recent_closed_issues=[],
        open_prs=[],
    )
    synthesis_input = SynthesisInput(
        run=_run_context(),
        product=ProductContext(vision="Improve activation."),
        memory_digest="none",
        research=research,
        existing_issues=existing_issues,
    )

    report = SynthesisEngine().run(synthesis_input, IssuePolicyConfig())

    assert len(report.proposals) == 1
    assert report.proposals[0].dedup.action.value == "update_existing"
    assert report.proposals[0].dedup.matched_issue_number == 42


class FakeEnhancer:
    cluster_review_enabled = True
    issue_writer_enabled = True
    is_configured = True

    def review_cluster(self, **kwargs):
        return ClusterReviewResponse(
            action="create",
            title="Sharper onboarding issue title",
            summary="Refined summary from model review.",
            user_problem="Refined user problem from model review.",
            evidence_summary="Refined evidence summary.",
            labels=["llm-reviewed"],
        )

    def write_issue(self, **kwargs):
        return "## Summary\nModel-authored issue body\n<!-- pm-agent: cluster_id=test -->"


class SuppressingEnhancer(FakeEnhancer):
    def review_cluster(self, **kwargs):
        return ClusterReviewResponse(
            action="noop",
            title="Suppressed",
            summary="Suppressed",
            user_problem="Suppressed",
            evidence_summary="Suppressed",
            labels=[],
            suppression_reason="llm_rejected",
        )


def test_engine_uses_model_review_and_issue_writer_when_available():
    research = ResearchAgentOutput.model_validate(
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
                    "title": "Onboarding does not explain next step",
                    "problem_statement": "New users are not told what to do immediately after login.",
                    "user_impact": "Activation suffers because users do not see early value.",
                    "severity": "high",
                    "raw_confidence": 0.9,
                    "novelty_key": "onboarding-guidance-gap",
                    "dedup_keys": ["onboarding-guidance-gap"],
                    "tags": ["onboarding"],
                }
            ],
            "competitors": [],
            "papers": [],
        }
    )
    synthesis_input = SynthesisInput(
        run=_run_context(),
        product=ProductContext(
            vision="Improve activation.",
            strategic_priorities=["Improve onboarding clarity"],
        ),
        memory_digest="none",
        research=research,
        existing_issues=_empty_existing_issues(),
    )

    report = SynthesisEngine(enhancer=FakeEnhancer()).run(
        synthesis_input,
        IssuePolicyConfig(),
    )

    assert report.proposals[0].title == "Sharper onboarding issue title"
    assert report.proposals[0].summary == "Refined summary from model review."
    assert "llm-reviewed" in report.proposals[0].labels
    assert report.proposals[0].issue_body_markdown == "## Summary\nModel-authored issue body\n<!-- pm-agent: cluster_id=test -->"


def test_engine_respects_model_suppression_for_unmatched_cluster():
    research = ResearchAgentOutput.model_validate(
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
                    "title": "Onboarding does not explain next step",
                    "problem_statement": "New users are not told what to do immediately after login.",
                    "user_impact": "Activation suffers because users do not see early value.",
                    "severity": "high",
                    "raw_confidence": 0.9,
                    "novelty_key": "onboarding-guidance-gap",
                    "dedup_keys": ["onboarding-guidance-gap"],
                }
            ],
            "competitors": [],
            "papers": [],
        }
    )
    synthesis_input = SynthesisInput(
        run=_run_context(),
        product=ProductContext(vision="Improve activation."),
        memory_digest="none",
        research=research,
        existing_issues=_empty_existing_issues(),
    )

    report = SynthesisEngine(enhancer=SuppressingEnhancer()).run(
        synthesis_input,
        IssuePolicyConfig(),
    )

    assert report.proposals == []
    assert report.suppressed[0].reason == "llm_rejected"


def test_engine_emits_warning_when_anthropic_enabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = load_pm_config("pm-config.example.yml")
    config.anthropic.enabled = True
    synthesis_input = SynthesisInput(
        run=_run_context(),
        product=ProductContext(vision="Improve activation."),
        memory_digest="none",
        research=ResearchAgentOutput.model_validate(
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
                        "title": "Onboarding does not explain next step",
                        "problem_statement": "New users are not told what to do immediately after login.",
                        "user_impact": "Activation suffers because users do not see early value.",
                        "severity": "high",
                        "raw_confidence": 0.9,
                        "novelty_key": "onboarding-guidance-gap",
                        "dedup_keys": ["onboarding-guidance-gap"],
                    }
                ],
                "competitors": [],
                "papers": [],
            }
        ),
        existing_issues=_empty_existing_issues(),
    )

    report = SynthesisEngine.from_config(config).run(synthesis_input, IssuePolicyConfig())

    assert report.proposals
    assert report.warnings == ["anthropic_synthesis_disabled: ANTHROPIC_API_KEY is not set"]
