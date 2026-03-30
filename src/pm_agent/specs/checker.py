"""Check that the repository's required specs are present."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SpecManifest(BaseModel):
    required_specs: list[str] = Field(default_factory=list)


def load_spec_manifest(repo_root: str | Path) -> SpecManifest:
    root = Path(repo_root)
    manifest_path = root / "specs" / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return SpecManifest.model_validate(data)


def find_missing_specs(repo_root: str | Path) -> list[Path]:
    root = Path(repo_root)
    manifest = load_spec_manifest(root)
    return [root / spec for spec in manifest.required_specs if not (root / spec).exists()]
