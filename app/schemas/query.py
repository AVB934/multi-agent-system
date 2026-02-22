from pydantic import BaseModel, Field, ConfigDict
from app.schemas.contracts import RunTrace, PlanSpec, TaskResult

class QueryRequest(BaseModel):
    query: str
    model_config = ConfigDict(strict=True, extra='allow')

class QueryResponse(BaseModel):
    answer: str
    plan: PlanSpec
    trace: RunTrace
    task_results: list[TaskResult]
    model_config = ConfigDict(strict=True, extra='forbid')