from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.dogfooding import DogfoodingAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import (
    AgentName,
    JourneyRun,
    JourneyStepResult,
    ProductContext,
    Trigger,
)
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context


class FakeRuntimeSession:
    def __init__(self, base_url: str = "http://localhost:3000") -> None:
        self.base_url = base_url
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeRuntimeLauncher:
    def __init__(self) -> None:
        self.session = FakeRuntimeSession()

    def launch(self, context: AgentExecutionContext) -> FakeRuntimeSession:
        return self.session


class FakeBrowserRunner:
    def run(self, request):
        return [
            JourneyRun(
                journey_id="login-home",
                persona="junior_dev",
                success=False,
                started_at="2026-03-30T10:00:00Z",
                ended_at="2026-03-30T10:01:00Z",
                steps=[
                    JourneyStepResult(
                        step_id="sign-in",
                        action="sign_in_test_user",
                        url="http://localhost:3000/login",
                        success=False,
                        console_errors=["TypeError: failed"],
                        network_errors=["GET /api/profile net::ERR_FAILED"],
                        screenshot_path="artifacts/step.png",
                        accessibility_snapshot_path="artifacts/step-a11y.json",
                        vision_notes=["No visible h1 detected after step."],
                    )
                ],
            )
        ]


def test_dogfooding_agent_maps_runtime_and_browser_signals():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )
    runtime = FakeRuntimeLauncher()
    agent = DogfoodingAgent(runtime_launcher=runtime, browser_runner=FakeBrowserRunner())

    output = agent.run(context)

    assert output.status.value == "partial"
    assert runtime.session.stopped is True
    assert output.journeys[0].success is False
    kinds = {finding.kind.value for finding in output.findings}
    assert "reliability" in kinds
    assert "ux_bug" in kinds


def test_dogfooding_agent_skips_when_capabilities_not_ready():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    capabilities.dogfooding_ready = False
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )

    output = DogfoodingAgent().run(context)

    assert output.agent == AgentName.DOGFOODING
    assert output.status.value == "skipped"
