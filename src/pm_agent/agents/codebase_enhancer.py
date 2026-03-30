"""Optional Anthropic-backed codebase review."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pm_agent.adapters.anthropic import AnthropicAdapterError, AnthropicMessagesClient
from pm_agent.agents.codebase_prompts import (
    build_codebase_review_system_prompt,
    build_codebase_review_user_prompt,
)
from pm_agent.models.contracts import ProductContext
from pm_agent.repo.manifest import RepoManifest


class CodebaseComponentReview(BaseModel):
    name: str
    paths: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CodebaseFindingReview(BaseModel):
    kind: str
    title: str
    problem_statement: str
    user_impact: str
    affected_surfaces: list[str] = Field(default_factory=list)
    severity: str = "low"
    confidence: float = 0.5
    summary: str
    relevant_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    proposed_direction: str | None = None


class CodebaseReviewResponse(BaseModel):
    repo_summary: str
    components: list[CodebaseComponentReview] = Field(default_factory=list)
    findings: list[CodebaseFindingReview] = Field(default_factory=list)


class AnthropicCodebaseEnhancer:
    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        codebase_review_enabled: bool = True,
    ) -> None:
        self._client = client
        self.codebase_review_enabled = codebase_review_enabled

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def review_codebase(
        self,
        *,
        product: ProductContext,
        manifest: RepoManifest,
        repo_summary: str,
        components: list[dict[str, object]],
        changed_files: list[str],
        hotspot_files: list[str],
        file_context: list[dict[str, object]],
    ) -> CodebaseReviewResponse:
        if not self.codebase_review_enabled:
            raise AnthropicAdapterError("Anthropic codebase review is disabled")
        return self._client.create_json_message(
            system_prompt=build_codebase_review_system_prompt(),
            user_prompt=build_codebase_review_user_prompt(
                product=product,
                manifest=manifest,
                repo_summary=repo_summary,
                components=components,
                changed_files=changed_files,
                hotspot_files=hotspot_files,
                file_context=file_context,
            ),
            response_model=CodebaseReviewResponse,
        )


__all__ = [
    "AnthropicAdapterError",
    "AnthropicCodebaseEnhancer",
    "CodebaseComponentReview",
    "CodebaseFindingReview",
    "CodebaseReviewResponse",
]
