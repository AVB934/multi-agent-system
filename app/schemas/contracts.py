from typing_extensions import Literal
import uuid

from pydantic import BaseModel, Field, ConfigDict

class TaskSpec(BaseModel):
    task_id : str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = Field(min_length=10)
    dependencies: list[str] = Field(default_factory=list)
    assined_agent: str = Field(min_length=1)
    required_tools: list[str] = Field(default_factory=list)

class PlanSpec(BaseModel):
    plan_id : str = Field(default_factory=lambda: str(uuid.uuid4()))
    tasks: list[TaskSpec] = Field(min_length=1)

class AgentSpec(BaseModel):
    agent_id : str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)

class RunTrace(BaseModel):
    pass

class TaskResult(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status : Literal["success", "failure"] = "success"
    output: str = Field(default="")
    citations: list[str] = Field(default_factory=list)
    error_message: str = Field(default="")

class SearchResult(BaseModel):
    pass
