"""Optional Anthropic-backed research review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pm_agent.adapters.anthropic import AnthropicAdapterError, AnthropicMessagesClient
from pm_agent.adapters.research import ArxivEntry, PageSummary
from pm_agent.agents.research_prompts import (
    build_competitor_review_system_prompt,
    build_competitor_review_user_prompt,
    build_paper_review_system_prompt,
    build_paper_review_user_prompt,
)
from pm_agent.models.contracts import ProductContext


class CompetitorReviewResponse(BaseModel):
    issue_worthy: bool = False
    finding_kind: Literal["competitive_gap", "strategic_opportunity"] = "strategic_opportunity"
    title: str
    problem_statement: str
    user_impact: str
    severity: Literal["low", "medium", "high"] = "low"
    confidence: float = 0.5
    summary: str
    notable_capabilities: list[str] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    proposed_direction: str | None = None


class PaperReviewResponse(BaseModel):
    issue_worthy: bool = False
    title: str
    problem_statement: str
    user_impact: str
    severity: Literal["low", "medium", "high"] = "low"
    confidence: float = 0.5
    relevance_reason: str
    implication: str
    tags: list[str] = Field(default_factory=list)
    proposed_direction: str | None = None


class AnthropicResearchEnhancer:
    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        research_review_enabled: bool = True,
    ) -> None:
        self._client = client
        self.research_review_enabled = research_review_enabled

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def review_competitor(
        self,
        *,
        product: ProductContext,
        summary: PageSummary,
    ) -> CompetitorReviewResponse:
        if not self.research_review_enabled:
            raise AnthropicAdapterError("Anthropic research review is disabled")
        return self._client.create_json_message(
            system_prompt=build_competitor_review_system_prompt(),
            user_prompt=build_competitor_review_user_prompt(product=product, summary=summary),
            response_model=CompetitorReviewResponse,
        )

    def review_paper(
        self,
        *,
        product: ProductContext,
        entry: ArxivEntry,
    ) -> PaperReviewResponse:
        if not self.research_review_enabled:
            raise AnthropicAdapterError("Anthropic research review is disabled")
        return self._client.create_json_message(
            system_prompt=build_paper_review_system_prompt(),
            user_prompt=build_paper_review_user_prompt(product=product, entry=entry),
            response_model=PaperReviewResponse,
        )


__all__ = [
    "AnthropicAdapterError",
    "AnthropicResearchEnhancer",
    "CompetitorReviewResponse",
    "PaperReviewResponse",
]
