from pathlib import Path

from pm_agent.harness.loader import load_harness_scenarios
from pm_agent.models.contracts import AgentName


def test_harness_scenarios_load():
    scenarios = load_harness_scenarios(Path("tests/fixtures/harness"))
    assert len(scenarios) == 1
    assert scenarios[0].agent == AgentName.RESEARCH
