"""Helpers for run artifact indexing and report persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pm_agent.models.contracts import AgentEnvelope, AgentName, AgentStatus, DogfoodingAgentOutput
from pm_agent.models.runtime import (
    ArtifactRecord,
    DryRunReport,
    RunEvent,
    SynthesisReport,
    WritebackReport,
)


def collect_artifacts(agent_outputs: Iterable[AgentEnvelope]) -> list[ArtifactRecord]:
    artifacts: list[ArtifactRecord] = []
    for output in agent_outputs:
        if not isinstance(output, DogfoodingAgentOutput):
            continue
        for journey in output.journeys:
            for step in journey.steps:
                if step.screenshot_path:
                    artifacts.append(
                        ArtifactRecord(
                            kind="screenshot",
                            path=step.screenshot_path,
                            agent=AgentName.DOGFOODING,
                            journey_id=journey.journey_id,
                            step_id=step.step_id,
                        )
                    )
                if step.accessibility_snapshot_path:
                    artifacts.append(
                        ArtifactRecord(
                            kind="accessibility_snapshot",
                            path=step.accessibility_snapshot_path,
                            agent=AgentName.DOGFOODING,
                            journey_id=journey.journey_id,
                            step_id=step.step_id,
                        )
                    )
    return artifacts


def build_agent_events(agent_outputs: Iterable[AgentEnvelope]) -> list[RunEvent]:
    events: list[RunEvent] = []
    for output in agent_outputs:
        events.append(
            RunEvent(
                timestamp=output.ended_at,
                code=f"agent_{output.status.value}",
                message=(
                    f"{output.agent.value} completed with status {output.status.value}; "
                    f"findings={len(output.findings)} warnings={len(output.warnings)}"
                ),
                level=_status_level(output.status),
                agent=output.agent,
            )
        )
        for warning in output.warnings:
            events.append(
                RunEvent(
                    timestamp=output.ended_at,
                    code=warning.code,
                    message=warning.message,
                    level="error" if warning.fatal else "warning",
                    agent=output.agent,
                )
            )
    return events


def build_synthesis_events(synthesis: SynthesisReport, *, timestamp: datetime) -> list[RunEvent]:
    events = [
        RunEvent(
            timestamp=timestamp,
            code="synthesis_completed",
            message=(
                "synthesis completed; "
                f"proposals={len(synthesis.proposals)} suppressed={len(synthesis.suppressed)}"
            ),
            level="info",
            agent=AgentName.SYNTHESIS,
        )
    ]
    events.extend(
        RunEvent(
            timestamp=timestamp,
            code="synthesis_warning",
            message=warning,
            level="warning",
            agent=AgentName.SYNTHESIS,
        )
        for warning in synthesis.warnings
    )
    return events


def persist_run_report(
    repo_root: str | Path,
    report: DryRunReport,
    *,
    writeback: WritebackReport | None = None,
) -> Path:
    root = Path(repo_root)
    artifact_root = root / ".pm-agent-artifacts" / report.run.run_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    if writeback is not None:
        payload["writeback"] = writeback.model_dump(mode="json")

    serialized = json.dumps(payload, indent=2)
    report_path = artifact_root / "run-report.json"
    report_path.write_text(serialized, encoding="utf-8")
    (root / ".pm-agent-run.json").write_text(serialized, encoding="utf-8")
    return report_path


def _status_level(status: AgentStatus) -> str:
    if status == AgentStatus.FAILED:
        return "error"
    if status == AgentStatus.PARTIAL:
        return "warning"
    return "info"
