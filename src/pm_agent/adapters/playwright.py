"""Playwright-backed browser runner for dogfooding journeys."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pm_agent.config.models import (
    AuthStrategy,
    ArtifactMode,
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
    repo_root: Path
    credentials: CredentialsAuthConfig | None = None
    storage_state: Path | None = None
    setup_script: Path | None = None
    setup_script_timeout_seconds: int = 120


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


@dataclass(frozen=True)
class PreparedAuthState:
    storage_state_path: Path | None = None
    cleanup_paths: tuple[Path, ...] = ()


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
        auth_state = _prepare_auth_state(request, credentials)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    for journey in request.journeys:
                        context_kwargs: dict[str, Any] = {}
                        if auth_state.storage_state_path is not None:
                            context_kwargs["storage_state"] = str(auth_state.storage_state_path)
                        context = browser.new_context(**context_kwargs)
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
        finally:
            _cleanup_auth_state(auth_state)

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
            artifact_mode = _artifact_mode_for_step(step)
            screenshot_path: Path | None = None
            acc_path: Path | None = None

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

            selectors_to_redact = _selectors_to_redact(step, artifact_mode)
            if artifact_mode == ArtifactMode.REDACT and not selectors_to_redact:
                artifact_mode = ArtifactMode.SKIP
                heuristic_notes.append(
                    "Artifacts skipped because no redact selectors were configured for a sensitive step."
                )
            elif selectors_to_redact and not _clear_sensitive_fields(page, selectors_to_redact):
                artifact_mode = ArtifactMode.SKIP
                heuristic_notes.append(
                    "Artifacts skipped because sensitive fields could not be cleared safely."
                )

            if artifact_mode != ArtifactMode.SKIP:
                screenshot_path = request.artifact_root / journey.id / f"{index:02d}-{step.id}.png"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)

                accessibility_snapshot = page.accessibility.snapshot()
                acc_path = request.artifact_root / journey.id / f"{index:02d}-{step.id}-a11y.json"
                acc_path.write_text(
                    json.dumps(accessibility_snapshot or {}, indent=2),
                    encoding="utf-8",
                )

            if artifact_mode == ArtifactMode.REDACT:
                heuristic_notes.append("Artifacts were captured after redacting sensitive fields.")
            elif artifact_mode == ArtifactMode.SKIP:
                heuristic_notes.append("Artifacts were skipped for this sensitive step.")

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
                    screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
                    accessibility_snapshot_path=str(acc_path) if acc_path is not None else None,
                    artifacts_redacted=artifact_mode == ArtifactMode.REDACT,
                    artifacts_skipped=artifact_mode == ArtifactMode.SKIP,
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
    if request.credentials is None:
        if request.auth_strategy == AuthStrategy.CREDENTIALS:
            raise BrowserAdapterError("credentials auth requires dogfooding.credentials")
        return None

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


def _prepare_auth_state(
    request: BrowserRunRequest,
    credentials: ResolvedCredentials | None,
) -> PreparedAuthState:
    if request.auth_strategy == AuthStrategy.MANUAL_DISABLED:
        raise BrowserAdapterError("manual auth is not supported for autonomous dogfooding")

    if request.auth_strategy == AuthStrategy.STORAGE_STATE:
        if request.storage_state is None:
            raise BrowserAdapterError("storage_state auth requires dogfooding.storage_state")
        storage_state_path = _resolve_repo_path(request.repo_root, request.storage_state)
        if not storage_state_path.exists():
            raise BrowserAdapterError(f"storage state file not found: {storage_state_path}")
        return PreparedAuthState(storage_state_path=storage_state_path)

    if request.auth_strategy == AuthStrategy.SETUP_SCRIPT:
        if request.setup_script is None:
            raise BrowserAdapterError("setup_script auth requires dogfooding.setup_script")
        setup_script_path = _resolve_repo_path(request.repo_root, request.setup_script)
        if not setup_script_path.exists():
            raise BrowserAdapterError(f"setup script not found: {setup_script_path}")
        configured_storage_state = (
            _resolve_repo_path(request.repo_root, request.storage_state)
            if request.storage_state is not None
            else None
        )
        storage_state_path = configured_storage_state or request.artifact_root / ".auth-storage-state.json"
        storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        _run_setup_script(
            request=request,
            setup_script_path=setup_script_path,
            storage_state_path=storage_state_path,
            credentials=credentials,
        )
        if not storage_state_path.exists():
            raise BrowserAdapterError(
                f"setup script did not create a storage state file: {storage_state_path}"
            )
        cleanup_paths = () if configured_storage_state is not None else (storage_state_path,)
        return PreparedAuthState(
            storage_state_path=storage_state_path,
            cleanup_paths=cleanup_paths,
        )

    return PreparedAuthState()


def _run_setup_script(
    *,
    request: BrowserRunRequest,
    setup_script_path: Path,
    storage_state_path: Path,
    credentials: ResolvedCredentials | None,
) -> None:
    command = _setup_script_command(setup_script_path)
    env = os.environ.copy()
    env.update(
        {
            "PM_AGENT_BASE_URL": request.base_url,
            "PM_AGENT_STORAGE_STATE_PATH": str(storage_state_path),
            "PM_AGENT_REPO_ROOT": str(request.repo_root),
        }
    )
    if credentials is not None:
        env["PM_AGENT_USERNAME"] = credentials.username
        env["PM_AGENT_PASSWORD"] = credentials.password
        if credentials.totp is not None:
            env["PM_AGENT_TOTP_SECRET"] = credentials.totp.secret
            env["PM_AGENT_TOTP_CODE"] = _generate_totp(credentials.totp)

    try:
        result = subprocess.run(
            command,
            cwd=request.repo_root,
            capture_output=True,
            text=True,
            timeout=request.setup_script_timeout_seconds,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise BrowserAdapterError(
            f"setup script runner is not available for {setup_script_path.name}: {exc.filename}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BrowserAdapterError(
            f"setup script timed out after {request.setup_script_timeout_seconds}s"
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        message = stderr or f"setup script failed with exit code {result.returncode}"
        raise BrowserAdapterError(message)


def _setup_script_command(setup_script_path: Path) -> list[str]:
    suffix = setup_script_path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(setup_script_path)]
    if suffix in {".js", ".mjs", ".cjs"}:
        return ["node", str(setup_script_path)]
    if suffix in {".ts", ".tsx"}:
        return ["npx", "tsx", str(setup_script_path)]
    if suffix == ".ps1":
        return ["powershell", "-File", str(setup_script_path)]
    if suffix == ".sh":
        return ["sh", str(setup_script_path)]
    raise BrowserAdapterError(
        f"unsupported setup script type for {setup_script_path.name}; use .py, .js, .ts, .ps1, or .sh"
    )


def _cleanup_auth_state(auth_state: PreparedAuthState) -> None:
    for path in auth_state.cleanup_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _artifact_mode_for_step(step: JourneyStepConfig) -> ArtifactMode:
    if step.artifact_mode != ArtifactMode.CAPTURE:
        return step.artifact_mode
    if step.value and _CREDENTIAL_PLACEHOLDER_PATTERN.search(step.value):
        return ArtifactMode.REDACT
    return ArtifactMode.CAPTURE


def _selectors_to_redact(step: JourneyStepConfig, artifact_mode: ArtifactMode) -> list[str]:
    selectors = list(step.redact_selectors)
    if artifact_mode in {ArtifactMode.REDACT, ArtifactMode.SKIP} and step.action == "fill" and step.selector:
        selectors.append(step.selector)

    seen: set[str] = set()
    ordered: list[str] = []
    for selector in selectors:
        if selector and selector not in seen:
            seen.add(selector)
            ordered.append(selector)
    return ordered


def _clear_sensitive_fields(page: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            page.locator(selector).first.evaluate(
                """element => {
                    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
                        element.value = '';
                        element.setAttribute('value', '');
                        return;
                    }
                    element.textContent = '';
                }"""
            )
        except Exception:  # noqa: BLE001
            return False
    return True


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
