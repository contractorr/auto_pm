from pathlib import Path

from pm_agent.specs.checker import find_missing_specs, load_spec_manifest


def test_spec_manifest_loads():
    manifest = load_spec_manifest(Path("."))
    assert manifest.required_specs


def test_spec_manifest_points_to_existing_files():
    assert find_missing_specs(Path(".")) == []
