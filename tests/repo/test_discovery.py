from pathlib import Path

from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import (
    AuthStrategy,
    CredentialsAuthConfig,
    RuntimeMode,
    SecretValueConfig,
    TotpConfig,
)
from pm_agent.repo.discovery import discover_repo_capabilities


def test_discovery_detects_compose_playwright_and_test_auth(tmp_path: Path):
    config = load_pm_config(Path("pm-config.example.yml"))
    (tmp_path / "PRODUCT.md").write_text("# Product Vision\n\nTest vision", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "web" / "e2e").mkdir(parents=True)
    (tmp_path / "web" / "src" / "lib").mkdir(parents=True)
    (tmp_path / "web" / "e2e" / "playwright.config.ts").write_text("export default {}", encoding="utf-8")
    (tmp_path / "web" / "src" / "lib" / "auth.ts").write_text(
        "const flag = process.env.ENABLE_TEST_AUTH === 'true';",
        encoding="utf-8",
    )

    snapshot = discover_repo_capabilities(tmp_path, config)

    assert snapshot.product_file_exists is True
    assert snapshot.docker_compose_ready is True
    assert snapshot.playwright_config == "web/e2e/playwright.config.ts"
    assert snapshot.test_auth_supported is True
    assert snapshot.github_actions_present is True
    assert snapshot.dogfooding_ready is True


def test_discovery_allows_remote_credentials_without_local_playwright_config(tmp_path: Path):
    config = load_pm_config(Path("pm-config.example.yml"))
    config.runtime.mode = RuntimeMode.EXTERNAL_URL
    config.runtime.compose_file = None
    config.runtime.start_commands = []
    config.runtime.service_urls = ["https://dogfood.example.com"]
    config.runtime.healthcheck_urls = []
    config.dogfooding.auth_strategy = AuthStrategy.CREDENTIALS
    config.dogfooding.credentials = CredentialsAuthConfig(
        username=SecretValueConfig(value="dogfood@example.com"),
        password=SecretValueConfig(value="super-secret"),
        totp=TotpConfig(secret=SecretValueConfig(value="JBSWY3DPEHPK3PXP")),
    )
    (tmp_path / "PRODUCT.md").write_text("# Product Vision\n\nRemote dogfooding", encoding="utf-8")

    snapshot = discover_repo_capabilities(tmp_path, config)

    assert snapshot.playwright_config is None
    assert snapshot.dogfooding_ready is True
    assert all("Playwright config" not in note for note in snapshot.notes)
