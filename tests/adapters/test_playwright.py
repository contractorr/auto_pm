from pathlib import Path

import pytest

from pm_agent.adapters.playwright import (
    BrowserAdapterError,
    BrowserRunRequest,
    ResolvedCredentials,
    ResolvedTotpConfig,
    _generate_totp,
    _resolve_credentials,
    _resolve_step_value,
)
from pm_agent.config.models import (
    AuthStrategy,
    CredentialsAuthConfig,
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
