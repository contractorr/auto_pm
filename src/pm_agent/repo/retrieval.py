"""Heuristics for selecting representative files from a manifest."""

from __future__ import annotations

from collections import defaultdict

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
