from pathlib import Path

import pytest

from pm_agent.adapters.playwright import (
    BrowserAdapterError,
    BrowserRunRequest,
    PreparedAuthState,
    ResolvedCredentials,
    ResolvedTotpConfig,
    _artifact_mode_for_step,
    _generate_totp,
    _prepare_auth_state,
    _resolve_credentials,
    _resolve_step_value,
)
from pm_agent.config.models import (
    AuthStrategy,
    ArtifactMode,
    CredentialsAuthConfig,
    JourneyStepConfig,
    SecretValueConfig,
    TotpConfig,
)


def test_resolve_credentials_reads_env_backed_values(monkeypatch):
    monkeypatch.setenv("DOGFOOD_USERNAME", "dogfood@example.com")
    monkeypatch.setenv("DOGFOOD_PASSWORD", "super-secret")
    monkeypatch.setenv("DOGFOOD_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    request = BrowserRunRequest(
        auth_strategy=AuthStrategy.CREDENTIALS,
        journeys=[],
        base_url="https://dogfood.example.com",
        artifact_root=Path("artifacts"),
        repo_root=Path("."),
        credentials=CredentialsAuthConfig(
            username=SecretValueConfig(env="DOGFOOD_USERNAME"),
            password=SecretValueConfig(env="DOGFOOD_PASSWORD"),
            totp=TotpConfig(secret=SecretValueConfig(env="DOGFOOD_TOTP_SECRET")),
        ),
    )

    credentials = _resolve_credentials(request)

    assert credentials is not None
    assert credentials.username == "dogfood@example.com"
    assert credentials.password == "super-secret"
    assert credentials.totp is not None
    assert credentials.totp.secret == "JBSWY3DPEHPK3PXP"


def test_generate_totp_matches_rfc_vector():
    config = ResolvedTotpConfig(
        secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
        digits=8,
        period_seconds=30,
        algorithm="SHA1",
    )

    assert _generate_totp(config, for_time=59) == "94287082"


def test_resolve_step_value_expands_credentials_placeholders(monkeypatch):
    monkeypatch.setattr("pm_agent.adapters.playwright._generate_totp", lambda _: "123456")
    credentials = ResolvedCredentials(
        username="dogfood@example.com",
        password="super-secret",
        totp=ResolvedTotpConfig(
            secret="JBSWY3DPEHPK3PXP",
            digits=6,
            period_seconds=30,
            algorithm="SHA1",
        ),
    )

    value = _resolve_step_value(
        "user={{ credentials.username }} otp={{ credentials.totp_code }}",
        auth_strategy=AuthStrategy.CREDENTIALS,
        credentials=credentials,
    )

    assert value == "user=dogfood@example.com otp=123456"


def test_resolve_step_value_rejects_credentials_placeholders_without_credentials():
    with pytest.raises(BrowserAdapterError, match="requires auth_strategy=credentials"):
        _resolve_step_value(
            "{{ credentials.password }}",
            auth_strategy=AuthStrategy.NONE,
            credentials=None,
        )


def test_artifact_mode_defaults_to_redact_for_credential_placeholders():
    step = JourneyStepConfig(
        id="fill-password",
        action="fill",
        selector="input[name='password']",
        value="{{ credentials.password }}",
    )

    assert _artifact_mode_for_step(step) == ArtifactMode.REDACT


def test_prepare_auth_state_uses_existing_storage_state(tmp_path: Path):
    storage_state = tmp_path / "auth.json"
    storage_state.write_text("{}", encoding="utf-8")
    request = BrowserRunRequest(
        auth_strategy=AuthStrategy.STORAGE_STATE,
        journeys=[],
        base_url="https://dogfood.example.com",
        artifact_root=tmp_path / "artifacts",
        repo_root=tmp_path,
        storage_state=Path("auth.json"),
    )

    auth_state = _prepare_auth_state(request, credentials=None)

    assert auth_state == PreparedAuthState(storage_state_path=storage_state)


def test_prepare_auth_state_runs_setup_script_and_creates_temporary_storage_state(tmp_path: Path):
    script = tmp_path / "setup-auth.py"
    script.write_text(
        """
from pathlib import Path
import json
import os

Path(os.environ["PM_AGENT_STORAGE_STATE_PATH"]).write_text(
    json.dumps({"cookies": [], "origins": []}),
    encoding="utf-8",
)
""".strip(),
        encoding="utf-8",
    )
    request = BrowserRunRequest(
        auth_strategy=AuthStrategy.SETUP_SCRIPT,
        journeys=[],
        base_url="https://dogfood.example.com",
        artifact_root=tmp_path / "artifacts",
        repo_root=tmp_path,
        setup_script=Path("setup-auth.py"),
        setup_script_timeout_seconds=5,
    )

    auth_state = _prepare_auth_state(request, credentials=None)

    assert auth_state.storage_state_path is not None
    assert auth_state.storage_state_path.exists()
    assert auth_state.cleanup_paths == (auth_state.storage_state_path,)


def test_prepare_auth_state_rejects_manual_auth(tmp_path: Path):
    request = BrowserRunRequest(
        auth_strategy=AuthStrategy.MANUAL_DISABLED,
        journeys=[],
        base_url="https://dogfood.example.com",
        artifact_root=tmp_path / "artifacts",
        repo_root=tmp_path,
    )

    with pytest.raises(BrowserAdapterError, match="manual auth is not supported"):
        _prepare_auth_state(request, credentials=None)
