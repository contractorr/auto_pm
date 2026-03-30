from pathlib import Path

from pm_agent.config.loader import load_pm_config
from pm_agent.repo.manifest import build_repo_manifest
from pm_agent.repo.retrieval import hotspot_files, select_component_entries
from pm_agent.repo.summarizer import summarize_components, summarize_repo


def test_manifest_builds_component_structure_for_sample_repo():
    config = load_pm_config(Path("pm-config.example.yml"))
    manifest = build_repo_manifest(
        Path("tests/fixtures/repos/sample-app"),
        project_roots=config.repo.project_roots,
        ignore_paths=config.repo.ignore_paths,
    )

    component_keys = {entry.component_key for entry in manifest.entries}
    assert "web/src" in component_keys
    assert "web/e2e" in component_keys
    assert "docker-compose.yml" in {entry.path for entry in manifest.entries}
    assert "playwright-e2e" in manifest.framework_signals


def test_manifest_retrieval_and_summary_are_deterministic():
    config = load_pm_config(Path("pm-config.example.yml"))
    manifest = build_repo_manifest(
        Path("tests/fixtures/repos/sample-app"),
        project_roots=config.repo.project_roots,
        ignore_paths=config.repo.ignore_paths,
    )

    selected = select_component_entries(manifest)
    components = summarize_components(manifest)
    summary = summarize_repo(manifest, components=components)

    assert "web/src" in selected
    assert components
    assert "Primary components" in summary
    assert hotspot_files(manifest) == []
