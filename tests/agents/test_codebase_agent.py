from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.codebase import CodebaseAgent
from pm_agent.agents.codebase_enhancer import CodebaseReviewResponse
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


class FakeCodebaseEnhancer:
    is_configured = True

    def review_codebase(self, **kwargs):
        return CodebaseReviewResponse.model_validate(
            {
                "repo_summary": "Model-backed summary highlights onboarding and authentication flows.",
                "components": [
                    {
                        "name": "web",
                        "paths": ["web/src"],
                        "responsibilities": [
                            "Owns onboarding and signed-in UI surfaces.",
                        ],
                        "risks": [
                            "Authentication and onboarding logic are concentrated here.",
                        ],
                    }
                ],
                "findings": [
                    {
                        "kind": "technical_risk",
                        "title": "Auth and onboarding logic are concentrated in the same frontend surface",
                        "problem_statement": "A small set of frontend files appear to own both auth and early-session behavior.",
                        "user_impact": "Changes in login or onboarding may create regressions in primary activation flows.",
                        "affected_surfaces": ["web/src"],
                        "severity": "medium",
                        "confidence": 0.74,
                        "summary": "Representative files suggest auth and onboarding responsibilities overlap in one component.",
                        "relevant_paths": ["web/src/lib/auth.ts"],
                        "tags": ["auth", "onboarding"],
                        "proposed_direction": "Split or better document early-session responsibilities before expanding flows.",
                    }
                ],
            }
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


def test_codebase_agent_uses_model_backed_review_when_enhancer_is_available():
    repo_root = Path("tests/fixtures/repos/sample-app")
    output = CodebaseAgent(enhancer=FakeCodebaseEnhancer()).run(_context_for(repo_root))  # type: ignore[arg-type]

    assert output.repo_summary == "Model-backed summary highlights onboarding and authentication flows."
    assert output.components[0].responsibilities == ["Owns onboarding and signed-in UI surfaces."]
    assert any(
        finding.title == "Auth and onboarding logic are concentrated in the same frontend surface"
        for finding in output.findings
    )


def test_codebase_agent_warns_when_anthropic_is_enabled_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    repo_root = Path("tests/fixtures/repos/sample-app")
    context = _context_for(repo_root)
    context.config.anthropic.enabled = True

    output = CodebaseAgent().run(context)

    assert any(warning.code == "anthropic_codebase_disabled" for warning in output.warnings)
