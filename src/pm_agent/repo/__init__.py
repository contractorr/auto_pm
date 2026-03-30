"""Repository inspection helpers."""

from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.manifest import build_repo_manifest
from pm_agent.repo.product import load_product_context
from pm_agent.repo.retrieval import hotspot_files
from pm_agent.repo.summarizer import summarize_components, summarize_repo

__all__ = [
    "build_repo_manifest",
    "discover_repo_capabilities",
    "hotspot_files",
    "load_product_context",
    "summarize_components",
    "summarize_repo",
]
