"""Live collection orchestration for local repos plus GitHub issues."""

from __future__ import annotations

from pathlib import Path

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.codebase import CodebaseAgent
from pm_agent.agents.dogfooding import DogfoodingAgent
from pm_agent.agents.existing_issues import ExistingIssuesAgent
from pm_agent.agents.research import ResearchAgent
from pm_agent.config.models import PMConfig
from pm_agent.memory.digest import build_memory_digest
from pm_agent.memory.store import load_memory, save_memory
from pm_agent.models.contracts import SynthesisInput, Trigger
from pm_agent.models.runtime import DryRunReport
from pm_agent.orchestration.lifecycle import plan_issue_lifecycle
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context
from pm_agent.repo.product import load_product_context
from pm_agent.synthesis.engine import SynthesisEngine


class LiveCollectionRunner:
    def __init__(
        self,
        *,
        research_agent: ResearchAgent | None = None,
        codebase_agent: CodebaseAgent | None = None,
        dogfooding_agent: DogfoodingAgent | None = None,
        existing_issues_agent: ExistingIssuesAgent | None = None,
        synthesis_engine: SynthesisEngine | None = None,
    ) -> None:
        self._research_agent = research_agent or ResearchAgent()
        self._codebase_agent = codebase_agent or CodebaseAgent()
        self._dogfooding_agent = dogfooding_agent or DogfoodingAgent()
        self._existing_issues_agent = existing_issues_agent or ExistingIssuesAgent()
        self._synthesis_engine = synthesis_engine or SynthesisEngine()

    def run(
        self,
        repo_root: str | Path,
        config: PMConfig,
        *,
        trigger: Trigger = Trigger.MANUAL,
        persist_memory: bool = False,
    ) -> DryRunReport:
        root = Path(repo_root)
        product = load_product_context(root / config.repo.product_file)
        capabilities = discover_repo_capabilities(root, config)
        run = build_run_context(root, config, trigger=trigger)
        context = AgentExecutionContext(
            run=run,
            product=product,
            config=config,
            repo_root=root,
            capabilities=capabilities,
        )
        memory = load_memory(root / config.repo.memory_file)

        research_output = self._research_agent.run(context)
        codebase_output = self._codebase_agent.run(context)
        dogfooding_output = self._dogfooding_agent.run(context)
        existing_issues_output = self._existing_issues_agent.run(context)

        synthesis_input = SynthesisInput(
            run=run,
            product=product,
            memory_digest=build_memory_digest(memory),
            research=research_output,
            codebase=codebase_output,
            dogfooding=dogfooding_output,
            existing_issues=existing_issues_output,
        )
        synthesis = self._synthesis_engine.run(
            synthesis_input,
            issue_policy=config.issue_policy,
            memory=memory,
            base_labels=config.github.labels,
        )
        lifecycle_proposals, updated_memory = plan_issue_lifecycle(
            synthesis=synthesis,
            existing_issues=existing_issues_output,
            issue_policy=config.issue_policy,
            github_config=config.github,
            memory=memory,
            run_started_at=run.started_at,
            base_labels=config.github.labels,
        )
        if lifecycle_proposals:
            synthesis.proposals = sorted(
                [*synthesis.proposals, *lifecycle_proposals],
                key=lambda proposal: proposal.ice.priority_score,
                reverse=True,
            )
        if persist_memory:
            save_memory(root / config.repo.memory_file, updated_memory)
        return DryRunReport(
            run=run,
            product=product,
            capabilities=capabilities,
            agent_outputs=[research_output, codebase_output, dogfooding_output, existing_issues_output],
            synthesis=synthesis,
        )
