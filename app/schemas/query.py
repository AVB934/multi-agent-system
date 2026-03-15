from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.contracts import PlanSpec, RunTrace, TaskResult


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1)
    include_json: bool = False


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str
    intent: str
    plan: PlanSpec
    task_results: list[TaskResult]
    trace: RunTrace
    json_payload: dict[str, object] | None = None