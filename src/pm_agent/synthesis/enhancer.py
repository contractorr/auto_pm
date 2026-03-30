"""Optional Anthropic-backed synthesis refinement."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pm_agent.adapters.anthropic import AnthropicAdapterError, AnthropicMessagesClient
from pm_agent.models.contracts import DedupDecision, ICEBreakdown, ProductContext
from pm_agent.models.runtime import FindingCluster
from pm_agent.synthesis.prompts import (
    build_cluster_review_system_prompt,
    build_cluster_review_user_prompt,
    build_issue_writer_system_prompt,
    build_issue_writer_user_prompt,
)


class ClusterReviewResponse(BaseModel):
    action: Literal["create", "noop"]
    title: str
    summary: str
    user_problem: str
    evidence_summary: str
    labels: list[str] = Field(default_factory=list)
    suppression_reason: str | None = None


class IssueWriterResponse(BaseModel):
    issue_body_markdown: str


class AnthropicSynthesisEnhancer:
    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        cluster_review_enabled: bool = True,
        issue_writer_enabled: bool = True,
    ) -> None:
        self._client = client
        self.cluster_review_enabled = cluster_review_enabled
        self.issue_writer_enabled = issue_writer_enabled

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def review_cluster(
        self,
        *,
        product: ProductContext,
        memory_digest: str,
        cluster: FindingCluster,
        ice: ICEBreakdown,
        dedup: DedupDecision,
        labels: list[str],
    ) -> ClusterReviewResponse:
        if not self.cluster_review_enabled:
            raise AnthropicAdapterError("Anthropic cluster review is disabled")
        return self._client.create_json_message(
            system_prompt=build_cluster_review_system_prompt(),
            user_prompt=build_cluster_review_user_prompt(
                product=product,
                memory_digest=memory_digest,
                cluster=cluster,
                ice=ice,
                dedup=dedup,
                labels=labels,
            ),
            response_model=ClusterReviewResponse,
        )

    def write_issue(
        self,
        *,
        product: ProductContext,
        cluster: FindingCluster,
        ice: ICEBreakdown,
        dedup: DedupDecision,
        title: str,
        summary: str,
        user_problem: str,
        evidence_summary: str,
        labels: list[str],
    ) -> str:
        if not self.issue_writer_enabled:
            raise AnthropicAdapterError("Anthropic issue writing is disabled")
        response = self._client.create_json_message(
            system_prompt=build_issue_writer_system_prompt(),
            user_prompt=build_issue_writer_user_prompt(
                product=product,
                cluster=cluster,
                ice=ice,
                dedup=dedup,
                title=title,
                summary=summary,
                user_problem=user_problem,
                evidence_summary=evidence_summary,
                labels=labels,
            ),
            response_model=IssueWriterResponse,
        )
        return response.issue_body_markdown


__all__ = [
    "AnthropicAdapterError",
    "AnthropicSynthesisEnhancer",
    "ClusterReviewResponse",
    "IssueWriterResponse",
]
