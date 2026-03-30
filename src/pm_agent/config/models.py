"""Typed configuration for pm-config.yml."""

from __future__ import annotations

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


class JourneyStepConfig(BaseModel):
    id: str
    action: str
    target: str | None = None
    selector: str | None = None
    value: str | None = None
    wait_for: str | None = None
    expect_url: str | None = None
    timeout_ms: int = 10000


class JourneyConfig(BaseModel):
    id: str
    persona: str | None = None
    start_path: str
    steps: list[JourneyStepConfig] = Field(default_factory=list)


class DogfoodingConfig(BaseModel):
    enabled: bool = True
    auth_strategy: AuthStrategy = AuthStrategy.NONE
    setup_script: Path | None = None
    journeys: list[JourneyConfig] = Field(default_factory=list)


class ResearchConfig(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    arxiv_categories: list[str] = Field(default_factory=list)


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
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    issue_policy: IssuePolicyConfig = Field(default_factory=IssuePolicyConfig)
