"""Typed configuration for pm-config.yml."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator


def validate_cron(expr: str) -> str:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields: {expr}")
    return expr


class RuntimeMode(str, Enum):
    DOCKER_COMPOSE = "docker_compose"
    COMMANDS = "commands"
    PREVIEW_URL = "preview_url"
    EXTERNAL_URL = "external_url"
    DISABLED = "disabled"


class AuthStrategy(str, Enum):
    NONE = "none"
    TEST_AUTH = "test_auth"
    CREDENTIALS = "credentials"
    STORAGE_STATE = "storage_state"
    SETUP_SCRIPT = "setup_script"
    MANUAL_DISABLED = "manual_disabled"


class ArtifactMode(str, Enum):
    CAPTURE = "capture"
    REDACT = "redact"
    SKIP = "skip"


class GitHubWriteMode(str, Enum):
    DISABLED = "disabled"
    COMMENT_ONLY = "comment_only"
    APPLY = "apply"


class RepoConfig(BaseModel):
    full_name: str
    default_branch: str = "main"
    product_file: Path = Path("PRODUCT.md")
    memory_file: Path = Path(".github/pm-agent-memory.json")
    project_roots: list[Path] = Field(default_factory=lambda: [Path(".")])
    ignore_paths: list[Path] = Field(default_factory=list)

    @model_validator(mode="after")
    def expand_paths(self) -> "RepoConfig":
        self.product_file = Path(self.product_file)
        self.memory_file = Path(self.memory_file)
        self.project_roots = [Path(path) for path in self.project_roots]
        self.ignore_paths = [Path(path) for path in self.ignore_paths]
        return self


class TriggerConfig(BaseModel):
    on_push_to_main: bool = True
    schedules: list[str] = Field(default_factory=list)

    @field_validator("schedules")
    @classmethod
    def validate_schedules(cls, values: list[str]) -> list[str]:
        return [validate_cron(value) for value in values]


class RuntimeConfig(BaseModel):
    mode: RuntimeMode = RuntimeMode.DISABLED
    compose_file: Path | None = None
    start_commands: list[str] = Field(default_factory=list)
    service_urls: list[str] = Field(default_factory=list)
    healthcheck_urls: list[str] = Field(default_factory=list)
    startup_timeout_seconds: int = 180
    healthcheck_timeout_seconds: int = 120


class SecretValueConfig(BaseModel):
    value: str | None = None
    env: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "SecretValueConfig":
        if bool(self.value) == bool(self.env):
            raise ValueError("secret value requires exactly one of value or env")
        return self

    def is_available(self) -> bool:
        if self.value:
            return True
        if self.env:
            return bool(os.getenv(self.env))
        return False

    def resolve(self, field_name: str) -> str:
        if self.value:
            return self.value
        if not self.env:
            raise ValueError(f"{field_name} is not configured")
        value = os.getenv(self.env)
        if not value:
            raise ValueError(f"{field_name} env var is not set: {self.env}")
        return value


class TotpConfig(BaseModel):
    secret: SecretValueConfig
    digits: int = 6
    period_seconds: int = 30
    algorithm: str = "SHA1"

    @field_validator("digits")
    @classmethod
    def validate_digits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("digits must be positive")
        return value

    @field_validator("period_seconds")
    @classmethod
    def validate_period_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("period_seconds must be positive")
        return value

    @field_validator("algorithm")
    @classmethod
    def normalize_algorithm(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"SHA1", "SHA256", "SHA512"}:
            raise ValueError("algorithm must be one of SHA1, SHA256, or SHA512")
        return normalized


class CredentialsAuthConfig(BaseModel):
    username: SecretValueConfig
    password: SecretValueConfig
    totp: TotpConfig | None = None

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.username.is_available():
            missing.append("username")
        if not self.password.is_available():
            missing.append("password")
        if self.totp is not None and not self.totp.secret.is_available():
            missing.append("totp.secret")
        return missing


class JourneyStepConfig(BaseModel):
    id: str
    action: str
    target: str | None = None
    selector: str | None = None
    value: str | None = None
    wait_for: str | None = None
    expect_url: str | None = None
    artifact_mode: ArtifactMode = ArtifactMode.CAPTURE
    redact_selectors: list[str] = Field(default_factory=list)
    timeout_ms: int = 10000


class JourneyConfig(BaseModel):
    id: str
    persona: str | None = None
    start_path: str
    steps: list[JourneyStepConfig] = Field(default_factory=list)


class DogfoodingConfig(BaseModel):
    enabled: bool = True
    auth_strategy: AuthStrategy = AuthStrategy.NONE
    credentials: CredentialsAuthConfig | None = None
    storage_state: Path | None = None
    setup_script: Path | None = None
    setup_script_timeout_seconds: int = 120
    journeys: list[JourneyConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_auth_requirements(self) -> "DogfoodingConfig":
        if self.storage_state is not None:
            self.storage_state = Path(self.storage_state)
        if self.setup_script is not None:
            self.setup_script = Path(self.setup_script)
        if self.auth_strategy == AuthStrategy.CREDENTIALS and self.credentials is None:
            raise ValueError("dogfooding.credentials is required when auth_strategy=credentials")
        if self.auth_strategy == AuthStrategy.STORAGE_STATE and self.storage_state is None:
            raise ValueError("dogfooding.storage_state is required when auth_strategy=storage_state")
        if self.auth_strategy == AuthStrategy.SETUP_SCRIPT and self.setup_script is None:
            raise ValueError("dogfooding.setup_script is required when auth_strategy=setup_script")
        if self.setup_script_timeout_seconds <= 0:
            raise ValueError("dogfooding.setup_script_timeout_seconds must be positive")
        return self


class ResearchConfig(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    arxiv_categories: list[str] = Field(default_factory=list)


class AnthropicConfig(BaseModel):
    enabled: bool = False
    api_key_env: str = "ANTHROPIC_API_KEY"
    api_base_url: str = "https://api.anthropic.com"
    model: str = "claude-3-7-sonnet-latest"
    max_tokens: int = 1800
    temperature: float = 0.0
    research_review_enabled: bool = True
    codebase_review_enabled: bool = True
    cluster_review_enabled: bool = True
    portfolio_review_enabled: bool = True
    issue_writer_enabled: bool = True


class GitHubConfig(BaseModel):
    labels: list[str] = Field(default_factory=list)
    stale_days: int = 21
    write_mode: GitHubWriteMode = GitHubWriteMode.DISABLED
    update_ai_authored_issues_only: bool = True


class IssuePolicyConfig(BaseModel):
    max_new_issues_per_run: int = 3
    min_priority_score: float = 24.0
    min_confidence: float = 3.0
    cooldown_days_per_cluster: int = 14
    auto_close_ai_issues_only: bool = True
    auto_close_absent_runs: int = 2


class PMConfig(BaseModel):
    repo: RepoConfig
    triggers: TriggerConfig = Field(default_factory=TriggerConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    dogfooding: DogfoodingConfig = Field(default_factory=DogfoodingConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    issue_policy: IssuePolicyConfig = Field(default_factory=IssuePolicyConfig)
