"""Deterministic repo manifest summarization."""

from __future__ import annotations

from collections import Counter, defaultdict

from pm_agent.models.contracts import ComponentSummary
from pm_agent.repo.manifest import ManifestEntry, RepoManifest
from pm_agent.repo.retrieval import select_component_entries


def _component_type(entries: list[ManifestEntry]) -> str:
    categories = {entry.category for entry in entries}
    paths = [entry.path.lower() for entry in entries]
    if any("/e2e/" in path or path.endswith("playwright.config.ts") for path in paths):
        return "e2e"
    if any(path.endswith((".tsx", ".jsx")) for path in paths):
        return "frontend"
    if any(path.endswith(".py") for path in paths):
        return "backend"
    if categories == {"doc"}:
        return "docs"
    return "shared"


def _responsibility_hints(entries: list[ManifestEntry], component_type: str) -> list[str]:
    path_text = " ".join(entry.path.lower() for entry in entries)
    hints: list[str] = []
    if component_type == "frontend":
        hints.append("Contains frontend views or UI logic.")
    elif component_type == "backend":
        hints.append("Contains backend or service logic.")
    elif component_type == "e2e":
        hints.append("Owns browser journey coverage and test automation.")
    else:
        hints.append("Contains shared application files.")

    if "auth" in path_text or "login" in path_text:
        hints.append("Likely handles authentication or sign-in flows.")
    if "onboarding" in path_text or "home" in path_text:
        hints.append("Touches early-session or onboarding surfaces.")
    return hints


def _risk_hints(entries: list[ManifestEntry], manifest: RepoManifest) -> list[str]:
    risks: list[str] = []
    if any(entry.category == "source" for entry in entries) and not any(
        entry.category == "test" for entry in entries
    ):
        risks.append("No nearby test files were detected for this component.")
    if any(entry.line_count >= 200 for entry in entries):
        risks.append("Contains relatively large files that may concentrate complexity.")
    if not manifest.doc_files:
        risks.append("Repository-level docs are sparse.")
    return risks


def summarize_components(manifest: RepoManifest, *, limit: int = 10) -> list[ComponentSummary]:
    selected = select_component_entries(manifest)
    grouped: dict[str, list[ManifestEntry]] = defaultdict(list)
    for entry in manifest.entries:
        grouped[entry.component_key].append(entry)

    components: list[ComponentSummary] = []
    for component_key, entries in sorted(grouped.items(), key=lambda item: item[0].lower()):
        if component_key == ".github":
            continue
        component_type = _component_type(entries)
        reps = selected.get(component_key, [])
        category_counts = Counter(entry.category for entry in entries)
        responsibilities = _responsibility_hints(reps or entries, component_type)
        responsibilities.append(
            f"Includes {category_counts.get('source', 0)} source files, "
            f"{category_counts.get('test', 0)} test files, and "
            f"{category_counts.get('doc', 0)} docs."
        )
        components.append(
            ComponentSummary(
                name=component_key.split("/")[-1],
                paths=[component_key],
                responsibilities=responsibilities,
                risks=_risk_hints(entries, manifest),
            )
        )
    return components[:limit]


def summarize_repo(manifest: RepoManifest, *, components: list[ComponentSummary]) -> str:
    dominant_components = ", ".join(path for component in components[:3] for path in component.paths) or "none"
    signals = ", ".join(manifest.framework_signals) or "no strong framework signals"
    return (
        f"Scanned {len(manifest.entries)} relevant files: "
        f"{len(manifest.source_files)} source, {len(manifest.test_files)} tests, "
        f"{len(manifest.doc_files)} docs, and {len(manifest.config_files)} config files. "
        f"Primary components: {dominant_components}. Detected signals: {signals}."
    )
