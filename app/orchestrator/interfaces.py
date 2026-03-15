from __future__ import annotations

from typing import Protocol

from app.schemas.contracts import PlanSpec, RunTrace, TaskResult


class IntentClassifier(Protocol):
    def classify(self, query: str) -> str: ...


class Planner(Protocol):
    def plan(self, query: str, intent: str) -> PlanSpec: ...


class Executor(Protocol):
    async def execute(self, plan: PlanSpec, trace: RunTrace | None = None) -> list[TaskResult]: ...
