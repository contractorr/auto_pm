"""Prompt builders for optional model-backed codebase review."""

from __future__ import annotations

import json

from pm_agent.models.contracts import ProductContext
from pm_agent.repo.manifest import RepoManifest


def build_codebase_review_system_prompt() -> str:
    return (
        "You are a conservative staff product engineer reviewing a repository snapshot. "
        "Use only the supplied manifest, deterministic summaries, and file excerpts. "
        "Return JSON only."
    )


def build_codebase_review_user_prompt(
    *,
    product: ProductContext,
    manifest: RepoManifest,
    repo_summary: str,
    components: list[dict[str, object]],
    changed_files: list[str],
    hotspot_files: list[str],
    file_context: list[dict[str, object]],
) -> str:
    payload = {
        "task": "Refine the current understanding of the repository and surface conservative codebase findings.",
        "rules": [
            "Do not invent features, components, or bugs not supported by the file context.",
            "Prefer a small number of high-signal findings over broad speculation.",
            "Return components only if you can improve or sharpen the deterministic component summaries.",
            "Use technical_risk or product_gap unless the evidence clearly indicates another finding kind.",
        ],
        "required_json_shape": {
            "repo_summary": "string",
            "components": [
                {
                    "name": "string",
                    "paths": ["string"],
                    "responsibilities": ["string"],
                    "risks": ["string"],
                }
            ],
            "findings": [
                {
                    "kind": (
                        "product_gap | technical_risk | reliability | performance | "
                        "content | strategic_opportunity"
                    ),
                    "title": "string",
                    "problem_statement": "string",
                    "user_impact": "string",
                    "affected_surfaces": ["string"],
                    "severity": "low | medium | high",
                    "confidence": "number between 0 and 1",
                    "summary": "string",
                    "relevant_paths": ["string"],
                    "tags": ["string"],
                    "proposed_direction": "string or null",
                }
            ],
        },
        "product": product.model_dump(mode="json"),
        "manifest": {
            "repo_root": manifest.repo_root,
            "entry_count": len(manifest.entries),
            "source_file_count": len(manifest.source_files),
            "test_file_count": len(manifest.test_files),
            "doc_file_count": len(manifest.doc_files),
            "config_file_count": len(manifest.config_files),
            "framework_signals": manifest.framework_signals,
        },
        "deterministic_summary": repo_summary,
        "deterministic_components": components,
        "changed_files": changed_files,
        "hotspot_files": hotspot_files,
        "representative_files": file_context,
    }
    return json.dumps(payload, indent=2)
