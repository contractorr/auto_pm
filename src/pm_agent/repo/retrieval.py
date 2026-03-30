"""Heuristics for selecting representative files from a manifest."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pm_agent.repo.manifest import ManifestEntry, RepoManifest

PRIORITY_NAME_HINTS = (
    "auth",
    "login",
    "onboarding",
    "home",
    "page",
    "route",
    "api",
    "playwright",
    "config",
)


def _entry_score(entry: ManifestEntry) -> tuple[int, int, str]:
    name = entry.path.lower()
    hint_score = sum(2 for hint in PRIORITY_NAME_HINTS if hint in name)
    category_score = {
        "source": 4,
        "test": 3,
        "doc": 2,
        "config": 1,
        "workflow": 0,
    }.get(entry.category, 0)
    return (hint_score + category_score, entry.line_count, entry.path)


def select_component_entries(manifest: RepoManifest, limit_per_component: int = 3) -> dict[str, list[ManifestEntry]]:
    grouped: dict[str, list[ManifestEntry]] = defaultdict(list)
    for entry in manifest.entries:
        if entry.category not in {"source", "test", "doc"}:
            continue
        grouped[entry.component_key].append(entry)

    selected: dict[str, list[ManifestEntry]] = {}
    for component, entries in grouped.items():
        selected[component] = sorted(entries, key=_entry_score, reverse=True)[:limit_per_component]
    return selected


def hotspot_files(manifest: RepoManifest, *, limit: int = 5, min_lines: int = 120) -> list[str]:
    entries = [
        entry.path
        for entry in sorted(manifest.source_files, key=lambda entry: entry.line_count, reverse=True)[:limit]
        if entry.line_count >= min_lines
    ]
    return entries


def representative_file_context(
    repo_root: str | Path,
    manifest: RepoManifest,
    *,
    limit_per_component: int = 2,
    hotspot_limit: int = 3,
    max_chars: int = 700,
) -> list[dict[str, object]]:
    root = Path(repo_root)
    selected = select_component_entries(manifest, limit_per_component=limit_per_component)
    by_path = {entry.path: entry for entries in selected.values() for entry in entries}
    for hotspot in hotspot_files(manifest, limit=hotspot_limit):
        entry = next((item for item in manifest.entries if item.path == hotspot), None)
        if entry is not None:
            by_path.setdefault(entry.path, entry)

    contexts: list[dict[str, object]] = []
    for entry in sorted(by_path.values(), key=_entry_score, reverse=True):
        file_path = root / entry.path
        try:
            excerpt = file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars].strip()
        except OSError:
            excerpt = ""
        contexts.append(
            {
                "path": entry.path,
                "category": entry.category,
                "component_key": entry.component_key,
                "line_count": entry.line_count,
                "excerpt": excerpt,
            }
        )
    return contexts
