"""CLI utilities for spec-first development and harness validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from pm_agent.config.loader import load_pm_config
from pm_agent.config.models import GitHubWriteMode
from pm_agent.harness.loader import load_harness_scenarios
from pm_agent.harness.runner import HarnessRunner
from pm_agent.memory.store import load_memory, save_memory
from pm_agent.models.contracts import Trigger
from pm_agent.orchestration.fixtures import load_dry_run_fixture
from pm_agent.orchestration.lifecycle import apply_writeback_results_to_memory
from pm_agent.orchestration.live import LiveCollectionRunner
from pm_agent.orchestration.runner import DryRunRunner
from pm_agent.orchestration.writeback import GitHubWritebackApplier
from pm_agent.repo.discovery import discover_repo_capabilities
from pm_agent.specs.checker import find_missing_specs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    specs_parser = subparsers.add_parser("specs")
    specs_sub = specs_parser.add_subparsers(dest="subcommand", required=True)
    specs_check = specs_sub.add_parser("check")
    specs_check.add_argument("--root", default=".")

    config_parser = subparsers.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="subcommand", required=True)
    config_validate = config_sub.add_parser("validate")
    config_validate.add_argument("path")

    harness_parser = subparsers.add_parser("harness")
    harness_sub = harness_parser.add_subparsers(dest="subcommand", required=True)
    harness_validate = harness_sub.add_parser("validate")
    harness_validate.add_argument("--path", default="tests/fixtures/harness")

    discover_parser = subparsers.add_parser("discover")
    discover_sub = discover_parser.add_subparsers(dest="subcommand", required=True)
    discover_inspect = discover_sub.add_parser("inspect")
    discover_inspect.add_argument("--config", required=True)
    discover_inspect.add_argument("--repo-root", default=".")

    run_parser = subparsers.add_parser("run")
    run_sub = run_parser.add_subparsers(dest="subcommand", required=True)
    run_dry = run_sub.add_parser("dry")
    run_dry.add_argument("--config", required=True)
    run_dry.add_argument("--repo-root", default=".")
    run_dry.add_argument("--fixture", required=True)

    run_live = run_sub.add_parser("live")
    run_live.add_argument("--config", required=True)
    run_live.add_argument("--repo-root", default=".")
    run_live.add_argument(
        "--trigger",
        choices=[trigger.value for trigger in Trigger],
        default=Trigger.MANUAL.value,
    )
    run_live.add_argument(
        "--write-mode",
        choices=[mode.value for mode in GitHubWriteMode],
        default=None,
    )

    return parser


def _cmd_specs_check(root: str) -> int:
    missing = find_missing_specs(root)
    if missing:
        for path in missing:
            print(f"MISSING {path}")
        return 1
    print("All required specs are present.")
    return 0


def _cmd_config_validate(path: str) -> int:
    config = load_pm_config(path)
    print(
        f"Loaded config for {config.repo.full_name} with runtime {config.runtime.mode.value} "
        f"and {len(config.dogfooding.journeys)} dogfooding journeys."
    )
    return 0


def _cmd_harness_validate(path: str) -> int:
    runner = HarnessRunner()
    scenarios = load_harness_scenarios(path)
    results = runner.run_many(scenarios)
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.scenario_id}: {'; '.join(result.messages)}")
    return 1 if failed else 0


def _cmd_discover_inspect(config_path: str, repo_root: str) -> int:
    config = load_pm_config(config_path)
    snapshot = discover_repo_capabilities(repo_root, config)
    print(json.dumps(snapshot.model_dump(mode="json"), indent=2))
    return 0


def _cmd_run_dry(config_path: str, repo_root: str, fixture_path: str) -> int:
    config = load_pm_config(config_path)
    fixture = load_dry_run_fixture(fixture_path)
    report = DryRunRunner().run(Path(repo_root), config, fixture)
    print(
        json.dumps(
            {
                "repo": report.run.repo,
                "capabilities": report.capabilities.model_dump(mode="json"),
                "proposal_count": len(report.synthesis.proposals),
                "suppressed_count": len(report.synthesis.suppressed),
                "proposal_titles": [proposal.title for proposal in report.synthesis.proposals],
            },
            indent=2,
        )
    )
    return 0


def _cmd_run_live(config_path: str, repo_root: str, trigger: str, write_mode: str | None) -> int:
    config = load_pm_config(config_path)
    root = Path(repo_root)
    report = LiveCollectionRunner().run(
        root,
        config,
        trigger=Trigger(trigger),
        persist_memory=True,
    )
    effective_mode = GitHubWriteMode(write_mode) if write_mode else config.github.write_mode
    writeback = None
    if effective_mode != GitHubWriteMode.DISABLED:
        owner, repo = config.repo.full_name.split("/", 1)
        existing_issues_output = next(
            output
            for output in report.agent_outputs
            if output.agent.value == "existing_issues"
        )
        writeback = GitHubWritebackApplier().apply(
            owner=owner,
            repo=repo,
            proposals=report.synthesis.proposals,
            existing_issues=existing_issues_output,
            github_config=config.github,
            mode=effective_mode,
        )
        memory = load_memory(root / config.repo.memory_file)
        if memory is not None:
            memory = apply_writeback_results_to_memory(
                memory=memory,
                synthesis=report.synthesis,
                proposals=report.synthesis.proposals,
                writeback=writeback,
                now=report.run.started_at,
            )
            save_memory(root / config.repo.memory_file, memory)
    print(
        json.dumps(
            {
                "repo": report.run.repo,
                "branch": report.run.branch,
                "commit_sha": report.run.commit_sha,
                "capabilities": report.capabilities.model_dump(mode="json"),
                "agent_statuses": {
                    output.agent.value: output.status.value for output in report.agent_outputs
                },
                "agent_warnings": {
                    output.agent.value: [warning.message for warning in output.warnings]
                    for output in report.agent_outputs
                    if output.warnings
                },
                "proposal_count": len(report.synthesis.proposals),
                "suppressed_count": len(report.synthesis.suppressed),
                "proposal_titles": [proposal.title for proposal in report.synthesis.proposals],
                **(
                    {
                        "writeback_mode": writeback.mode,
                        "writeback_results": [result.model_dump(mode="json") for result in writeback.results],
                    }
                    if writeback is not None
                    else {}
                ),
            },
            indent=2,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "specs" and args.subcommand == "check":
        return _cmd_specs_check(args.root)
    if args.command == "config" and args.subcommand == "validate":
        return _cmd_config_validate(args.path)
    if args.command == "harness" and args.subcommand == "validate":
        return _cmd_harness_validate(args.path)
    if args.command == "discover" and args.subcommand == "inspect":
        return _cmd_discover_inspect(args.config, args.repo_root)
    if args.command == "run" and args.subcommand == "dry":
        return _cmd_run_dry(args.config, args.repo_root, args.fixture)
    if args.command == "run" and args.subcommand == "live":
        return _cmd_run_live(args.config, args.repo_root, args.trigger, args.write_mode)
    raise SystemExit("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
