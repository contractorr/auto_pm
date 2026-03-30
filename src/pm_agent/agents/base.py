"""Base contracts for pluggable agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from pm_agent.config.models import PMConfig
from pm_agent.models.contracts import AgentEnvelope, AgentName, ProductContext, RunContext
from pm_agent.models.runtime import CapabilitySnapshot


class AgentExecutionContext(BaseModel):
    run: RunContext
    product: ProductContext
    config: PMConfig
    repo_root: Path
    capabilities: CapabilitySnapshot | None = None
    changed_files: list[str] = []


class BaseAgent(ABC):
    """Base class for future collection and synthesis agents."""

    name: AgentName

    @abstractmethod
    def run(self, context: AgentExecutionContext) -> AgentEnvelope:
        """Run the agent and return a typed envelope."""
