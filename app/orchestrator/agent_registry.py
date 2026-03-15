from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.agents.base import BaseAgent
from app.agents.baseline import PlannerAgent, ResearchAgent, VerifierAgent


@dataclass(frozen=True)
class AgentTemplate:
    template_id: str
    role: str
    agent_cls: type[BaseAgent]
    required_tools: tuple[str, ...] = ()


class AgentRegistry:
    def __init__(self, templates: Iterable[AgentTemplate] | None = None) -> None:
        self._templates: dict[str, AgentTemplate] = {}
        for template in templates or []:
            self.register(template)

    @classmethod
    def with_defaults(cls) -> "AgentRegistry":
        return cls(
            templates=(
                AgentTemplate(
                    template_id="planner",
                    role="planning",
                    agent_cls=PlannerAgent,
                    required_tools=("llm.adk",),
                ),
                AgentTemplate(
                    template_id="research",
                    role="research",
                    agent_cls=ResearchAgent,
                    required_tools=("web.search", "llm.adk"),
                ),
                AgentTemplate(
                    template_id="verifier",
                    role="verification",
                    agent_cls=VerifierAgent,
                    required_tools=("llm.adk", "web.search"),
                ),
            )
        )

    def register(self, template: AgentTemplate) -> None:
        if template.template_id in self._templates:
            raise ValueError(f"template already registered: {template.template_id}")
        self._templates[template.template_id] = template

    def get(self, template_id: str) -> AgentTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise KeyError(f"unknown template: {template_id}") from exc

    def list_templates(self) -> list[AgentTemplate]:
        return list(self._templates.values())
