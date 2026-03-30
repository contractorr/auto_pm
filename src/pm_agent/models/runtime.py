"""Runtime and synthesis result models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm_agent.models.contracts import (
    AgentEnvelope,
    AgentName,
    Finding,
    IssueProposal,
    ProductContext,
    RunContext,
    Severity,
)


class CapabilitySnapshot(BaseModel):
    repo_root: str
    runtime_mode: str
    product_file: str
    product_file_exists: bool
    compose_file: str | None = None
    docker_compose_ready: bool = False
    playwright_config: str | None = None
    test_auth_supported: bool = False
    github_actions_present: bool = False
    dogfooding_ready: bool = False
    notes: list[str] = Field(default_factory=list)


class FindingCluster(BaseModel):
    cluster_id: str
    title: str
    problem_statement: str
    user_impact: str
    affected_surfaces: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_agents: list[AgentName] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    convergence_count: int
    severity: Severity
    average_confidence: float
    novelty_keys: list[str] = Field(default_factory=list)


class SuppressedCluster(BaseModel):
    cluster_id: str
    title: str
    reason: str


class SynthesisReport(BaseModel):
    clusters: list[FindingCluster] = Field(default_factory=list)
    proposals: list[IssueProposal] = Field(default_factory=list)
    suppressed: list[SuppressedCluster] = Field(default_factory=list)


class DryRunReport(BaseModel):
    run: RunContext
    product: ProductContext
    capabilities: CapabilitySnapshot
    agent_outputs: list[AgentEnvelope] = Field(default_factory=list)
    synthesis: SynthesisReport


class WritebackActionResult(BaseModel):
    cluster_id: str
    proposal_title: str
    action: str
    outcome: str
    target_number: int | None = None
    message: str


class WritebackReport(BaseModel):
    mode: str
    results: list[WritebackActionResult] = Field(default_factory=list)
