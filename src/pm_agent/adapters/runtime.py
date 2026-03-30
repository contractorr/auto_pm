"""Runtime launchers for dogfooding sessions."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import urlopen

from pm_agent.agents.base import AgentExecutionContext
from pm_agent.config.models import RuntimeMode


class RuntimeAdapterError(RuntimeError):
    """Raised when runtime setup fails."""


@dataclass
class RuntimeSession:
    base_url: str | None
    stop_commands: list[list[str]] = field(default_factory=list)
    processes: list[subprocess.Popen[str]] = field(default_factory=list)

    def stop(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for command in self.stop_commands:
            subprocess.run(command, check=False)


class LocalRuntimeLauncher:
    """Start repo-local runtime dependencies and wait for health checks."""

    def launch(self, context: AgentExecutionContext) -> RuntimeSession:
        mode = context.config.runtime.mode
        base_url = context.config.runtime.service_urls[0] if context.config.runtime.service_urls else None
        session = RuntimeSession(base_url=base_url)

        if mode in {RuntimeMode.PREVIEW_URL, RuntimeMode.EXTERNAL_URL, RuntimeMode.DISABLED}:
            self._wait_for_healthchecks(context)
            return session

        if mode == RuntimeMode.DOCKER_COMPOSE:
            compose_file = context.config.runtime.compose_file
            if compose_file is None:
                raise RuntimeAdapterError("docker_compose mode requires compose_file")
            command = [
                "docker",
                "compose",
                "-f",
                str(context.repo_root / compose_file),
                "up",
                "-d",
                "--build",
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=context.repo_root,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeAdapterError("docker CLI is not installed or not on PATH") from exc
            if result.returncode != 0:
                raise RuntimeAdapterError(result.stderr.strip() or "docker compose up failed")
            session.stop_commands.append(
                ["docker", "compose", "-f", str(context.repo_root / compose_file), "down"]
            )
            self._wait_for_healthchecks(context)
            return session

        if mode == RuntimeMode.COMMANDS:
            for command in context.config.runtime.start_commands:
                process = subprocess.Popen(
                    command,
                    cwd=context.repo_root,
                    shell=True,
                    text=True,
                )
                session.processes.append(process)
            self._wait_for_healthchecks(context)
            return session

        raise RuntimeAdapterError(f"unsupported runtime mode: {mode.value}")

    def _wait_for_healthchecks(self, context: AgentExecutionContext) -> None:
        urls = context.config.runtime.healthcheck_urls
        if not urls:
            return

        deadline = time.monotonic() + context.config.runtime.healthcheck_timeout_seconds
        pending = set(urls)
        while pending and time.monotonic() < deadline:
            done: list[str] = []
            for url in pending:
                try:
                    with urlopen(url, timeout=5) as response:
                        if 200 <= response.status < 400:
                            done.append(url)
                except URLError:
                    continue
            for url in done:
                pending.discard(url)
            if pending:
                time.sleep(2)

        if pending:
            raise RuntimeAdapterError(
                "health checks did not pass: " + ", ".join(sorted(pending))
            )
