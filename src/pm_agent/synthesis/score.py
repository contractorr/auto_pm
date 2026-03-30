"""Deterministic ICE scoring heuristics."""

from __future__ import annotations

import re

from pm_agent.memory.calibrate import calibration_multiplier
from pm_agent.models.contracts import ICEBreakdown, PMAgentMemory, ProductContext, Severity
from pm_agent.models.runtime import FindingCluster

SEVERITY_IMPACT = {
    Severity.LOW: 2.0,
    Severity.MEDIUM: 3.0,
    Severity.HIGH: 4.0,
    Severity.CRITICAL: 5.0,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _priority_keywords(product: ProductContext) -> set[str]:
    keywords: set[str] = set()
    for item in product.strategic_priorities:
        for token in re.findall(r"[a-z0-9]+", item.lower()):
            if len(token) >= 4:
                keywords.add(token)
    return keywords


def _strategic_match(cluster: FindingCluster, product: ProductContext) -> bool:
    keywords = _priority_keywords(product)
    if not keywords:
        return False
    haystack = " ".join(
        [
            cluster.title,
            cluster.problem_statement,
            cluster.user_impact,
            *cluster.tags,
            *cluster.affected_surfaces,
        ]
    ).lower()
    return any(keyword in haystack for keyword in keywords)


def score_cluster(
    cluster: FindingCluster,
    product: ProductContext,
    memory: PMAgentMemory | None,
) -> ICEBreakdown:
    strategic = _strategic_match(cluster, product)
    impact = _clamp(
        SEVERITY_IMPACT[cluster.severity]
        + min(1.0, 0.25 * max(0, len(cluster.affected_surfaces) - 1))
        + (0.5 if strategic else 0.0),
        1.0,
        5.0,
    )

    evidence_count = sum(len(finding.evidence) for finding in cluster.findings)
    confidence = _clamp(
        1.0
        + (cluster.average_confidence * 4.0)
        + (0.35 * max(0, cluster.convergence_count - 1))
        + min(0.3, evidence_count * 0.1),
        1.0,
        5.0,
    )

    ease_penalty = 0.4 * max(0, len(cluster.affected_surfaces) - 1)
    severity_penalty = {
        Severity.LOW: 0.0,
        Severity.MEDIUM: 0.25,
        Severity.HIGH: 0.6,
        Severity.CRITICAL: 1.0,
    }[cluster.severity]
    ease = _clamp(4.5 - ease_penalty - severity_penalty, 1.0, 5.0)

    ice_score = round(impact * confidence * ease, 2)
    convergence_multiplier = round(min(1.45, 1.0 + 0.15 * (cluster.convergence_count - 1)), 2)
    strategic_multiplier = 1.25 if strategic else 1.0
    calibration = calibration_multiplier(cluster.affected_surfaces, cluster.source_agents, memory)
    priority_score = round(
        ice_score * convergence_multiplier * strategic_multiplier * calibration,
        2,
    )

    rationale = (
        f"impact={impact:.2f} from severity {cluster.severity.value}; "
        f"confidence={confidence:.2f} from avg_confidence {cluster.average_confidence:.2f} "
        f"and convergence {cluster.convergence_count}; "
        f"ease={ease:.2f}; strategic_match={'yes' if strategic else 'no'}; "
        f"calibration={calibration:.2f}."
    )

    return ICEBreakdown(
        impact=round(impact, 2),
        confidence=round(confidence, 2),
        ease=round(ease, 2),
        ice_score=ice_score,
        convergence_multiplier=convergence_multiplier,
        strategic_multiplier=strategic_multiplier,
        calibration_multiplier=calibration,
        priority_score=priority_score,
        rationale=rationale,
    )
