"""Playwright-backed browser runner for dogfooding journeys."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pm_agent.config.models import (
    AuthStrategy,
    CredentialsAuthConfig,
    JourneyConfig,
    JourneyStepConfig,
)
from pm_agent.models.contracts import JourneyRun, JourneyStepResult

_CREDENTIAL_PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*credentials\.(username|password|totp_code)\s*\}\}"
)


class BrowserAdapterError(RuntimeError):
    """Raised when browser automation fails."""


@dataclass
class BrowserRunRequest:
    auth_strategy: AuthStrategy
    journeys: list[JourneyConfig]
    base_url: str
    artifact_root: Path
    credentials: CredentialsAuthConfig | None = None


@dataclass(frozen=True)
class ResolvedTotpConfig:
    secret: str
    digits: int
    period_seconds: int
    algorithm: str


@dataclass(frozen=True)
class ResolvedCredentials:
    username: str
    password: str
    totp: ResolvedTotpConfig | None = None


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
        credentials = _resolve_credentials(request)

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
                                    credentials=credentials,
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
        credentials: ResolvedCredentials | None,
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
                self._perform_step(page, step, request.auth_strategy, credentials)
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

    def _perform_step(
        self,
        page: Any,
        step: JourneyStepConfig,
        auth_strategy: AuthStrategy,
        credentials: ResolvedCredentials | None,
    ) -> None:
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
            value = _resolve_step_value(
                step.value or "",
                auth_strategy=auth_strategy,
                credentials=credentials,
            )
            page.locator(step.selector).first.fill(value, timeout=timeout)
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


def _resolve_credentials(request: BrowserRunRequest) -> ResolvedCredentials | None:
    if request.auth_strategy != AuthStrategy.CREDENTIALS:
        return None
    if request.credentials is None:
        raise BrowserAdapterError("credentials auth requires dogfooding.credentials")

    try:
        username = request.credentials.username.resolve("dogfooding.credentials.username")
        password = request.credentials.password.resolve("dogfooding.credentials.password")
        resolved_totp = None
        if request.credentials.totp is not None:
            resolved_totp = ResolvedTotpConfig(
                secret=request.credentials.totp.secret.resolve("dogfooding.credentials.totp.secret"),
                digits=request.credentials.totp.digits,
                period_seconds=request.credentials.totp.period_seconds,
                algorithm=request.credentials.totp.algorithm,
            )
    except ValueError as exc:
        raise BrowserAdapterError(str(exc)) from exc

    return ResolvedCredentials(username=username, password=password, totp=resolved_totp)


def _resolve_step_value(
    value: str,
    *,
    auth_strategy: AuthStrategy,
    credentials: ResolvedCredentials | None,
) -> str:
    if "{{" not in value:
        return value

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if auth_strategy != AuthStrategy.CREDENTIALS or credentials is None:
            raise BrowserAdapterError(
                f"placeholder {match.group(0)} requires auth_strategy=credentials"
            )
        if token == "username":
            return credentials.username
        if token == "password":
            return credentials.password
        if token == "totp_code":
            if credentials.totp is None:
                raise BrowserAdapterError(
                    "placeholder {{ credentials.totp_code }} requires dogfooding.credentials.totp"
                )
            return _generate_totp(credentials.totp)
        raise BrowserAdapterError(f"unsupported credentials placeholder: {token}")

    return _CREDENTIAL_PLACEHOLDER_PATTERN.sub(replace, value)


def _generate_totp(config: ResolvedTotpConfig, for_time: int | None = None) -> str:
    counter = int((time.time() if for_time is None else for_time) // config.period_seconds)
    counter_bytes = counter.to_bytes(8, byteorder="big")
    digestmod = getattr(hashlib, config.algorithm.lower(), None)
    if digestmod is None:
        raise BrowserAdapterError(f"unsupported TOTP algorithm: {config.algorithm}")
    digest = hmac.new(_decode_base32_secret(config.secret), counter_bytes, digestmod).digest()
    offset = digest[-1] & 0x0F
    code_int = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
    code = code_int % (10 ** config.digits)
    return str(code).zfill(config.digits)


def _decode_base32_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padded = normalized + ("=" * (-len(normalized) % 8))
    try:
        return base64.b32decode(padded, casefold=True)
    except binascii.Error as exc:
        raise BrowserAdapterError("invalid TOTP secret; expected a base32-encoded value") from exc
