"""Helpers for extracting git metadata from a checked-out repository."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pm_agent.config.models import PMConfig
from pm_agent.models.contracts import RunContext, Trigger


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def build_run_context(repo_root: str | Path, config: PMConfig, trigger: Trigger = Trigger.MANUAL) -> RunContext:
    root = Path(repo_root)
    branch = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD") or config.repo.default_branch
    commit_sha = _git_output(root, "rev-parse", "HEAD")
    config_hash = hashlib.sha1(
        json.dumps(config.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    started_at = datetime.now(UTC)
    run_id = started_at.strftime("run-%Y%m%d%H%M%S")
    return RunContext(
        run_id=run_id,
        repo=config.repo.full_name,
        branch=branch,
        commit_sha=commit_sha,
        trigger=trigger,
        started_at=started_at,
        config_hash=config_hash,
    )
