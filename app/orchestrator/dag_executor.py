from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.orchestrator.agent_factory import AgentFactory
from app.runtime.logging import log_event
from app.schemas.contracts import PlanSpec, RunTrace, TaskResult, TaskSpec


@dataclass(frozen=True)
class ExecutionBudget:
    max_agents: int = 10
    max_tool_calls: int = 50
    token_budget: int = 10000  # Placeholder until token accounting is integrated.


@dataclass(frozen=True)
class ExecutionPolicy:
    per_task_timeout_seconds: float = 120.0
    max_retries: int = 1
    budget: ExecutionBudget = ExecutionBudget()


class DagExecutionError(RuntimeError):
    pass


class DAGExecutor:
    def __init__(self, agent_factory: AgentFactory, policy: ExecutionPolicy | None = None) -> None:
        self.agent_factory = agent_factory
        self.policy = policy or ExecutionPolicy()

    async def execute(self, plan: PlanSpec, trace: RunTrace | None = None) -> list[TaskResult]:
        self._validate_plan(plan)
        self._enforce_budgets_preflight(plan, trace)

        task_by_id = {task.task_id: task for task in plan.tasks}
        dependents: dict[str, set[str]] = {task.task_id: set() for task in plan.tasks}
        pending_deps: dict[str, set[str]] = {task.task_id: set(task.dependencies) for task in plan.tasks}
        for task in plan.tasks:
            for dep_id in task.dependencies:
                dependents[dep_id].add(task.task_id)

        results: dict[str, TaskResult] = {}
        attempts: dict[str, int] = {}
        ready: set[str] = {task.task_id for task in plan.tasks if not task.dependencies}
        running: dict[str, asyncio.Task[TaskResult]] = {}
        completed_ids: set[str] = set()
        agent_runs = 0
        tool_calls_used = 0  # Placeholder counter until tools emit call events.

        while len(completed_ids) < len(plan.tasks):
            while ready:
                task_id = ready.pop()
                if task_id in completed_ids or task_id in running:
                    continue
                task = task_by_id[task_id]
                if any(results.get(dep_id) and results[dep_id].status == "failed" for dep_id in task.dependencies):
                    failed_deps = [dep for dep in task.dependencies if results[dep].status == "failed"]
                    result = TaskResult(
                        task_id=task.task_id,
                        status="failed",
                        output="",
                        citations=[],
                        error=f"dependency_failed: {','.join(failed_deps)}",
                    )
                    results[task.task_id] = result
                    completed_ids.add(task.task_id)
                    self._trace_event(trace, "task.end", task=task, status="failed", error=result.error or "")
                    self._mark_dependents_ready(task.task_id, dependents, pending_deps, ready, completed_ids)
                    continue

                agent_runs += 1
                if agent_runs > self.policy.budget.max_agents:
                    raise DagExecutionError(
                        f"max_agents budget exceeded: {agent_runs}>{self.policy.budget.max_agents}"
                    )

                attempts[task_id] = attempts.get(task_id, 0) + 1
                self._trace_event(
                    trace,
                    "task.start",
                    task=task,
                    attempt=str(attempts[task_id]),
                    timeout_seconds=str(self.policy.per_task_timeout_seconds),
                )
                running[task_id] = asyncio.create_task(
                    self._run_task(task=task, prior_results=results, trace=trace)
                )

            if not running:
                if len(completed_ids) >= len(plan.tasks):
                    break
                unresolved = set(task_by_id) - completed_ids
                if not unresolved:
                    break
                raise DagExecutionError(f"deadlock or cycle detected; unresolved tasks: {sorted(unresolved)}")

            done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
            finished_task_ids = [task_id for task_id, task_future in running.items() if task_future in done]

            for task_id in finished_task_ids:
                task = task_by_id[task_id]
                task_future = running.pop(task_id)
                result = task_future.result()
                results[task_id] = result

                if result.status == "failed" and attempts[task_id] <= self.policy.max_retries:
                    self._trace_event(
                        trace,
                        "task.retry",
                        task=task,
                        attempt=str(attempts[task_id]),
                        error=result.error or "",
                    )
                    ready.add(task_id)
                    continue

                completed_ids.add(task_id)
                self._trace_event(
                    trace,
                    "task.end",
                    task=task,
                    status=result.status,
                    error=result.error or "",
                    tool_calls=str(tool_calls_used),
                )
                self._mark_dependents_ready(task_id, dependents, pending_deps, ready, completed_ids)

        ordered_results = [results[task.task_id] for task in plan.tasks]
        self._trace_budget_summary(trace, agent_runs=agent_runs, tool_calls_used=tool_calls_used)
        return ordered_results

    def _validate_plan(self, plan: PlanSpec) -> None:
        task_ids = [task.task_id for task in plan.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise DagExecutionError("duplicate task_id detected")

        task_id_set = set(task_ids)
        for task in plan.tasks:
            missing = [dep for dep in task.dependencies if dep not in task_id_set]
            if missing:
                raise DagExecutionError(f"task {task.task_id} references missing dependencies: {missing}")

        self._assert_acyclic(plan)

    def _assert_acyclic(self, plan: PlanSpec) -> None:
        indegree = {task.task_id: len(task.dependencies) for task in plan.tasks}
        edges: dict[str, list[str]] = {task.task_id: [] for task in plan.tasks}
        for task in plan.tasks:
            for dep in task.dependencies:
                edges[dep].append(task.task_id)

        queue = [task_id for task_id, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for nxt in edges[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if visited != len(plan.tasks):
            raise DagExecutionError("cycle detected in plan")

    def _enforce_budgets_preflight(self, plan: PlanSpec, trace: RunTrace | None) -> None:
        if len(plan.tasks) > self.policy.budget.max_agents:
            raise DagExecutionError(
                f"max_agents budget exceeded during preflight: {len(plan.tasks)}>"
                f"{self.policy.budget.max_agents}"
            )
        self._trace_event(
            trace,
            "budget.preflight",
            status="ok",
            max_agents=str(self.policy.budget.max_agents),
            max_tool_calls=str(self.policy.budget.max_tool_calls),
            token_budget=str(self.policy.budget.token_budget),
            note="tool_calls and token_budget are placeholders in phase_2",
        )

    async def _run_task(
        self,
        task: TaskSpec,
        prior_results: dict[str, TaskResult],
        trace: RunTrace | None,
    ) -> TaskResult:
        try:
            agent = self.agent_factory.create(task.assigned_agent, agent_id=f"{task.assigned_agent}:{task.task_id}")
            unauthorized_required = set(task.required_tools) - set(agent.spec.allowed_tools)
            if unauthorized_required:
                return TaskResult(
                    task_id=task.task_id,
                    status="failed",
                    output="",
                    citations=[],
                    error=f"task_requested_unauthorized_tools:{sorted(unauthorized_required)}",
                )

            context = self._build_context(task, prior_results, trace=trace)
            result = await asyncio.wait_for(
                agent.run(task, context=context),
                timeout=self.policy.per_task_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            self._trace_event(trace, "task.error", task=task, error="timeout")
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                output="",
                citations=[],
                error="timeout",
            )
        except Exception as exc:  # pragma: no cover - defensive path
            self._trace_event(trace, "task.error", task=task, error=str(exc))
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                output="",
                citations=[],
                error=f"exception:{type(exc).__name__}:{exc}",
            )

    def _build_context(
        self,
        task: TaskSpec,
        prior_results: dict[str, TaskResult],
        trace: RunTrace | None = None,
    ) -> dict[str, Any]:
        dependency_results = {dep_id: prior_results[dep_id] for dep_id in task.dependencies if dep_id in prior_results}
        draft = "\n".join(result.output for result in dependency_results.values() if result.output)
        citations: list[str] = []
        for result in dependency_results.values():
            citations.extend(result.citations)
        ctx = {
            "dependency_results": dependency_results,
            "draft": draft,
            "citations": citations,
        }
        if trace is not None:
            ctx["request_id"] = trace.request_id
            ctx["trace_id"] = trace.trace_id
        return ctx

    def _mark_dependents_ready(
        self,
        task_id: str,
        dependents: dict[str, set[str]],
        pending_deps: dict[str, set[str]],
        ready: set[str],
        completed_ids: set[str],
    ) -> None:
        for dependent_id in dependents.get(task_id, set()):
            pending = pending_deps[dependent_id]
            pending.discard(task_id)
            if not pending and dependent_id not in completed_ids:
                ready.add(dependent_id)

    def _trace_event(
        self,
        trace: RunTrace | None,
        event_type: str,
        task: TaskSpec | None = None,
        **fields: str,
    ) -> None:
        if trace is None:
            return
        payload: dict[str, str] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
        }
        if task is not None:
            payload["task_id"] = task.task_id
            payload["agent"] = task.assigned_agent
        payload.update({key: str(value) for key, value in fields.items()})
        trace.events.append(payload)
        if "trace_id" in trace.model_fields_set or trace.trace_id:
            log_event(trace.trace_id, "dag_executor", event_type, **payload)

    def _trace_budget_summary(self, trace: RunTrace | None, agent_runs: int, tool_calls_used: int) -> None:
        self._trace_event(
            trace,
            "budget.summary",
            status="ok",
            agent_runs=str(agent_runs),
            tool_calls_used=str(tool_calls_used),
            token_budget_used="0",
            note="tool_calls and token accounting placeholders",
        )
