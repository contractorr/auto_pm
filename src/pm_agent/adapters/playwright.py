"""Playwright-backed browser runner for dogfooding journeys."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pm_agent.config.models import AuthStrategy, JourneyConfig, JourneyStepConfig
from pm_agent.models.contracts import JourneyRun, JourneyStepResult


class BrowserAdapterError(RuntimeError):
    """Raised when browser automation fails."""


@dataclass
class BrowserRunRequest:
    auth_strategy: AuthStrategy
    journeys: list[JourneyConfig]
    base_url: str
    artifact_root: Path


class PlaywrightBrowserRunner:
    """Execute configured journeys with Playwright."""

    def run(self, request: BrowserRunRequest) -> list[JourneyRun]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserAdapterError(
                "playwright is not installed; run `python -m playwright install chromium` after installing deps"
            ) from exc

        request.artifact_root.mkdir(parents=True, exist_ok=True)
        journeys: list[JourneyRun] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    for journey in request.journeys:
                        context = browser.new_context()
                        page = context.new_page()
                        console_errors: list[str] = []
                        network_failures: list[str] = []
                        page.on(
                            "console",
                            lambda message: (
                                console_errors.append(message.text)
                                if message.type == "error"
                                else None
                            ),
                        )
                        page.on(
                            "requestfailed",
                            lambda req: network_failures.append(
                                f"{req.method} {req.url} {req.failure.error_text if req.failure else ''}".strip()
                            ),
                        )
                        try:
                            journeys.append(
                                self._run_journey(
                                    page=page,
                                    journey=journey,
                                    request=request,
                                    console_errors=console_errors,
                                    network_failures=network_failures,
                                )
                            )
                        finally:
                            context.close()
                finally:
                    browser.close()
        except PlaywrightError as exc:
            raise BrowserAdapterError(str(exc)) from exc

        return journeys

    def _run_journey(
        self,
        *,
        page: Any,
        journey: JourneyConfig,
        request: BrowserRunRequest,
        console_errors: list[str],
        network_failures: list[str],
    ) -> JourneyRun:
        from datetime import UTC, datetime

        started_at = datetime.now(UTC)
        results: list[JourneyStepResult] = []
        page.goto(_join_url(request.base_url, journey.start_path), wait_until="domcontentloaded")

        for index, step in enumerate(journey.steps, start=1):
            step_console_start = len(console_errors)
            step_network_start = len(network_failures)
            heuristic_notes: list[str] = []
            success = True
            action_error: str | None = None

            try:
                self._perform_step(page, step, request.auth_strategy)
                if step.expect_url:
                    page.wait_for_url(f"**{step.expect_url}", timeout=step.timeout_ms)
                if step.wait_for:
                    page.locator(step.wait_for).first.wait_for(
                        state="visible", timeout=step.timeout_ms
                    )
                heuristic_notes.extend(self._heuristic_notes(page))
            except Exception as exc:  # noqa: BLE001
                success = False
                action_error = str(exc)
                heuristic_notes.append(f"step_failed: {exc}")

            screenshot_path = request.artifact_root / journey.id / f"{index:02d}-{step.id}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)

            accessibility_snapshot = page.accessibility.snapshot()
            acc_path = request.artifact_root / journey.id / f"{index:02d}-{step.id}-a11y.json"
            acc_path.write_text(
                json.dumps(accessibility_snapshot or {}, indent=2),
                encoding="utf-8",
            )

            step_console_errors = console_errors[step_console_start:]
            step_network_errors = network_failures[step_network_start:]
            if action_error and action_error not in step_console_errors:
                step_console_errors = [*step_console_errors, action_error]

            results.append(
                JourneyStepResult(
                    step_id=step.id,
                    action=step.action,
                    url=page.url,
                    success=success,
                    console_errors=step_console_errors,
                    network_errors=step_network_errors,
                    screenshot_path=str(screenshot_path),
                    accessibility_snapshot_path=str(acc_path),
                    vision_notes=heuristic_notes,
                )
            )

        ended_at = datetime.now(UTC)
        return JourneyRun(
            journey_id=journey.id,
            persona=journey.persona,
            success=all(result.success for result in results),
            started_at=started_at,
            ended_at=ended_at,
            steps=results,
        )

    def _perform_step(self, page: Any, step: JourneyStepConfig, auth_strategy: AuthStrategy) -> None:
        timeout = step.timeout_ms
        if step.action == "goto":
            if not step.target:
                raise BrowserAdapterError("goto step requires target")
            page.goto(_join_url(page.url, step.target), wait_until="domcontentloaded", timeout=timeout)
            return

        if step.action == "click":
            if not step.selector:
                raise BrowserAdapterError("click step requires selector")
            page.locator(step.selector).first.click(timeout=timeout)
            return

        if step.action == "fill":
            if not step.selector:
                raise BrowserAdapterError("fill step requires selector")
            page.locator(step.selector).first.fill(step.value or "", timeout=timeout)
            return

        if step.action == "sign_in_test_user":
            if auth_strategy != AuthStrategy.TEST_AUTH:
                raise BrowserAdapterError("sign_in_test_user requires test_auth strategy")
            username = step.target or "test"
            page.locator("#test-username").select_option(username, timeout=timeout)
            page.locator("#test-password").fill("test", timeout=timeout)
            page.get_by_role(
                "button",
                name=re.compile(rf"sign in as {re.escape(username)}", re.I),
            ).click(timeout=timeout)
            return

        raise BrowserAdapterError(f"unsupported journey action: {step.action}")

    def _heuristic_notes(self, page: Any) -> list[str]:
        notes: list[str] = []
        heading_count = page.locator("h1").count()
        button_count = page.locator("button").count()
        if heading_count == 0:
            notes.append("No visible h1 detected after step.")
        if button_count == 0:
            notes.append("No buttons detected after step.")
        return notes


def _join_url(base_or_current: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = base_or_current.rstrip("/")
    if path.startswith("/"):
        match = re.match(r"^(https?://[^/]+)", base)
        if match:
            return f"{match.group(1)}{path}"
    return f"{base}/{path.lstrip('/')}"
