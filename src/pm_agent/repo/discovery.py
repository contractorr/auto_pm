"""Discover local repository capabilities needed by the PM agent."""

from __future__ import annotations

from pathlib import Path

from pm_agent.config.models import AuthStrategy, PMConfig, RuntimeMode
from pm_agent.models.runtime import CapabilitySnapshot

PLAYWRIGHT_CANDIDATES = (
    Path("playwright.config.ts"),
    Path("playwright.config.js"),
    Path("web/e2e/playwright.config.ts"),
    Path("web/e2e/playwright.config.js"),
    Path("web/playwright.config.ts"),
    Path("web/playwright.config.js"),
)

TEST_AUTH_CANDIDATES = (
    Path("web/src/lib/auth.ts"),
    Path("web/src/app/login/page.tsx"),
    Path("src/web/auth.py"),
)


def _first_existing(root: Path, candidates: tuple[Path, ...] | list[Path]) -> Path | None:
    for candidate in candidates:
        full_path = root / candidate
        if full_path.exists():
            return full_path
    return None


def _file_contains(path: Path | None, text: str) -> bool:
    if path is None or not path.exists() or not path.is_file():
        return False
    return text in path.read_text(encoding="utf-8", errors="ignore")


def _credentials_ready(config: PMConfig, notes: list[str]) -> bool:
    credentials = config.dogfooding.credentials
    if credentials is None:
        notes.append("credentials auth requested but no dogfooding.credentials block was configured")
        return False

    missing = credentials.missing_fields()
    if missing:
        notes.append(
            "credentials auth requested but required values are unavailable: "
            + ", ".join(missing)
        )
        return False
    return True


def discover_repo_capabilities(repo_root: str | Path, config: PMConfig) -> CapabilitySnapshot:
    root = Path(repo_root)
    notes: list[str] = []

    product_file = root / config.repo.product_file
    if not product_file.exists():
        notes.append(f"missing product file: {config.repo.product_file}")

    compose_file = (root / config.runtime.compose_file) if config.runtime.compose_file else None
    docker_ready = (
        config.runtime.mode == RuntimeMode.DOCKER_COMPOSE
        and compose_file is not None
        and compose_file.exists()
    )
    if config.runtime.mode == RuntimeMode.DOCKER_COMPOSE and not docker_ready:
        notes.append("runtime mode is docker_compose but compose file is missing")

    url_runtime = config.runtime.mode in {RuntimeMode.PREVIEW_URL, RuntimeMode.EXTERNAL_URL}
    playwright_path = _first_existing(root, PLAYWRIGHT_CANDIDATES)
    if config.dogfooding.enabled and playwright_path is None and not url_runtime:
        notes.append("dogfooding enabled but no Playwright config was discovered")

    test_auth_supported = any(_file_contains(root / path, "ENABLE_TEST_AUTH") for path in TEST_AUTH_CANDIDATES)
    if config.dogfooding.auth_strategy == AuthStrategy.TEST_AUTH and not test_auth_supported:
        notes.append("test auth requested but no ENABLE_TEST_AUTH hook was discovered")

    if config.runtime.mode in {RuntimeMode.PREVIEW_URL, RuntimeMode.EXTERNAL_URL} and not config.runtime.service_urls:
        notes.append("URL-based runtime selected but no service_urls were configured")

    if config.dogfooding.auth_strategy == AuthStrategy.TEST_AUTH:
        auth_ready = test_auth_supported
    elif config.dogfooding.auth_strategy == AuthStrategy.CREDENTIALS:
        auth_ready = _credentials_ready(config, notes)
    else:
        auth_ready = config.dogfooding.auth_strategy in {
            AuthStrategy.NONE,
            AuthStrategy.STORAGE_STATE,
            AuthStrategy.SETUP_SCRIPT,
            AuthStrategy.MANUAL_DISABLED,
        }
    runtime_ready = docker_ready or (
        config.runtime.mode in {RuntimeMode.PREVIEW_URL, RuntimeMode.EXTERNAL_URL}
        and bool(config.runtime.service_urls)
    ) or (config.runtime.mode == RuntimeMode.COMMANDS and bool(config.runtime.start_commands))

    browser_ready = bool(playwright_path) or url_runtime
    dogfooding_ready = bool(config.dogfooding.enabled and runtime_ready and browser_ready and auth_ready)

    return CapabilitySnapshot(
        repo_root=str(root.resolve()),
        runtime_mode=config.runtime.mode.value,
        product_file=str(config.repo.product_file),
        product_file_exists=product_file.exists(),
        compose_file=str(config.runtime.compose_file) if config.runtime.compose_file else None,
        docker_compose_ready=docker_ready,
        playwright_config=(
            playwright_path.relative_to(root).as_posix() if playwright_path else None
        ),
        test_auth_supported=test_auth_supported,
        github_actions_present=(root / ".github" / "workflows").exists(),
        dogfooding_ready=dogfooding_ready,
        notes=notes,
    )
