"""Deduplicate clusters against existing issues and PRs."""

from __future__ import annotations

import re

from pm_agent.models.contracts import DedupDecision, ExistingIssueRecord, IssueAction
from pm_agent.models.runtime import FindingCluster


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 4}


def _cluster_tokens(cluster: FindingCluster) -> set[str]:
    parts = [cluster.title, cluster.problem_statement, *cluster.tags, *cluster.novelty_keys]
    return {token for part in parts for token in _tokens(part)}


def _record_tokens(record: ExistingIssueRecord) -> set[str]:
    return _tokens(" ".join([record.title, record.body_summary, *record.labels]))


def _match_score(cluster: FindingCluster, record: ExistingIssueRecord) -> float:
    record_text = " ".join([record.title, record.body_summary, *record.labels]).lower()
    cluster_text = " ".join([cluster.title, cluster.problem_statement, *cluster.novelty_keys]).lower()
    normalized_title = re.sub(r"[^a-z0-9]+", " ", cluster.title.lower()).strip()
    normalized_record_title = re.sub(r"[^a-z0-9]+", " ", record.title.lower()).strip()
    if normalized_title and normalized_title == normalized_record_title:
        return 1.0
    for key in cluster.novelty_keys:
        normalized_key = re.sub(r"[^a-z0-9]+", " ", key.lower()).strip()
        if normalized_key and normalized_key in record_text:
            return 0.9

    left = _cluster_tokens(cluster)
    right = _record_tokens(record)
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    union = len(left | right)
    score = overlap / union if union else 0.0
    if cluster_text and cluster_text in record_text:
        return max(score, 0.8)
    return score


def deduplicate_cluster(
    cluster: FindingCluster,
    open_issues: list[ExistingIssueRecord],
    recent_closed_issues: list[ExistingIssueRecord],
    open_prs: list[ExistingIssueRecord],
) -> DedupDecision:
    best_open = max(open_issues, key=lambda record: _match_score(cluster, record), default=None)
    if best_open is not None and _match_score(cluster, best_open) >= 0.35:
        return DedupDecision(
            action=IssueAction.UPDATE_EXISTING,
            matched_issue_number=best_open.number,
            rationale=f"matched open issue #{best_open.number}",
        )

    best_pr = max(open_prs, key=lambda record: _match_score(cluster, record), default=None)
    if best_pr is not None and _match_score(cluster, best_pr) >= 0.35:
        return DedupDecision(
            action=IssueAction.COMMENT_EXISTING,
            matched_issue_number=best_pr.number,
            rationale=f"matched open PR #{best_pr.number}",
        )

    best_closed = max(
        recent_closed_issues,
        key=lambda record: _match_score(cluster, record),
        default=None,
    )
    if best_closed is not None and _match_score(cluster, best_closed) >= 0.45:
        return DedupDecision(
            action=IssueAction.COMMENT_EXISTING,
            matched_issue_number=best_closed.number,
            rationale=f"matched recently closed issue #{best_closed.number}",
        )

    return DedupDecision(
        action=IssueAction.NOOP,
        matched_issue_number=None,
        rationale="no sufficiently similar issue or PR found",
    )
