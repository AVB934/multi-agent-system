from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from app.schemas.contracts import AgentSpec, TaskResult, TaskSpec


class BaseAgent(ABC):
    """Runtime agent instance with explicitly scoped tool access."""

    def __init__(self, spec: AgentSpec, tools: Mapping[str, Any]) -> None:
        unauthorized = set(tools) - set(spec.allowed_tools)
        if unauthorized:
            raise ValueError(
                f"unauthorized tools for {spec.agent_id}: {sorted(unauthorized)}"
            )
        self.spec = spec
        self.tools = dict(tools)

    @abstractmethod
    async def run(
        self, task: TaskSpec, context: dict[str, Any] | None = None
    ) -> TaskResult:
        raise NotImplementedError
