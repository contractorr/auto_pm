"""Load repository configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

from pm_agent.config.models import PMConfig


def load_pm_config(path: str | Path) -> PMConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return PMConfig.model_validate(data)
