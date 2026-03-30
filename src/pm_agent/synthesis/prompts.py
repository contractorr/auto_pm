"""Prompt builders for model-backed synthesis review and issue writing."""

from __future__ import annotations

import json

from pm_agent.models.contracts import DedupDecision, ICEBreakdown, ProductContext
from pm_agent.models.runtime import FindingCluster


def build_cluster_review_system_prompt() -> str:
    return (
        "You are a conservative PM/UX triage reviewer. "
        "You will receive one candidate issue cluster at a time. "
        "Only use provided evidence. Return JSON only."
    )


def build_cluster_review_user_prompt(
    *,
    product: ProductContext,
    memory_digest: str,
    cluster: FindingCluster,
    ice: ICEBreakdown,
    dedup: DedupDecision,
    labels: list[str],
) -> str:
    instructions = {
        "task": "Review whether this cluster should become an issue proposal now.",
        "rules": [
            "Be conservative and prefer suppressing weak or redundant issues.",
            "Do not invent evidence or implementation details.",
            "If the deterministic dedup action already matched an existing issue or PR, do not override the target.",
            "For unmatched clusters, action may only be create or noop.",
            "Return labels as short GitHub labels.",
        ],
        "required_json_shape": {
            "action": "create | noop",
            "title": "string",
            "summary": "string",
            "user_problem": "string",
            "evidence_summary": "string",
            "labels": ["string"],
            "suppression_reason": "string or null",
        },
        "product": product.model_dump(mode="json"),
        "memory_digest": memory_digest,
        "cluster": cluster.model_dump(mode="json"),
        "ice": ice.model_dump(mode="json"),
        "dedup": dedup.model_dump(mode="json"),
        "base_labels": labels,
    }
    return json.dumps(instructions, indent=2)


def build_issue_writer_system_prompt() -> str:
    return (
        "You write structured GitHub issues for product and UX teams. "
        "Use only the provided data. Return JSON only."
    )


def build_issue_writer_user_prompt(
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
    instructions = {
        "task": "Write a concise GitHub issue body in markdown.",
        "rules": [
            "Keep the hidden pm-agent metadata comment at the end.",
            "Cite all source families mentioned in the cluster.",
            "Do not invent repro steps that are not supported by the evidence.",
            "Prefer short, actionable language.",
        ],
        "required_json_shape": {
            "issue_body_markdown": "string",
        },
        "product": product.model_dump(mode="json"),
        "cluster": cluster.model_dump(mode="json"),
        "ice": ice.model_dump(mode="json"),
        "dedup": dedup.model_dump(mode="json"),
        "proposal": {
            "title": title,
            "summary": summary,
            "user_problem": user_problem,
            "evidence_summary": evidence_summary,
            "labels": labels,
        },
    }
    return json.dumps(instructions, indent=2)
