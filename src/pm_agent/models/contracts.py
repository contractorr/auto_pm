"""Shared contracts across agents, synthesis, and lifecycle management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Trigger(str, Enum):
    PUSH = "push"
    SCHEDULE = "schedule"
    MANUAL = "manual"


class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentName(str, Enum):
    RESEARCH = "research"
    CODEBASE = "codebase"
    DOGFOODING = "dogfooding"
    EXISTING_ISSUES = "existing_issues"
    SYNTHESIS = "synthesis"


class FindingKind(str, Enum):
    UX_BUG = "ux_bug"
    PRODUCT_GAP = "product_gap"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    CONTENT = "content"
    COMPETITIVE_GAP = "competitive_gap"
    TECHNICAL_RISK = "technical_risk"
    STRATEGIC_OPPORTUNITY = "strategic_opportunity"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(str, Enum):
    COMPETITOR_PAGE = "competitor_page"
    ARXIV_PAPER = "arxiv_paper"
    REPO_FILE = "repo_file"
    REPO_DOC = "repo_doc"
    PLAYWRIGHT_STEP = "playwright_step"
    GITHUB_ISSUE = "github_issue"
    GITHUB_PR = "github_pr"
    MEMORY = "memory"


class IssueAction(str, Enum):
    CREATE = "create"
    UPDATE_EXISTING = "update_existing"
    COMMENT_EXISTING = "comment_existing"
    CLOSE_EXISTING = "close_existing"
    NOOP = "noop"


class RunContext(BaseModel):
    run_id: str
    repo: str
    branch: str
    commit_sha: str | None = None
    trigger: Trigger
    started_at: datetime
    config_hash: str


class ProductContext(BaseModel):
    vision: str
    target_users: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    strategic_priorities: list[str] = Field(default_factory=list)


class AgentWarning(BaseModel):
    code: str
    message: str
    fatal: bool = False


class SourceRef(BaseModel):
    source_type: SourceType
    source_id: str
    title: str | None = None
    locator: str | None = None
    excerpt: str | None = None
    repo_path: str | None = None
    issue_number: int | None = None
    artifact_path: str | None = None


class Evidence(BaseModel):
    summary: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    reproduction_steps: list[str] = Field(default_factory=list)
    observed_behavior: str | None = None
    expected_behavior: str | None = None
    console_errors: list[str] = Field(default_factory=list)
    network_errors: list[str] = Field(default_factory=list)
    accessibility_notes: list[str] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    finding_id: str
    agent: AgentName
    kind: FindingKind
    title: str
    problem_statement: str
    user_impact: str
    affected_surfaces: list[str] = Field(default_factory=list)
    affected_personas: list[str] = Field(default_factory=list)
    severity: Severity
    raw_confidence: float
    novelty_key: str
    dedup_keys: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    proposed_direction: str | None = None


class AgentEnvelope(BaseModel):
    agent: AgentName
    status: AgentStatus
    started_at: datetime
    ended_at: datetime
    warnings: list[AgentWarning] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class CompetitorSnapshot(BaseModel):
    url: str
    product_summary: str
    notable_capabilities: list[str] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)


class PaperSnapshot(BaseModel):
    arxiv_id: str
    title: str
    published_at: datetime
    relevance_reason: str
    implication: str


class ResearchAgentOutput(AgentEnvelope):
    agent: Literal[AgentName.RESEARCH] = AgentName.RESEARCH
    competitors: list[CompetitorSnapshot] = Field(default_factory=list)
    papers: list[PaperSnapshot] = Field(default_factory=list)


class ComponentSummary(BaseModel):
    name: str
    paths: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CodebaseAgentOutput(AgentEnvelope):
    agent: Literal[AgentName.CODEBASE] = AgentName.CODEBASE
    repo_summary: str
    components: list[ComponentSummary] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    hotspot_files: list[str] = Field(default_factory=list)


class JourneyStepResult(BaseModel):
    step_id: str
    action: str
    url: str | None = None
    success: bool
    console_errors: list[str] = Field(default_factory=list)
    network_errors: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    accessibility_snapshot_path: str | None = None
    artifacts_redacted: bool = False
    artifacts_skipped: bool = False
    vision_notes: list[str] = Field(default_factory=list)


class JourneyRun(BaseModel):
    journey_id: str
    persona: str | None = None
    success: bool
    started_at: datetime
    ended_at: datetime
    steps: list[JourneyStepResult] = Field(default_factory=list)


class DogfoodingAgentOutput(AgentEnvelope):
    agent: Literal[AgentName.DOGFOODING] = AgentName.DOGFOODING
    runtime_mode: str
    base_url: str | None = None
    journeys: list[JourneyRun] = Field(default_factory=list)


class ExistingIssueRecord(BaseModel):
    number: int
    title: str
    state: Literal["open", "closed"]
    labels: list[str] = Field(default_factory=list)
    body_summary: str
    ai_authored: bool = False
    cluster_id: str | None = None
    linked_prs: list[int] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None


class ExistingIssuesAgentOutput(AgentEnvelope):
    agent: Literal[AgentName.EXISTING_ISSUES] = AgentName.EXISTING_ISSUES
    open_issues: list[ExistingIssueRecord] = Field(default_factory=list)
    recent_closed_issues: list[ExistingIssueRecord] = Field(default_factory=list)
    open_prs: list[ExistingIssueRecord] = Field(default_factory=list)


class SynthesisInput(BaseModel):
    run: RunContext
    product: ProductContext
    memory_digest: str
    research: ResearchAgentOutput | None = None
    codebase: CodebaseAgentOutput | None = None
    dogfooding: DogfoodingAgentOutput | None = None
    existing_issues: ExistingIssuesAgentOutput


class ICEBreakdown(BaseModel):
    impact: float
    confidence: float
    ease: float
    ice_score: float
    convergence_multiplier: float
    strategic_multiplier: float
    calibration_multiplier: float
    priority_score: float
    rationale: str


class DedupDecision(BaseModel):
    action: IssueAction
    matched_issue_number: int | None = None
    rationale: str


class IssueProposal(BaseModel):
    cluster_id: str
    title: str
    summary: str
    user_problem: str
    evidence_summary: str
    affected_surfaces: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    ice: ICEBreakdown
    dedup: DedupDecision
    issue_body_markdown: str | None = None


class MemoryOutcome(BaseModel):
    issue_number: int
    cluster_id: str
    disposition: Literal["fixed", "wontfix", "duplicate", "obsolete", "stale"]
    components: list[str] = Field(default_factory=list)
    source_agents: list[AgentName] = Field(default_factory=list)
    maintainer_reason: str | None = None
    closed_at: datetime | None = None


class IssueStateMemory(BaseModel):
    issue_number: int
    cluster_id: str | None = None
    ai_authored: bool = False
    absent_runs: int = 0
    last_seen_open_at: datetime | None = None
    last_seen_cluster_at: datetime | None = None
    last_escalated_at: datetime | None = None
    components: list[str] = Field(default_factory=list)
    source_agents: list[AgentName] = Field(default_factory=list)


class PMAgentMemory(BaseModel):
    schema_version: int = 1
    updated_at: datetime
    recent_outcomes: list[MemoryOutcome] = Field(default_factory=list)
    source_priors: dict[str, float] = Field(default_factory=dict)
    component_priors: dict[str, float] = Field(default_factory=dict)
    false_positive_patterns: dict[str, str] = Field(default_factory=dict)
    label_preferences: dict[str, list[str]] = Field(default_factory=dict)
    issue_state: dict[str, IssueStateMemory] = Field(default_factory=dict)
