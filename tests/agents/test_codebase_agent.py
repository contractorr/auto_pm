from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.codebase import CodebaseAgent
from pm_agent.config.loader import load_pm_config
from pm_agent.models.contracts import ProductContext, Trigger
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context


def _context_for(repo_root: Path):
    config = load_pm_config(Path("pm-config.example.yml"))
    run = build_run_context(repo_root, config, trigger=Trigger.MANUAL)
    capabilities = discover_repo_capabilities(repo_root, config)
    return AgentExecutionContext(
        run=run,
        product=ProductContext(vision="Improve onboarding."),
        config=config,
        repo_root=repo_root,
        capabilities=capabilities,
    )


def test_codebase_agent_builds_manifest_based_summary_for_sample_repo():
    repo_root = Path("tests/fixtures/repos/sample-app")
    context = _context_for(repo_root)

    output = CodebaseAgent().run(context)

    assert output.repo_summary
    assert "Primary components" in output.repo_summary
    assert {path for component in output.components for path in component.paths} >= {"web/src", "web/e2e"}
    assert "missing-tests" not in {key for finding in output.findings for key in finding.dedup_keys}


def test_codebase_agent_emits_missing_tests_for_repo_without_test_signals(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "PRODUCT.md").write_text("# Product Vision\n\nTest vision\n", encoding="utf-8")

    output = CodebaseAgent().run(_context_for(tmp_path))

    assert "missing-tests" in {key for finding in output.findings for key in finding.dedup_keys}
