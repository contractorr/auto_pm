"""Build compact memory digests for synthesis inputs."""

from __future__ import annotations

from pm_agent.models.contracts import PMAgentMemory


def build_memory_digest(memory: PMAgentMemory | None) -> str:
    if memory is None or not memory.recent_outcomes:
        return "No prior AI issue outcome memory is available."

    disposition_counts: dict[str, int] = {}
    for outcome in memory.recent_outcomes:
        disposition_counts[outcome.disposition] = disposition_counts.get(outcome.disposition, 0) + 1

    top_sources = ", ".join(
        f"{key}={value:.2f}" for key, value in sorted(memory.source_priors.items())[:5]
    ) or "none"
    top_components = ", ".join(
        f"{key}={value:.2f}" for key, value in sorted(memory.component_priors.items())[:5]
    ) or "none"
    counts = ", ".join(f"{key}={value}" for key, value in sorted(disposition_counts.items()))
    tracked_issues = len(memory.issue_state)

    return (
        f"Recent outcomes: {counts}. "
        f"Source priors: {top_sources}. "
        f"Component priors: {top_components}. "
        f"Tracked open AI issues: {tracked_issues}."
    )
