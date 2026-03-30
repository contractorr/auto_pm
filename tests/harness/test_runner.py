from pathlib import Path

from pm_agent.harness.loader import load_harness_scenarios
from pm_agent.harness.runner import HarnessRunner


def test_harness_runner_passes_sample_scenario():
    scenario = load_harness_scenarios(Path("tests/fixtures/harness"))[0]
    result = HarnessRunner().evaluate(scenario)
    assert result.passed is True
    assert result.messages == ["ok"]
