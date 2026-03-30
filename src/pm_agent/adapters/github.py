"""Minimal GitHub REST adapter for issues and pull requests."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubAdapterError(RuntimeError):
    """Raised when GitHub API requests fail."""


class GitHubIssuesClient:
    def __init__(
        self,
        token: str | None = None,
        api_base_url: str = "https://api.github.com",
        user_agent: str = "auto-pm/0.1.0",
    ) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN")
        self._api_base_url = api_base_url.rstrip("/")
        self._user_agent = user_agent

    def _request(self, path: str, *, params: dict[str, Any] | None = None, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self._api_base_url}{path}{query}"
        body = None
        if data is not None:
            if not self._token:
                raise GitHubAdapterError("GitHub write operations require GITHUB_TOKEN")
            body = json.dumps(data).encode("utf-8")
        request = Request(
            url,
            method=method,
            data=body,
            headers={
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
                **({"Authorization": f"Bearer {self._token}"} if self._token else {}),
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GitHubAdapterError(f"GitHub API error {exc.code} for {url}") from exc
        except URLError as exc:
            raise GitHubAdapterError(f"GitHub API request failed for {url}: {exc.reason}") from exc
        return payload

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self._request(path, params=params)
        if not isinstance(payload, list):
            raise GitHubAdapterError(f"Unexpected GitHub API payload for {path}")
        return payload

    def _paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int = 1,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            page_params = {"page": page, "per_page": 100, **(params or {})}
            payload = self._request_json(path, page_params)
            if not payload:
                break
            items.extend(payload)
            if len(payload) < int(page_params["per_page"]):
                break
        return items

    def list_open_issues(self, owner: str, repo: str, max_pages: int = 1) -> list[dict[str, Any]]:
        items = self._paginate(f"/repos/{owner}/{repo}/issues", params={"state": "open"}, max_pages=max_pages)
        return [item for item in items if "pull_request" not in item]

    def list_recent_closed_issues(self, owner: str, repo: str, max_pages: int = 1) -> list[dict[str, Any]]:
        items = self._paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "closed", "sort": "updated", "direction": "desc"},
            max_pages=max_pages,
        )
        return [item for item in items if "pull_request" not in item]

    def list_open_pull_requests(self, owner: str, repo: str, max_pages: int = 1) -> list[dict[str, Any]]:
        return self._paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "sort": "updated", "direction": "desc"},
            max_pages=max_pages,
        )

    def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        payload = self._request(
            f"/repos/{owner}/{repo}/issues",
            method="POST",
            data={"title": title, "body": body, "labels": labels},
        )
        if not isinstance(payload, dict):
            raise GitHubAdapterError("Unexpected GitHub create issue payload")
        return payload

    def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if labels is not None:
            data["labels"] = labels
        if state is not None:
            data["state"] = state
        payload = self._request(
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            method="PATCH",
            data=data,
        )
        if not isinstance(payload, dict):
            raise GitHubAdapterError("Unexpected GitHub update issue payload")
        return payload

    def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        body: str,
    ) -> dict[str, Any]:
        payload = self._request(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            method="POST",
            data={"body": body},
        )
        if not isinstance(payload, dict):
            raise GitHubAdapterError("Unexpected GitHub create comment payload")
        return payload
