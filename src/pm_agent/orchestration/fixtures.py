"""Load typed dry-run pipeline fixtures."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from pm_agent.models.contracts import (
    CodebaseAgentOutput,
    DogfoodingAgentOutput,
    ExistingIssuesAgentOutput,
    ResearchAgentOutput,
    RunContext,
)


class DryRunFixture(BaseModel):
    run: RunContext
    research: ResearchAgentOutput | None = None
    codebase: CodebaseAgentOutput | None = None
    dogfooding: DogfoodingAgentOutput | None = None
    existing_issues: ExistingIssuesAgentOutput


def load_dry_run_fixture(path: str | Path) -> DryRunFixture:
    fixture_path = Path(path)
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8")) or {}
    return DryRunFixture.model_validate(data)
