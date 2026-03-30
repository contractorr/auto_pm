from pathlib import Path

from pm_agent.config.loader import load_pm_config
from pm_agent.orchestration.fixtures import load_dry_run_fixture
from pm_agent.orchestration.runner import DryRunRunner


def test_dry_run_runner_produces_report():
    config = load_pm_config(Path("pm-config.example.yml"))
    fixture = load_dry_run_fixture(Path("tests/fixtures/pipeline/sample-dry-run.yaml"))
    report = DryRunRunner().run(Path("tests/fixtures/repos/sample-app"), config, fixture)

    assert report.capabilities.dogfooding_ready is True
    assert len(report.synthesis.proposals) == 1
    assert report.synthesis.proposals[0].dedup.action.value == "create"
