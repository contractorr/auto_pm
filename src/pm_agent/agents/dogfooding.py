"""Dogfooding agent backed by runtime and browser adapters."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pm_agent.adapters.playwright import (
    BrowserAdapterError,
    BrowserRunRequest,
    PlaywrightBrowserRunner,
)
from pm_agent.adapters.runtime import LocalRuntimeLauncher, RuntimeAdapterError
from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    AgentWarning,
    DogfoodingAgentOutput,
    Evidence,
    Finding,
    FindingKind,
    JourneyRun,
    Severity,
    SourceRef,
    SourceType,
    Trigger,
)


def _journey_tokens(journey) -> set[str]:
    parts = [journey.id, journey.persona or "", journey.start_path]
    for step in journey.steps:
        parts.extend([step.id, step.action, step.target or "", step.selector or "", step.wait_for or ""])
    return {
        token
        for token in re.findall(r"[a-z0-9]+", " ".join(parts).lower())
        if len(token) >= 3
    }


def _changed_file_tokens(changed_files: list[str]) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", " ".join(changed_files).lower())
        if len(token) >= 3
    }


def _journeys_for_context(context: AgentExecutionContext):
    journeys = context.config.dogfooding.journeys
    if context.run.trigger != Trigger.PUSH or len(journeys) <= 1:
        return journeys, None

    changed_tokens = _changed_file_tokens(context.changed_files)
    if not changed_tokens:
        return journeys[:1], "push trigger detected with no changed files; limited to first journey"

    matched = [
        journey
        for journey in journeys
        if _journey_tokens(journey) & changed_tokens
    ]
    if matched:
        return matched[:2], None
    return journeys[:1], "push trigger detected with no matching journey hints; limited to first journey"


class DogfoodingAgent(BaseAgent):
    name = AgentName.DOGFOODING

    def __init__(
        self,
        *,
        runtime_launcher: LocalRuntimeLauncher | None = None,
        browser_runner: PlaywrightBrowserRunner | None = None,
        artifact_dirname: str = ".pm-agent-artifacts",
    ) -> None:
        self._runtime_launcher = runtime_launcher or LocalRuntimeLauncher()
        self._browser_runner = browser_runner or PlaywrightBrowserRunner()
        self._artifact_dirname = artifact_dirname

    def run(self, context: AgentExecutionContext) -> DogfoodingAgentOutput:
        started_at = datetime.now(UTC)
        warnings: list[AgentWarning] = []
        journeys: list[JourneyRun] = []
        findings: list[Finding] = []
        selected_journeys, selection_warning = _journeys_for_context(context)
        if selection_warning is not None:
            warnings.append(AgentWarning(code="dogfooding_downshifted", message=selection_warning))

        if not context.config.dogfooding.enabled:
            return DogfoodingAgentOutput(
                agent=AgentName.DOGFOODING,
                status=AgentStatus.SKIPPED,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                warnings=[AgentWarning(code="dogfooding_disabled", message="dogfooding is disabled")],
                findings=[],
                runtime_mode=context.config.runtime.mode.value,
                base_url=None,
                journeys=[],
            )

        capabilities = context.capabilities
        if capabilities is not None and not capabilities.dogfooding_ready:
            return DogfoodingAgentOutput(
                agent=AgentName.DOGFOODING,
                status=AgentStatus.SKIPPED,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                warnings=[
                    AgentWarning(
                        code="dogfooding_not_ready",
                        message="dogfooding prerequisites are not satisfied",
                    )
                ],
                findings=[],
                runtime_mode=context.config.runtime.mode.value,
                base_url=context.config.runtime.service_urls[0]
                if context.config.runtime.service_urls
                else None,
                journeys=[],
            )

        session = None
        base_url = context.config.runtime.service_urls[0] if context.config.runtime.service_urls else None
        artifact_root = (
            context.repo_root
            / self._artifact_dirname
            / context.run.run_id
            / "dogfooding"
        )
        try:
            session = self._runtime_launcher.launch(context)
            if session.base_url:
                base_url = session.base_url
            if not base_url:
                raise RuntimeAdapterError("no base_url available for dogfooding")
            journeys = self._browser_runner.run(
                BrowserRunRequest(
                    auth_strategy=context.config.dogfooding.auth_strategy,
                    journeys=selected_journeys,
                    base_url=base_url,
                    artifact_root=artifact_root,
                    credentials=context.config.dogfooding.credentials,
                )
            )
            findings = self._journey_findings(context, journeys)
            status = AgentStatus.SUCCESS
            if any(not journey.success for journey in journeys):
                status = AgentStatus.PARTIAL
        except (RuntimeAdapterError, BrowserAdapterError) as exc:
            warnings.append(AgentWarning(code="dogfooding_failed", message=str(exc)))
            status = AgentStatus.PARTIAL
        finally:
            if session is not None:
                session.stop()

        return DogfoodingAgentOutput(
            agent=AgentName.DOGFOODING,
            status=status,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=warnings,
            findings=findings,
            runtime_mode=context.config.runtime.mode.value,
            base_url=base_url,
            journeys=journeys,
        )

    def _journey_findings(
        self,
        context: AgentExecutionContext,
        journeys: list[JourneyRun],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for journey in journeys:
            if not journey.success:
                failing_steps = [step for step in journey.steps if not step.success]
                findings.append(
                    Finding(
                        finding_id=f"{context.run.run_id}-{journey.journey_id}-failed",
                        agent=AgentName.DOGFOODING,
                        kind=FindingKind.RELIABILITY,
                        title=f"Dogfooding journey failed: {journey.journey_id}",
                        problem_statement="A configured user journey could not be completed successfully.",
                        user_impact="Users may be blocked or see broken flows in a core path.",
                        affected_surfaces=sorted({step.url or "" for step in failing_steps if step.url}),
                        affected_personas=[journey.persona] if journey.persona else [],
                        severity=Severity.HIGH,
                        raw_confidence=0.9,
                        novelty_key=f"journey-failed-{journey.journey_id}",
                        dedup_keys=[f"journey-failed-{journey.journey_id}"],
                        tags=["dogfooding", "journey-failure"],
                        evidence=[
                            Evidence(
                                summary=f"Journey {journey.journey_id} had {len(failing_steps)} failing steps.",
                                source_refs=[
                                    SourceRef(
                                        source_type=SourceType.PLAYWRIGHT_STEP,
                                        source_id=step.step_id,
                                        locator=step.url,
                                        artifact_path=step.screenshot_path,
                                    )
                                    for step in failing_steps
                                ],
                                console_errors=[
                                    error for step in failing_steps for error in step.console_errors
                                ],
                                network_errors=[
                                    error for step in failing_steps for error in step.network_errors
                                ],
                                screenshot_paths=[
                                    step.screenshot_path for step in failing_steps if step.screenshot_path
                                ],
                            )
                        ],
                        proposed_direction="Stabilize the journey before enabling autonomous issue lifecycle actions.",
                    )
                )

            for step in journey.steps:
                if step.console_errors or step.network_errors:
                    findings.append(
                        Finding(
                            finding_id=f"{context.run.run_id}-{journey.journey_id}-{step.step_id}-runtime",
                            agent=AgentName.DOGFOODING,
                            kind=FindingKind.RELIABILITY,
                            title=f"Runtime errors during dogfooding step {step.step_id}",
                            problem_statement="Console or network failures occurred during a user journey step.",
                            user_impact="Users may encounter broken UI behavior or incomplete data loading.",
                            affected_surfaces=[step.url] if step.url else [],
                            affected_personas=[journey.persona] if journey.persona else [],
                            severity=Severity.MEDIUM,
                            raw_confidence=0.88,
                            novelty_key=f"runtime-errors-{journey.journey_id}-{step.step_id}",
                            dedup_keys=[f"runtime-errors-{step.step_id}"],
                            tags=["dogfooding", "runtime"],
                            evidence=[
                                Evidence(
                                    summary=f"Step {step.step_id} recorded runtime errors.",
                                    source_refs=[
                                        SourceRef(
                                            source_type=SourceType.PLAYWRIGHT_STEP,
                                            source_id=step.step_id,
                                            locator=step.url,
                                            artifact_path=step.screenshot_path,
                                        )
                                    ],
                                    console_errors=step.console_errors,
                                    network_errors=step.network_errors,
                                    screenshot_paths=[step.screenshot_path] if step.screenshot_path else [],
                                )
                            ],
                            proposed_direction="Inspect the failing browser/network path and stabilize it.",
                        )
                    )

                if any("No visible h1" in note for note in step.vision_notes):
                    findings.append(
                        Finding(
                            finding_id=f"{context.run.run_id}-{journey.journey_id}-{step.step_id}-clarity",
                            agent=AgentName.DOGFOODING,
                            kind=FindingKind.UX_BUG,
                            title=f"Dogfooding step lacks a clear page heading: {step.step_id}",
                            problem_statement="The page did not expose a visible primary heading after the step.",
                            user_impact="Users may struggle to orient themselves within the flow.",
                            affected_surfaces=[step.url] if step.url else [],
                            affected_personas=[journey.persona] if journey.persona else [],
                            severity=Severity.LOW,
                            raw_confidence=0.7,
                            novelty_key=f"missing-heading-{journey.journey_id}-{step.step_id}",
                            dedup_keys=[f"missing-heading-{step.step_id}"],
                            tags=["dogfooding", "ux", "orientation"],
                            evidence=[
                                Evidence(
                                    summary="Heuristic analysis found no visible h1 on the page.",
                                    source_refs=[
                                        SourceRef(
                                            source_type=SourceType.PLAYWRIGHT_STEP,
                                            source_id=step.step_id,
                                            locator=step.url,
                                            artifact_path=step.accessibility_snapshot_path,
                                        )
                                    ],
                                    accessibility_notes=step.vision_notes,
                                    screenshot_paths=[step.screenshot_path] if step.screenshot_path else [],
                                )
                            ],
                            proposed_direction="Ensure each core surface exposes a visible primary heading or equivalent landmark.",
                        )
                    )

        return findings
