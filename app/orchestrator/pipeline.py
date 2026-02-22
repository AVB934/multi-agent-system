
from app.schemas.contracts import AgentSpec, TaskResult, TaskSpec, PlanSpec
from app.schemas.query import QueryResponse
from app.orchestrator.agent_factory import AgentFactory
from app.orchestrator.agent_registory import AgentRegistry
from app.tools.web_search import StubWebSearchTool

class StubIntentClassifier:
    def classify(self, query: str) -> str:
        return "research" #TODO

class StubPlanner:
    async def plan(self, query: str, intent: str) -> PlanSpec:
        return PlanSpec(
            tasks = [
                TaskSpec(
                    task_id="researcher_agent_task",
                    description="Research facts for the query: " + query,
                    dependencies=[],
                    assined_agent="research",
                    required_tools=["web.search"]
                ),
                TaskSpec(
                    description=f"Verify the facts for the query: {query}, factual consistency and citation coverage" ,
                    dependencies=["researcher_agent_task"],
                    assined_agent="verifier",
                    required_tools=[]
                ),
            ]
        )

class StubExecutor:
    async def execute(self, plan: PlanSpec, trace: None) -> list[TaskResult]:
        return [
            TaskResult(
                task_id=task.task_id,
                status="success",
                output=f"Completed {task.description}",
                citations=[],
                error=None
            )
            for task in plan.tasks
        ]
    
class Orchestrator:
    def __init__(self, classifier : StubIntentClassifier =None, planner : StubPlanner =None, executor : StubExecutor =None):
        self._classifier = classifier or StubIntentClassifier()
        self._planner = planner or StubPlanner()
        self._executor = executor or StubExecutor()
        self._default_registry = AgentRegistry()
        self._factory = AgentFactory(self._default_registry, 
                                     available_tools={"web.search": StubWebSearchTool()}
            )
    async def run(self, query: str) -> QueryResponse:
        
        # TODO : Add trace throughout the pipeline

        intent = await self._classifier.classify(query)

        plan = await self._planner.plan(query, intent)

        task_results = await self._executor.execute(plan, trace=None)
        aggregated_result = await self.aggregate_results(plan, task_results)

        task_results, aggregated_result, post_verify = await self.verify_and_repair(plan, task_results, aggregated_result)

        answer = aggregated_result.get("answer", "No answer generated")
        citations = aggregated_result.get("citations", [])

        return QueryResponse(
            answer=answer,
            citations=citations,
            trace=None
        )

    

    async def aggregate_results(self, plan: PlanSpec, task_results: list[TaskResult]) -> dict[str, any]:
        pass

    async def verify_and_repair(self, plan: PlanSpec, task_results: list[TaskResult], aggregated_result: dict[str, any]) -> (list[TaskResult], dict[str, any], TaskResult):
        pass
        