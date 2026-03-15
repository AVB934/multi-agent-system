from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskSpec(StrictModel):
    task_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    assigned_agent: str = Field(min_length=1)
    required_tools: list[str] = Field(default_factory=list)


class TaskResult(StrictModel):
    task_id: str = Field(min_length=1)
    status: Literal["success", "failed"]
    output: str = ""
    citations: list[str] = Field(default_factory=list)
    error: str | None = None


class AgentSpec(StrictModel):
    agent_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)


class PlanSpec(StrictModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    tasks: list[TaskSpec] = Field(min_length=1)


class RunTrace(StrictModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: Literal["started", "completed", "failed"] = "started"
    events: list[dict[str, str]] = Field(default_factory=list)
