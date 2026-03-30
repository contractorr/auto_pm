"""Harness scenario models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    FindingKind,
    ProductContext,
    RunContext,
)


class HarnessInput(BaseModel):
    run: RunContext
    product: ProductContext


class HarnessExpectation(BaseModel):
    status: AgentStatus = AgentStatus.SUCCESS
    min_findings: int = 0
    required_kinds: list[FindingKind] = Field(default_factory=list)
    required_tags: list[str] = Field(default_factory=list)


class HarnessScenario(BaseModel):
    id: str
    description: str
    agent: AgentName
    input: HarnessInput
    expected: HarnessExpectation = Field(default_factory=HarnessExpectation)
    fixture_output: dict[str, Any]


class ScenarioResult(BaseModel):
    scenario_id: str
    passed: bool
    messages: list[str] = Field(default_factory=list)
