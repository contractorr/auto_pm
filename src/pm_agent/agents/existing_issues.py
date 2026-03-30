"""GitHub-backed existing issues agent."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pm_agent.adapters.github import GitHubAdapterError, GitHubIssuesClient
from pm_agent.agents.base import AgentExecutionContext, BaseAgent
from pm_agent.models.contracts import (
    AgentName,
    AgentStatus,
    AgentWarning,
    ExistingIssueRecord,
    ExistingIssuesAgentOutput,
)

CLUSTER_RE = re.compile(r"cluster_id=([a-zA-Z0-9_-]+)")


def _split_repo(full_name: str) -> tuple[str, str]:
    owner, repo = full_name.split("/", 1)
    return owner, repo


def _ai_authored(item: dict[str, Any]) -> bool:
    labels = {label.get("name", "") for label in item.get("labels", [])}
    body = item.get("body") or ""
    return "ai-generated" in labels or "<!-- pm-agent:" in body


def _cluster_id(item: dict[str, Any]) -> str | None:
    body = item.get("body") or ""
    match = CLUSTER_RE.search(body)
    return match.group(1) if match else None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_record(item: dict[str, Any], state: str) -> ExistingIssueRecord:
    labels = [label.get("name", "") for label in item.get("labels", []) if label.get("name")]
    body = item.get("body") or ""
    return ExistingIssueRecord(
        number=item["number"],
        title=item["title"],
        state=state,  # type: ignore[arg-type]
        labels=labels,
        body_summary=body[:500],
        ai_authored=_ai_authored(item),
        cluster_id=_cluster_id(item),
        linked_prs=[],
        created_at=_parse_timestamp(item.get("created_at")),
        updated_at=_parse_timestamp(item.get("updated_at")),
        closed_at=_parse_timestamp(item.get("closed_at")),
    )


class ExistingIssuesAgent(BaseAgent):
    name = AgentName.EXISTING_ISSUES

    def __init__(self, client: GitHubIssuesClient | None = None, max_pages: int = 1) -> None:
        self._client = client or GitHubIssuesClient()
        self._max_pages = max_pages

    def run(self, context: AgentExecutionContext) -> ExistingIssuesAgentOutput:
        started_at = datetime.now(UTC)
        warnings: list[AgentWarning] = []
        owner, repo = _split_repo(context.config.repo.full_name)

        open_issues: list[ExistingIssueRecord] = []
        recent_closed_issues: list[ExistingIssueRecord] = []
        open_prs: list[ExistingIssueRecord] = []
        status = AgentStatus.SUCCESS

        try:
            open_issues = [
                _to_record(item, "open")
                for item in self._client.list_open_issues(owner, repo, max_pages=self._max_pages)
            ]
        except GitHubAdapterError as exc:
            status = AgentStatus.PARTIAL
            warnings.append(AgentWarning(code="github_open_issues_failed", message=str(exc)))

        try:
            recent_closed_issues = [
                _to_record(item, "closed")
                for item in self._client.list_recent_closed_issues(
                    owner, repo, max_pages=self._max_pages
                )
            ]
        except GitHubAdapterError as exc:
            status = AgentStatus.PARTIAL
            warnings.append(AgentWarning(code="github_closed_issues_failed", message=str(exc)))

        try:
            open_prs = [
                _to_record(item, "open")
                for item in self._client.list_open_pull_requests(owner, repo, max_pages=self._max_pages)
            ]
        except GitHubAdapterError as exc:
            status = AgentStatus.PARTIAL
            warnings.append(AgentWarning(code="github_open_prs_failed", message=str(exc)))

        return ExistingIssuesAgentOutput(
            agent=AgentName.EXISTING_ISSUES,
            status=status,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=warnings,
            findings=[],
            open_issues=open_issues,
            recent_closed_issues=recent_closed_issues,
            open_prs=open_prs,
        )
