import json
from datetime import UTC, datetime
from pathlib import Path

from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    DogfoodingAgentOutput,
    JourneyRun,
    JourneyStepResult,
    ProductContext,
    RunContext,
    Trigger,
)
from pm_agent.models.runtime import (
    CapabilitySnapshot,
    DryRunReport,
    SynthesisReport,
    WritebackReport,
)
from pm_agent.orchestration.artifacts import (
    build_agent_events,
    build_synthesis_events,
    collect_artifacts,
    persist_run_report,
)


def _dogfooding_output() -> DogfoodingAgentOutput:
    now = datetime(2026, 3, 30, tzinfo=UTC)
    return DogfoodingAgentOutput(
        agent=AgentName.DOGFOODING,
        status=AgentStatus.PARTIAL,
        started_at=now,
        ended_at=now,
        warnings=[{"code": "dogfooding_failed", "message": "browser crashed"}],
        findings=[],
        runtime_mode="external_url",
        base_url="https://example.com",
        journeys=[
            JourneyRun(
                journey_id="signup",
                persona="guest",
                success=False,
                started_at=now,
                ended_at=now,
                steps=[
                    JourneyStepResult(
                        step_id="start",
                        action="visit",
                        url="https://example.com/signup",
                        success=False,
                        screenshot_path=".pm-agent-artifacts/run-1/dogfooding/signup/start.png",
                        accessibility_snapshot_path=".pm-agent-artifacts/run-1/dogfooding/signup/start.a11y.json",
                    )
                ],
            )
        ],
    )


def test_collect_artifacts_and_events_from_dogfooding_output():
    output = _dogfooding_output()

    artifacts = collect_artifacts([output])
    events = build_agent_events([output])
    synthesis_events = build_synthesis_events(
        SynthesisReport(warnings=["model fallback used"]),
        timestamp=output.ended_at,
    )

    assert [artifact.kind for artifact in artifacts] == [
        "screenshot",
        "accessibility_snapshot",
    ]
    assert events[0].code == "agent_partial"
    assert events[1].code == "dogfooding_failed"
    assert synthesis_events[0].code == "synthesis_completed"
    assert synthesis_events[1].code == "synthesis_warning"


def test_collect_artifacts_ignores_skipped_sensitive_steps():
    now = datetime(2026, 3, 30, tzinfo=UTC)
    output = DogfoodingAgentOutput(
        agent=AgentName.DOGFOODING,
        status=AgentStatus.SUCCESS,
        started_at=now,
        ended_at=now,
        findings=[],
        runtime_mode="external_url",
        journeys=[
            JourneyRun(
                journey_id="login",
                persona="member",
                success=True,
                started_at=now,
                ended_at=now,
                steps=[
                    JourneyStepResult(
                        step_id="fill-password",
                        action="fill",
                        success=True,
                        artifacts_skipped=True,
                    )
                ],
            )
        ],
    )

    assert collect_artifacts([output]) == []


def test_persist_run_report_writes_latest_and_artifact_copy(tmp_path: Path):
    now = datetime(2026, 3, 30, tzinfo=UTC)
    report = DryRunReport(
        run=RunContext(
            run_id="run-123",
            repo="contractorr/stewardme",
            branch="main",
            commit_sha="abc123",
            trigger=Trigger.SCHEDULE,
            started_at=now,
            config_hash="hash",
        ),
        product=ProductContext(vision="Test product"),
        capabilities=CapabilitySnapshot(
            repo_root=str(tmp_path),
            runtime_mode="external_url",
            product_file="PRODUCT.md",
            product_file_exists=True,
        ),
        agent_outputs=[_dogfooding_output()],
        synthesis=SynthesisReport(),
        artifacts=collect_artifacts([_dogfooding_output()]),
        events=build_agent_events([_dogfooding_output()]),
    )

    report_path = persist_run_report(tmp_path, report, writeback=WritebackReport(mode="disabled"))

    latest_path = tmp_path / ".pm-agent-run.json"
    assert report_path == tmp_path / ".pm-agent-artifacts" / "run-123" / "run-report.json"
    assert latest_path.exists()
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["run"]["run_id"] == "run-123"
    assert payload["writeback"]["mode"] == "disabled"
