from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.dogfooding import DogfoodingAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import (
    AuthStrategy,
    CredentialsAuthConfig,
    JourneyConfig,
    JourneyStepConfig,
    RuntimeMode,
    SecretValueConfig,
    TotpConfig,
)
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
    def __init__(self, base_url: str = "http://localhost:3000") -> None:
        self.session = FakeRuntimeSession(base_url=base_url)

    def launch(self, context: AgentExecutionContext) -> FakeRuntimeSession:
        return self.session


class FakeBrowserRunner:
    def __init__(self) -> None:
        self.last_request = None

    def run(self, request):
        self.last_request = request
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


def test_dogfooding_agent_limits_push_journeys_by_changed_files():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    config.dogfooding.journeys = [
        JourneyConfig(
            id="login-home",
            persona="junior_dev",
            start_path="/login",
            steps=[
                JourneyStepConfig(id="sign-in", action="sign_in_test_user", target="junior_dev"),
            ],
        ),
        JourneyConfig(
            id="settings-profile",
            persona="junior_dev",
            start_path="/settings",
            steps=[
                JourneyStepConfig(id="visit-settings", action="goto", target="/settings"),
            ],
        ),
    ]
    run = build_run_context(repo_root, config, trigger=Trigger.PUSH)
    capabilities = discover_repo_capabilities(repo_root, config)
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
        changed_files=["web/src/app/settings/page.tsx"],
    )
    runtime = FakeRuntimeLauncher()
    browser = FakeBrowserRunner()
    agent = DogfoodingAgent(runtime_launcher=runtime, browser_runner=browser)

    agent.run(context)

    assert browser.last_request is not None
    assert [journey.id for journey in browser.last_request.journeys] == ["settings-profile"]


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


def test_dogfooding_agent_passes_remote_credentials_to_browser_runner():
    repo_root = Path("tests/fixtures/repos/sample-app")
    config = load_pm_config(Path("pm-config.example.yml"))
    config.runtime.mode = RuntimeMode.EXTERNAL_URL
    config.runtime.compose_file = None
    config.runtime.start_commands = []
    config.runtime.service_urls = ["https://dogfood.example.com"]
    config.runtime.healthcheck_urls = []
    config.dogfooding.auth_strategy = AuthStrategy.CREDENTIALS
    config.dogfooding.credentials = CredentialsAuthConfig(
        username=SecretValueConfig(value="dogfood@example.com"),
        password=SecretValueConfig(value="super-secret"),
        totp=TotpConfig(secret=SecretValueConfig(value="JBSWY3DPEHPK3PXP")),
    )
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    context = AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )
    runtime = FakeRuntimeLauncher(base_url="https://dogfood.example.com")
    browser = FakeBrowserRunner()
    agent = DogfoodingAgent(runtime_launcher=runtime, browser_runner=browser)

    output = agent.run(context)

    assert output.base_url == "https://dogfood.example.com"
    assert browser.last_request is not None
    assert browser.last_request.base_url == "https://dogfood.example.com"
    assert browser.last_request.credentials == config.dogfooding.credentials
