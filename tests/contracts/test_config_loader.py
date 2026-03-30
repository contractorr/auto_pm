from pathlib import Path

import pytest

from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import AuthStrategy, GitHubWriteMode, RuntimeMode


def test_example_config_parses():
    config = load_pm_config(Path("pm-config.example.yml"))
    assert config.repo.full_name == "contractorr/stewardme"
    assert config.runtime.mode == RuntimeMode.DOCKER_COMPOSE
    assert config.dogfooding.auth_strategy == AuthStrategy.TEST_AUTH
    assert config.anthropic.enabled is False
    assert config.anthropic.model == "claude-3-7-sonnet-latest"
    assert config.anthropic.research_review_enabled is True
    assert config.anthropic.codebase_review_enabled is True
    assert config.anthropic.portfolio_review_enabled is True
    assert config.github.write_mode == GitHubWriteMode.DISABLED
    assert len(config.dogfooding.journeys) == 1


def test_credentials_auth_requires_credentials_block(tmp_path: Path):
    config_path = tmp_path / "pm-config.yml"
    config_path.write_text(
        """
repo:
  full_name: example/app
dogfooding:
  auth_strategy: credentials
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="dogfooding.credentials"):
        load_pm_config(config_path)


def test_credentials_auth_config_parses_env_backed_totp(tmp_path: Path):
    config_path = tmp_path / "pm-config.yml"
    config_path.write_text(
        """
repo:
  full_name: example/app
runtime:
  mode: external_url
  service_urls:
    - https://dogfood.example.com
dogfooding:
  auth_strategy: credentials
  credentials:
    username:
      env: DOGFOOD_USERNAME
    password:
      env: DOGFOOD_PASSWORD
    totp:
      secret:
        env: DOGFOOD_TOTP_SECRET
  journeys: []
""".strip(),
        encoding="utf-8",
    )

    config = load_pm_config(config_path)

    assert config.runtime.mode == RuntimeMode.EXTERNAL_URL
    assert config.dogfooding.auth_strategy == AuthStrategy.CREDENTIALS
    assert config.dogfooding.credentials is not None
    assert config.dogfooding.credentials.username.env == "DOGFOOD_USERNAME"
    assert config.dogfooding.credentials.totp is not None
    assert config.dogfooding.credentials.totp.secret.env == "DOGFOOD_TOTP_SECRET"
