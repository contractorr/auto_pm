"""Live collection orchestration for local repos plus GitHub issues."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.agents.codebase import CodebaseAgent
from pm_agent.agents.dogfooding import DogfoodingAgent
from pm_agent.agents.existing_issues import ExistingIssuesAgent
from pm_agent.agents.research import ResearchAgent
from pm_agent.config.models import PMConfig
from pm_agent.memory.digest import build_memory_digest
from pm_agent.memory.store import load_memory, save_memory
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    AgentWarning,
    CodebaseAgentOutput,
    DogfoodingAgentOutput,
    ExistingIssuesAgentOutput,
    ResearchAgentOutput,
    SynthesisInput,
    Trigger,
)
from pm_agent.models.runtime import DryRunReport, SynthesisReport
from pm_agent.orchestration.artifacts import (
    build_agent_events,
    build_synthesis_events,
    collect_artifacts,
)
from pm_agent.orchestration.lifecycle import plan_issue_lifecycle
from pm_agent.orchestration.locks import FileRunLock, RunLockError
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.repo.git import build_run_context, changed_files
from pm_agent.repo.product import load_product_context
from pm_agent.synthesis.engine import SynthesisEngine


def _issue_policy_for_trigger(config: PMConfig, trigger: Trigger):
    if trigger != Trigger.PUSH:
        return config.issue_policy
    return config.issue_policy.model_copy(
        update={
            "max_new_issues_per_run": min(1, config.issue_policy.max_new_issues_per_run),
        }
    )


def _skipped_research_output(context: AgentExecutionContext) -> ResearchAgentOutput:
    return ResearchAgentOutput(
        agent=AgentName.RESEARCH,
        status=AgentStatus.SKIPPED,
        started_at=context.run.started_at,
        ended_at=context.run.started_at,
        warnings=[],
        findings=[],
        competitors=[],
        papers=[],
    )


def _locked_outputs(run, message: str):
    warning = [AgentWarning(code="run_locked", message=message)]
    return [
        ResearchAgentOutput(
            agent=AgentName.RESEARCH,
            status=AgentStatus.SKIPPED,
            started_at=run.started_at,
            ended_at=run.started_at,
            warnings=warning,
            findings=[],
            competitors=[],
            papers=[],
        ),
        CodebaseAgentOutput(
            agent=AgentName.CODEBASE,
            status=AgentStatus.SKIPPED,
            started_at=run.started_at,
            ended_at=run.started_at,
            warnings=warning,
            findings=[],
            repo_summary="skipped because another run is active",
            components=[],
            changed_files=[],
            hotspot_files=[],
        ),
        DogfoodingAgentOutput(
            agent=AgentName.DOGFOODING,
            status=AgentStatus.SKIPPED,
            started_at=run.started_at,
            ended_at=run.started_at,
            warnings=warning,
            findings=[],
            runtime_mode="unknown",
            base_url=None,
            journeys=[],
        ),
        ExistingIssuesAgentOutput(
            agent=AgentName.EXISTING_ISSUES,
            status=AgentStatus.SKIPPED,
            started_at=run.started_at,
            ended_at=run.started_at,
            warnings=warning,
            findings=[],
            open_issues=[],
            recent_closed_issues=[],
            open_prs=[],
        ),
    ]


def _build_run_events(*, run, trigger: Trigger, agent_outputs, synthesis: SynthesisReport):
    events = [
        {
            "timestamp": run.started_at,
            "code": "run_started",
            "message": f"live run started with trigger={trigger.value}",
            "level": "info",
        }
    ]
    if trigger == Trigger.PUSH:
        events.append(
            {
                "timestamp": run.started_at,
                "code": "push_downshifted",
                "message": "push trigger downshifted research and issue budget",
                "level": "info",
            }
        )
    events.extend(event.model_dump(mode="python") for event in build_agent_events(agent_outputs))
    timestamp = max((output.ended_at for output in agent_outputs), default=run.started_at)
    events.extend(
        event.model_dump(mode="python")
        for event in build_synthesis_events(synthesis, timestamp=timestamp)
    )
    return events


def _run_collection_tasks(
    tasks: dict[str, Callable[[], object]],
) -> dict[str, object]:
    if not tasks:
        return {}
    with ThreadPoolExecutor(
        max_workers=min(4, len(tasks)),
        thread_name_prefix="live-collection",
    ) as executor:
        futures = {
            name: executor.submit(task)
            for name, task in tasks.items()
        }
        return {
            name: future.result()
            for name, future in futures.items()
        }


class LiveCollectionRunner:
    def __init__(
        self,
        *,
        research_agent: ResearchAgent | None = None,
        codebase_agent: CodebaseAgent | None = None,
        dogfooding_agent: DogfoodingAgent | None = None,
        existing_issues_agent: ExistingIssuesAgent | None = None,
        synthesis_engine: SynthesisEngine | None = None,
        run_lock: FileRunLock | None = None,
    ) -> None:
        self._research_agent = research_agent or ResearchAgent()
        self._codebase_agent = codebase_agent or CodebaseAgent()
        self._dogfooding_agent = dogfooding_agent or DogfoodingAgent()
        self._existing_issues_agent = existing_issues_agent or ExistingIssuesAgent()
        self._synthesis_engine = synthesis_engine
        self._run_lock = run_lock or FileRunLock()

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
        repo_changed_files = changed_files(root)
        context = AgentExecutionContext(
            run=run,
            product=product,
            config=config,
            repo_root=root,
            capabilities=capabilities,
            changed_files=repo_changed_files,
        )
        memory = load_memory(root / config.repo.memory_file)
        synthesis_engine = self._synthesis_engine or SynthesisEngine.from_config(config)
        issue_policy = _issue_policy_for_trigger(config, trigger)
        lease = None

        try:
            lease = self._run_lock.acquire(
                lock_path=root / ".pm-agent-run.lock",
                run_id=run.run_id,
                repo=config.repo.full_name,
                trigger=trigger.value,
            )
        except RunLockError as exc:
            message = str(exc)
            return DryRunReport(
                run=run,
                product=product,
                capabilities=capabilities,
                agent_outputs=_locked_outputs(run, message),
                synthesis=SynthesisReport(warnings=[f"run_locked: {message}"]),
                events=[
                    {
                        "timestamp": run.started_at,
                        "code": "run_locked",
                        "message": message,
                        "level": "warning",
                    }
                ],
            )

        try:
            task_results = _run_collection_tasks(
                {
                    **(
                        {}
                        if trigger == Trigger.PUSH
                        else {"research": lambda: self._research_agent.run(context)}
                    ),
                    "codebase": lambda: self._codebase_agent.run(context),
                    "dogfooding": lambda: self._dogfooding_agent.run(context),
                    "existing_issues": lambda: self._existing_issues_agent.run(context),
                }
            )
            research_output = (
                _skipped_research_output(context)
                if trigger == Trigger.PUSH
                else task_results["research"]
            )
            codebase_output = task_results["codebase"]
            dogfooding_output = task_results["dogfooding"]
            existing_issues_output = task_results["existing_issues"]

            synthesis_input = SynthesisInput(
                run=run,
                product=product,
                memory_digest=build_memory_digest(memory),
                research=research_output,
                codebase=codebase_output,
                dogfooding=dogfooding_output,
                existing_issues=existing_issues_output,
            )
            synthesis = synthesis_engine.run(
                synthesis_input,
                issue_policy=issue_policy,
                memory=memory,
                base_labels=config.github.labels,
            )
            lifecycle_proposals, updated_memory = plan_issue_lifecycle(
                synthesis=synthesis,
                existing_issues=existing_issues_output,
                issue_policy=issue_policy,
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
            agent_outputs = [
                research_output,
                codebase_output,
                dogfooding_output,
                existing_issues_output,
            ]
            return DryRunReport(
                run=run,
                product=product,
                capabilities=capabilities,
                agent_outputs=agent_outputs,
                synthesis=synthesis,
                artifacts=collect_artifacts(agent_outputs),
                events=_build_run_events(
                    run=run,
                    trigger=trigger,
                    agent_outputs=agent_outputs,
                    synthesis=synthesis,
                ),
            )
        finally:
            if lease is not None:
                lease.release()
