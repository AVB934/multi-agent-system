from typing import Any

from app.agents.base import BaseAgent
from app.schemas.contracts import AgentSpec, TaskResult, TaskSpec, SearchResult
from app.tools.base import BaseTool

class ResearchAgent(BaseAgent):
    async def run(self, task: TaskSpec, context: dict[str, Any]) -> TaskResult:
        search_tool = self.tools.get("web.search")

        results : list[SearchResult] = await search_tool.run(task.description)
        citations = [item.url for item in results]
        # TODO
        combined_result = None
        return TaskResult(
            task_id=task.task_id,
            status="success",
            output=combined_result,
            citations=citations
        )
    
class VerfierAgent(BaseAgent):
    pass

class PlannerAgent(BaseAgent):
    pass

