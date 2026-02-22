from abc import ABC, abstractmethod
from typing import Mapping
from app.schemas.contracts import AgentSpec, TaskResult, TaskSpec

class BaseAgent(ABC):
    def __init__(self, spec: AgentSpec, tools: Mapping[str, any])-> None:
        self.spec = spec
        self.tools = dict(tools)

    @abstractmethod
    async def run(self, task: TaskSpec, context: dict[str, any]) -> TaskResult:
        raise NotImplementedError()

