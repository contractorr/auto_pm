"""Dry-run orchestration using local repo context plus fixture agent outputs."""

from __future__ import annotations

from pathlib import Path

from pm_agent.config.models import PMConfig
from pm_agent.memory.digest import build_memory_digest
from pm_agent.memory.store import load_memory
from pm_agent.models.contracts import SynthesisInput
from pm_agent.models.runtime import DryRunReport
from pm_agent.orchestration.artifacts import (
    build_agent_events,
    build_synthesis_events,
    collect_artifacts,
)
from pm_agent.orchestration.fixtures import DryRunFixture
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.product import load_product_context
from pm_agent.synthesis.engine import SynthesisEngine


class DryRunRunner:
    def __init__(self, synthesis_engine: SynthesisEngine | None = None) -> None:
        self._synthesis = synthesis_engine

    def run(self, repo_root: str | Path, config: PMConfig, fixture: DryRunFixture) -> DryRunReport:
        root = Path(repo_root)
        product = load_product_context(root / config.repo.product_file)
        capabilities = discover_repo_capabilities(root, config)
        memory = load_memory(root / config.repo.memory_file)
        synthesis_engine = self._synthesis or SynthesisEngine.from_config(config)
        synthesis_input = SynthesisInput(
            run=fixture.run,
            product=product,
            memory_digest=build_memory_digest(memory),
            research=fixture.research,
            codebase=fixture.codebase,
            dogfooding=fixture.dogfooding,
            existing_issues=fixture.existing_issues,
        )
        synthesis = synthesis_engine.run(
            synthesis_input,
            issue_policy=config.issue_policy,
            memory=memory,
            base_labels=config.github.labels,
        )
        outputs = [
            output
            for output in (
                fixture.research,
                fixture.codebase,
                fixture.dogfooding,
                fixture.existing_issues,
            )
            if output is not None
        ]
        events = [
            {
                "timestamp": fixture.run.started_at,
                "code": "dry_run_started",
                "message": "fixture-backed dry run started",
                "level": "info",
            }
        ]
        events.extend(event.model_dump(mode="python") for event in build_agent_events(outputs))
        events.extend(
            event.model_dump(mode="python")
            for event in build_synthesis_events(synthesis, timestamp=fixture.run.started_at)
        )
        return DryRunReport(
            run=fixture.run,
            product=product,
            capabilities=capabilities,
            agent_outputs=outputs,
            synthesis=synthesis,
            artifacts=collect_artifacts(outputs),
            events=events,
        )
