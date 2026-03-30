"""Prompt builders for optional model-backed research review."""

from __future__ import annotations

import json

from pm_agent.adapters.research import ArxivEntry, PageSummary
from pm_agent.models.contracts import ProductContext


def build_competitor_review_system_prompt() -> str:
    return (
        "You are a conservative product research analyst. "
        "Review one competitor source at a time against the target product strategy. "
        "Only use the provided source data. Return JSON only."
    )


def build_competitor_review_user_prompt(
    *,
    product: ProductContext,
    summary: PageSummary,
) -> str:
    payload = {
        "task": "Assess whether this competitor source reveals a meaningful product or UX gap worth tracking.",
        "rules": [
            "Be conservative and do not invent features or claims not present in the source summary.",
            "Use competitive_gap only when the source implies a specific product gap; otherwise use strategic_opportunity.",
            "If the source is only loosely relevant, set issue_worthy to false.",
        ],
        "required_json_shape": {
            "issue_worthy": "boolean",
            "finding_kind": "competitive_gap | strategic_opportunity",
            "title": "string",
            "problem_statement": "string",
            "user_impact": "string",
            "severity": "low | medium | high",
            "confidence": "number between 0 and 1",
            "summary": "string",
            "notable_capabilities": ["string"],
            "comparison_notes": ["string"],
            "tags": ["string"],
            "proposed_direction": "string or null",
        },
        "product": product.model_dump(mode="json"),
        "source": {
            "url": summary.url,
            "title": summary.title,
            "description": summary.description,
            "text_excerpt": summary.text_excerpt,
        },
    }
    return json.dumps(payload, indent=2)


def build_paper_review_system_prompt() -> str:
    return (
        "You are a conservative PM research analyst reviewing one paper at a time. "
        "Only use the provided metadata and abstract summary. Return JSON only."
    )


def build_paper_review_user_prompt(
    *,
    product: ProductContext,
    entry: ArxivEntry,
) -> str:
    payload = {
        "task": "Assess whether this paper creates a meaningful product or UX opportunity worth tracking now.",
        "rules": [
            "Be conservative and avoid overselling speculative research.",
            "If the paper is only adjacent to the current strategy, set issue_worthy to false.",
            "Prefer strategic_opportunity over hard bug framing for papers.",
        ],
        "required_json_shape": {
            "issue_worthy": "boolean",
            "title": "string",
            "problem_statement": "string",
            "user_impact": "string",
            "severity": "low | medium | high",
            "confidence": "number between 0 and 1",
            "relevance_reason": "string",
            "implication": "string",
            "tags": ["string"],
            "proposed_direction": "string or null",
        },
        "product": product.model_dump(mode="json"),
        "paper": {
            "arxiv_id": entry.arxiv_id,
            "title": entry.title,
            "summary": entry.summary,
            "published_at": entry.published_at.isoformat(),
            "category": entry.category,
            "link": entry.link,
        },
    }
    return json.dumps(payload, indent=2)
