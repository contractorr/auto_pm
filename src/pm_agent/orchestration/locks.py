"""Run locking helpers for autonomous live execution."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


class RunLockError(RuntimeError):
    """Raised when a live run cannot acquire the repository lock."""


@dataclass(frozen=True)
class RunLease:
    lock_path: Path
    token: str

    def release(self) -> None:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None

        if isinstance(payload, dict) and payload.get("token") != self.token:
            return

        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return


class FileRunLock:
    def __init__(self, *, stale_after_seconds: int = 6 * 60 * 60) -> None:
        self._stale_after = stale_after_seconds

    def acquire(
        self,
        *,
        lock_path: str | Path,
        run_id: str,
        repo: str,
        trigger: str,
    ) -> RunLease:
        path = Path(lock_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_if_stale(path)

        token = uuid.uuid4().hex
        payload = {
            "token": token,
            "run_id": run_id,
            "repo": repo,
            "trigger": trigger,
            "created_at": datetime.now(UTC).isoformat(),
        }
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            message = self._describe_existing_lock(path)
            raise RunLockError(message) from exc

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise

        return RunLease(lock_path=path, token=token)

    def _clear_if_stale(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return

        created_at_raw = payload.get("created_at")
        if not isinstance(created_at_raw, str):
            path.unlink(missing_ok=True)
            return

        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            path.unlink(missing_ok=True)
            return

        if datetime.now(UTC) - created_at > timedelta(seconds=self._stale_after):
            path.unlink(missing_ok=True)

    def _describe_existing_lock(self, path: Path) -> str:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return f"another pm-agent run is already active ({path.as_posix()})"

        run_id = payload.get("run_id", "unknown")
        trigger = payload.get("trigger", "unknown")
        created_at = payload.get("created_at", "unknown")
        return (
            "another pm-agent run is already active "
            f"(run_id={run_id}, trigger={trigger}, created_at={created_at})"
        )
