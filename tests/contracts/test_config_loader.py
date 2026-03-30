from pathlib import Path

from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import AuthStrategy, GitHubWriteMode, RuntimeMode


def test_example_config_parses():
    config = load_pm_config(Path("pm-config.example.yml"))
    assert config.repo.full_name == "contractorr/stewardme"
    assert config.runtime.mode == RuntimeMode.DOCKER_COMPOSE
    assert config.dogfooding.auth_strategy == AuthStrategy.TEST_AUTH
    assert config.github.write_mode == GitHubWriteMode.DISABLED
    assert len(config.dogfooding.journeys) == 1
