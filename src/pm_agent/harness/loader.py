"""Load harness scenarios from YAML fixtures."""

from __future__ import annotations

from pathlib import Path

import yaml

from pm_agent.harness.models import HarnessScenario


def load_harness_scenarios(path: str | Path) -> list[HarnessScenario]:
    root = Path(path)
    scenarios: list[HarnessScenario] = []
    for scenario_path in sorted(root.rglob("*.y*ml")):
        data = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
        scenarios.append(HarnessScenario.model_validate(data))
    return scenarios
