"""Apply synthesized proposals to GitHub under explicit safety modes."""

from __future__ import annotations

from pm_agent.adapters.github import GitHubAdapterError, GitHubIssuesClient
from pm_agent.config.models import GitHubConfig, GitHubWriteMode
from pm_agent.models.contracts import (
    ExistingIssueRecord,
    ExistingIssuesAgentOutput,
    IssueAction,
    IssueProposal,
)
from pm_agent.models.runtime import WritebackActionResult, WritebackReport


def render_proposal_comment(proposal: IssueProposal) -> str:
    return "\n".join(
        [
            "PM agent follow-up:",
            "",
            f"- Proposed action: {proposal.dedup.action.value}",
            f"- Priority score: {proposal.ice.priority_score:.2f}",
            f"- Summary: {proposal.summary}",
            "",
            proposal.issue_body_markdown or "",
        ]
    ).strip()


class GitHubWritebackApplier:
    def __init__(self, client: GitHubIssuesClient | None = None) -> None:
        self._client = client or GitHubIssuesClient()

    def apply(
        self,
        *,
        owner: str,
        repo: str,
        proposals: list[IssueProposal],
        existing_issues: ExistingIssuesAgentOutput,
        github_config: GitHubConfig,
        mode: GitHubWriteMode | None = None,
    ) -> WritebackReport:
        effective_mode = mode or github_config.write_mode
        if effective_mode == GitHubWriteMode.DISABLED:
            return WritebackReport(
                mode=effective_mode.value,
                results=[
                    WritebackActionResult(
                        cluster_id=proposal.cluster_id,
                        proposal_title=proposal.title,
                        action=proposal.dedup.action.value,
                        outcome="planned",
                        target_number=proposal.dedup.matched_issue_number,
                        message="writeback disabled",
                    )
                    for proposal in proposals
                ],
            )

        records = {
            record.number: record
            for record in [
                *existing_issues.open_issues,
                *existing_issues.recent_closed_issues,
                *existing_issues.open_prs,
            ]
        }

        results: list[WritebackActionResult] = []
        for proposal in proposals:
            try:
                results.append(
                    self._apply_one(
                        owner=owner,
                        repo=repo,
                        proposal=proposal,
                        existing_record=records.get(proposal.dedup.matched_issue_number),
                        github_config=github_config,
                        mode=effective_mode,
                    )
                )
            except GitHubAdapterError as exc:
                results.append(
                    WritebackActionResult(
                        cluster_id=proposal.cluster_id,
                        proposal_title=proposal.title,
                        action=proposal.dedup.action.value,
                        outcome="failed",
                        target_number=proposal.dedup.matched_issue_number,
                        message=str(exc),
                    )
                )

        return WritebackReport(mode=effective_mode.value, results=results)

    def _apply_one(
        self,
        *,
        owner: str,
        repo: str,
        proposal: IssueProposal,
        existing_record: ExistingIssueRecord | None,
        github_config: GitHubConfig,
        mode: GitHubWriteMode,
    ) -> WritebackActionResult:
        action = proposal.dedup.action
        target = proposal.dedup.matched_issue_number

        if action == IssueAction.CREATE:
            if mode == GitHubWriteMode.COMMENT_ONLY:
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="skipped",
                    target_number=None,
                    message="comment_only mode does not create issues",
                )
            created = self._client.create_issue(
                owner,
                repo,
                title=proposal.title,
                body=proposal.issue_body_markdown or proposal.summary,
                labels=proposal.labels,
            )
            return WritebackActionResult(
                cluster_id=proposal.cluster_id,
                proposal_title=proposal.title,
                action=action.value,
                outcome="created",
                target_number=created.get("number"),
                message="created new issue",
            )

        if action in {IssueAction.UPDATE_EXISTING, IssueAction.COMMENT_EXISTING}:
            if target is None:
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="skipped",
                    message="no matched issue number",
                )

            should_update_body = (
                mode == GitHubWriteMode.APPLY
                and action == IssueAction.UPDATE_EXISTING
                and existing_record is not None
                and (
                    existing_record.ai_authored
                    or not github_config.update_ai_authored_issues_only
                )
            )
            if should_update_body:
                self._client.update_issue(
                    owner,
                    repo,
                    target,
                    title=proposal.title,
                    body=proposal.issue_body_markdown or proposal.summary,
                    labels=proposal.labels,
                )
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="updated",
                    target_number=target,
                    message="updated existing AI-authored issue",
                )

            self._client.create_issue_comment(
                owner,
                repo,
                target,
                body=render_proposal_comment(proposal),
            )
            return WritebackActionResult(
                cluster_id=proposal.cluster_id,
                proposal_title=proposal.title,
                action=action.value,
                outcome="commented",
                target_number=target,
                message="added comment to existing issue or PR",
            )

        if action == IssueAction.CLOSE_EXISTING:
            if target is None:
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="skipped",
                    message="no matched issue number",
                )
            if mode != GitHubWriteMode.APPLY:
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="skipped",
                    target_number=target,
                    message="close actions require apply mode",
                )
            if github_config.update_ai_authored_issues_only and existing_record is not None and not existing_record.ai_authored:
                return WritebackActionResult(
                    cluster_id=proposal.cluster_id,
                    proposal_title=proposal.title,
                    action=action.value,
                    outcome="skipped",
                    target_number=target,
                    message="refusing to close non-AI-authored issue",
                )
            self._client.update_issue(owner, repo, target, state="closed")
            return WritebackActionResult(
                cluster_id=proposal.cluster_id,
                proposal_title=proposal.title,
                action=action.value,
                outcome="closed",
                target_number=target,
                message="closed issue",
            )

        return WritebackActionResult(
            cluster_id=proposal.cluster_id,
            proposal_title=proposal.title,
            action=action.value,
            outcome="skipped",
            target_number=target,
            message="no writeback action taken",
        )
