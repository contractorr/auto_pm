from pathlib import Path


def test_local_only_repo_files_are_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "PRODUCT.md" in gitignore
    assert "pm-config.yml" in gitignore
    assert ".github/pm-agent-memory.json" in gitignore


def test_workflow_scaffolding_exists():
    assert Path(".github/workflows/ci.yml").exists()
    assert Path(".github/workflows/reusable-pm-agent.yml").exists()
