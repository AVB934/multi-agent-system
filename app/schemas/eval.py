from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    input_jsonl_path: str = Field(min_length=1)
    output_report_path: str | None = None


class EvalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    total_cases: int
    report_path: str
    metrics: dict[str, float | int]