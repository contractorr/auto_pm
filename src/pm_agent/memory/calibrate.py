"""Calibrate deterministic synthesis scores using persisted priors."""

from __future__ import annotations

from pm_agent.models.contracts import AgentName, PMAgentMemory


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calibration_multiplier(
    surfaces: list[str],
    source_agents: list[AgentName],
    memory: PMAgentMemory | None,
) -> float:
    if memory is None:
        return 1.0

    priors: list[float] = []
    for agent in source_agents:
        agent_key = agent.value
        if agent_key in memory.source_priors:
            priors.append(memory.source_priors[agent_key])

    for surface in surfaces:
        if surface in memory.component_priors:
            priors.append(memory.component_priors[surface])

    if not priors:
        return 1.0

    average = sum(priors) / len(priors)
    return round(_clamp(0.85 + average * 0.3, 0.85, 1.15), 2)
