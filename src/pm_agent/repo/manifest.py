"""Local repository manifest building and classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

RELEVANT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
DOC_SUFFIXES = {".md"}
CONFIG_SUFFIXES = {".yml", ".yaml", ".json", ".toml"}
TEST_MARKERS = ("test", "spec", "e2e")


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    suffix: str
    category: str
    line_count: int
    component_key: str


@dataclass(frozen=True)
class RepoManifest:
    repo_root: str
    entries: list[ManifestEntry] = field(default_factory=list)
    source_files: list[ManifestEntry] = field(default_factory=list)
    test_files: list[ManifestEntry] = field(default_factory=list)
    doc_files: list[ManifestEntry] = field(default_factory=list)
    config_files: list[ManifestEntry] = field(default_factory=list)
    workflow_files: list[ManifestEntry] = field(default_factory=list)
    framework_signals: list[str] = field(default_factory=list)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def _is_ignored(relative_path: Path, ignore_paths: list[Path]) -> bool:
    relative_parts = relative_path.parts
    for ignore_path in ignore_paths:
        ignore_parts = ignore_path.parts
        if ignore_parts and relative_parts[: len(ignore_parts)] == ignore_parts:
            return True
    return False


def _category_for(relative_path: Path) -> str:
    path_text = relative_path.as_posix().lower()
    suffix = relative_path.suffix.lower()
    if ".github/workflows/" in path_text:
        return "workflow"
    if any(marker in path_text for marker in TEST_MARKERS):
        return "test"
    if suffix in DOC_SUFFIXES:
        return "doc"
    if suffix in SOURCE_SUFFIXES:
        return "source"
    if suffix in CONFIG_SUFFIXES:
        return "config"
    return "other"


def _component_key(relative_path: Path) -> str:
    parts = relative_path.parts
    if not parts:
        return "."
    if parts[0] == ".github":
        return ".github"
    if len(parts) >= 2 and parts[1] in {
        "src",
        "app",
        "pages",
        "e2e",
        "tests",
        "test",
        "server",
        "backend",
        "frontend",
        "api",
    }:
        return "/".join(parts[:2])
    if parts[0] in {"src", "app", "pages", "tests", "test", "e2e"} and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _framework_signals(entries: list[ManifestEntry]) -> list[str]:
    paths = [entry.path.lower() for entry in entries]
    signals: set[str] = set()
    if any(path.endswith((".tsx", ".jsx")) for path in paths):
        signals.add("react-like-ui")
    if any("/app/" in path or path.startswith("app/") for path in paths):
        signals.add("app-router-like-frontend")
    if any("/e2e/" in path or "playwright.config." in path for path in paths):
        signals.add("playwright-e2e")
    if any(path.endswith(".py") for path in paths):
        signals.add("python-service")
    if any("docker-compose" in path for path in paths):
        signals.add("docker-compose")
    if any(path.startswith(".github/workflows/") for path in paths):
        signals.add("github-actions")
    return sorted(signals)


def build_repo_manifest(
    repo_root: str | Path,
    *,
    project_roots: list[Path],
    ignore_paths: list[Path],
) -> RepoManifest:
    root = Path(repo_root).resolve()
    entries: list[ManifestEntry] = []

    for project_root in project_roots:
        scan_root = (root / project_root).resolve()
        if not scan_root.exists() or not scan_root.is_dir():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(root)
            if _is_ignored(relative_path, ignore_paths):
                continue
            if path.suffix.lower() not in RELEVANT_SUFFIXES:
                continue
            category = _category_for(relative_path)
            entries.append(
                ManifestEntry(
                    path=relative_path.as_posix(),
                    suffix=path.suffix.lower(),
                    category=category,
                    line_count=_line_count(path),
                    component_key=_component_key(relative_path),
                )
            )

    source_files = [entry for entry in entries if entry.category == "source"]
    test_files = [entry for entry in entries if entry.category == "test"]
    doc_files = [entry for entry in entries if entry.category == "doc"]
    config_files = [entry for entry in entries if entry.category == "config"]
    workflow_files = [entry for entry in entries if entry.category == "workflow"]

    return RepoManifest(
        repo_root=str(root.resolve()),
        entries=sorted(entries, key=lambda entry: entry.path),
        source_files=sorted(source_files, key=lambda entry: entry.path),
        test_files=sorted(test_files, key=lambda entry: entry.path),
        doc_files=sorted(doc_files, key=lambda entry: entry.path),
        config_files=sorted(config_files, key=lambda entry: entry.path),
        workflow_files=sorted(workflow_files, key=lambda entry: entry.path),
        framework_signals=_framework_signals(entries),
    )
