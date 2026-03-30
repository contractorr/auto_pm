from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.codebase import CodebaseAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import ProductContext, Trigger
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context


def test_codebase_agent_emits_missing_tests_finding_for_sparse_repo():
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

    output = CodebaseAgent().run(context)

    assert output.repo_summary
    assert "missing-tests" in {key for finding in output.findings for key in finding.dedup_keys}
    assert output.components
