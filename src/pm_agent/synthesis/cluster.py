"""Deterministic finding clustering."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from pm_agent.models.contracts import Finding, Severity
from pm_agent.models.runtime import FindingCluster

SEVERITY_ORDER = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def _canonicalize(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "uncategorized"


def _cluster_key(finding: Finding) -> str:
    if finding.dedup_keys:
        return _canonicalize(finding.dedup_keys[0])
    if finding.novelty_key:
        return _canonicalize(finding.novelty_key)
    return _canonicalize(finding.title)


def _cluster_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _representative(findings: list[Finding]) -> Finding:
    return max(
        findings,
        key=lambda finding: (
            SEVERITY_ORDER[finding.severity],
            finding.raw_confidence,
            len(finding.evidence),
        ),
    )


def build_clusters(findings: list[Finding]) -> list[FindingCluster]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[_cluster_key(finding)].append(finding)

    clusters: list[FindingCluster] = []
    for key, group in grouped.items():
        rep = _representative(group)
        clusters.append(
            FindingCluster(
                cluster_id=_cluster_id(key),
                title=rep.title,
                problem_statement=rep.problem_statement,
                user_impact=rep.user_impact,
                affected_surfaces=sorted({surface for finding in group for surface in finding.affected_surfaces}),
                tags=sorted({tag for finding in group for tag in finding.tags}),
                source_agents=sorted({finding.agent for finding in group}, key=lambda agent: agent.value),
                findings=group,
                convergence_count=len({finding.agent for finding in group}),
                severity=max(group, key=lambda finding: SEVERITY_ORDER[finding.severity]).severity,
                average_confidence=round(
                    sum(finding.raw_confidence for finding in group) / len(group), 2
                ),
                novelty_keys=sorted(
                    {key for finding in group for key in [finding.novelty_key, *finding.dedup_keys] if key}
                ),
            )
        )

    return sorted(clusters, key=lambda cluster: (cluster.title.lower(), cluster.cluster_id))
