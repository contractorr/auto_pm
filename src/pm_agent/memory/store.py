"""Load and persist PM agent memory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pm_agent.models.contracts import PMAgentMemory


def load_memory(path: str | Path) -> PMAgentMemory | None:
    memory_path = Path(path)
    if not memory_path.exists():
        return None
    data = json.loads(memory_path.read_text(encoding="utf-8"))
    return PMAgentMemory.model_validate(data)


def create_memory(*, now: datetime | None = None) -> PMAgentMemory:
    return PMAgentMemory(updated_at=now or datetime.now(UTC))


def save_memory(path: str | Path, memory: PMAgentMemory) -> None:
    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        json.dumps(memory.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
