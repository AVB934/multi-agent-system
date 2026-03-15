from __future__ import annotations

from typing import Any, Mapping

from app.agents.base import BaseAgent
from app.orchestrator.agent_registry import AgentRegistry
from app.schemas.contracts import AgentSpec


class ToolScopeError(RuntimeError):
    pass


class AgentFactory:
    def __init__(self, registry: AgentRegistry, available_tools: Mapping[str, Any]) -> None:
        self.registry = registry
        self.available_tools = dict(available_tools)

    def create(self, template_id: str, agent_id: str | None = None) -> BaseAgent:
        template = self.registry.get(template_id)
        missing = [name for name in template.required_tools if name not in self.available_tools]
        if missing:
            raise ToolScopeError(
                f"cannot instantiate {template_id}; missing required tools: {sorted(missing)}"
            )

        scoped_tools = {
            tool_name: self.available_tools[tool_name] for tool_name in template.required_tools
        }
        spec = AgentSpec(
            agent_id=agent_id or f"{template_id}-runtime",
            role=template.role,
            allowed_tools=list(scoped_tools.keys()),
        )
        return template.agent_cls(spec=spec, tools=scoped_tools)
