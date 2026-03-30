"""Simple registry for future agent wiring."""

from __future__ import annotations

from collections.abc import Iterable

from pm_agent.agents.base import BaseAgent
from pm_agent.models.contracts import AgentName


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[AgentName, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: AgentName) -> BaseAgent:
        return self._agents[name]

    def names(self) -> Iterable[AgentName]:
        return self._agents.keys()
