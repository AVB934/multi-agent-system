from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas.contracts import PlanSpec, RunTrace, TaskResult


class RunStore(Protocol):
    def migrate(self) -> None: ...

    def save_run(
        self,
        *,
        request_id: str,
        trace_id: str,
        query: str,
        intent: str,
        plan: PlanSpec,
        task_results: list[TaskResult],
        trace: RunTrace,
        answer: str,
        json_payload: dict[str, object] | None,
    ) -> None: ...

    def get_run(self, request_id: str) -> dict[str, object] | None: ...

    def insert_curated_memory(
        self,
        *,
        request_id: str,
        memory_key: str,
        content: str,
        citations: list[str],
    ) -> None: ...

    def list_curated_memory(self, limit: int = 50) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class MemoryPolicy:
    require_citations: bool = True
    min_content_length: int = 20
    max_entries_per_run: int = 1
