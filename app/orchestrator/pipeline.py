from __future__ import annotations

import json
import os
from typing import Any

from app.orchestrator.agent_factory import AgentFactory
from app.orchestrator.agent_registry import AgentRegistry
from app.orchestrator.dag_executor import DAGExecutor
from app.orchestrator.interfaces import Executor, IntentClassifier, Planner
from app.persistence import CuratedMemoryStore, RunStore, SqliteRunStore
from app.runtime.logging import log_event
from app.runtime.security import sanitize_untrusted_text
from app.runtime.tracing import mark_trace_complete, new_trace
from app.schemas.contracts import PlanSpec, TaskResult, TaskSpec
from app.schemas.query import QueryResponse
from app.tools.adk_gemini import ADKGeminiTool
from app.tools.web_search import StubWebSearchTool


class StubIntentClassifier:
    def classify(self, query: str) -> str:
        _ = query
        return "general"


class StubPlanner:
    def plan(self, query: str, intent: str) -> PlanSpec:
        _ = intent
        return PlanSpec(
            tasks=[
                TaskSpec(
                    task_id="research-1",
                    description=f"Research facts for query: {query}",
                    dependencies=[],
                    assigned_agent="research",
                    required_tools=["llm.adk"],
                ),
                TaskSpec(
                    task_id="verify-1",
                    description="Verify factual consistency and citation coverage.",
                    dependencies=["research-1"],
                    assigned_agent="verifier",
                    required_tools=[],
                )
            ]
        )


class StubExecutor:
    async def execute(self, plan: PlanSpec, trace=None) -> list[TaskResult]:
        _ = trace
        return [
            TaskResult(
                task_id=task.task_id,
                status="success",
                output=f"Completed {task.description}",
                citations=[],
                error=None,
            )
            for task in plan.tasks
        ]


class Orchestrator:
    """Phase 0 orchestrator with stubbed classification, planning, and execution."""

    def __init__(
        self,
        classifier: IntentClassifier | None = None,
        planner: Planner | None = None,
        executor: Executor | None = None,
        run_store: RunStore | None = None,
        memory_store: CuratedMemoryStore | None = None,
    ) -> None:
        self._classifier = classifier or StubIntentClassifier()
        self._planner = planner or StubPlanner()
        self._llm_tool = ADKGeminiTool.from_env()
        db_path = os.getenv("MAS_DB_PATH", "data/mas.sqlite3")
        self._run_store = run_store or SqliteRunStore(db_path=db_path)
        self._memory_store = memory_store or CuratedMemoryStore(self._run_store)
        self._default_registry = AgentRegistry.with_defaults()
        self._default_factory = AgentFactory(
            registry=self._default_registry,
            available_tools={
                "web.search": StubWebSearchTool(),
                "llm.adk": self._llm_tool,
            },
        )
        self._executor = executor or self._build_default_executor()

    async def run(self, query: str, include_json: bool = False) -> QueryResponse:
        trace = new_trace()
        trace.events.append({"stage": "ingest", "message": "request received"})
        log_event(trace.trace_id, "ingest", "request received")

        intent = await self.classify_query(query)
        trace.events.append({"stage": "classify", "message": f"intent={intent}"})
        log_event(trace.trace_id, "classify", "intent classified", intent=intent)

        plan = await self.plan_query(query, intent)
        trace.events.append({"stage": "plan", "message": f"tasks={len(plan.tasks)}"})
        log_event(trace.trace_id, "plan", "plan created", task_count=len(plan.tasks))

        task_results = await self.execute(plan, trace=trace)
        trace.events.append({"stage": "execute", "message": f"results={len(task_results)}"})
        log_event(trace.trace_id, "execute", "tasks executed", result_count=len(task_results))

        aggregated = self.aggregate(plan=plan, task_results=task_results, trace=trace)
        trace.events.append({"stage": "aggregate", "message": f"citations={len(aggregated['citations'])}"})
        log_event(trace.trace_id, "aggregate", "results aggregated", citations=len(aggregated["citations"]))

        task_results, aggregated, post_verify = await self.verify_and_repair(
            plan=plan,
            task_results=task_results,
            aggregated=aggregated,
            trace=trace,
        )

        answer, json_payload = self.format_response(
            query=query,
            intent=intent,
            plan=plan,
            task_results=task_results,
            aggregated=aggregated,
            verification_result=post_verify,
            trace=trace,
            include_json=include_json,
        )
        mark_trace_complete(trace=trace, status="completed", event="response_ready")
        log_event(trace.trace_id, "respond", "response ready")
        self.persist_run(
            query=query,
            intent=intent,
            plan=plan,
            task_results=task_results,
            trace=trace,
            answer=answer,
            json_payload=json_payload,
        )
        self.persist_curated_memory(trace=trace, aggregated=aggregated)

        return QueryResponse(
            answer=answer,
            intent=intent,
            plan=plan,
            task_results=task_results,
            trace=trace,
            json_payload=json_payload,
        )

    def classify(self, query: str) -> str:
        return self._classifier.classify(query)

    def plan(self, query: str, intent: str) -> PlanSpec:
        return self._planner.plan(query, intent)

    async def classify_query(self, query: str) -> str:
        if not self._llm_tool.enabled:
            return self.classify(query)
        prompt = (
            "Classify the user query intent in one label from this set: "
            "[general, research, coding, planning]. "
            "Return strict JSON: {\"intent\":\"<label>\"}."
        )
        try:
            result = await self._llm_tool.complete_json(
                system_instruction="You are an intent classifier. Return only valid JSON.",
                user_prompt=f"Query: {query}\n{prompt}",
            )
            intent = str(result.get("intent", "general")).strip().lower()
            if intent in {"general", "research", "coding", "planning"}:
                return intent
        except Exception as exc:
            log_event("n/a", "classify", "llm_classification_fallback", error=str(exc))
        return self.classify(query)

    async def plan_query(self, query: str, intent: str) -> PlanSpec:
        if not self._llm_tool.enabled:
            return self.plan(query, intent)
        prompt = (
            "Create a minimal task DAG for this query. "
            "You must produce no more than 3 tasks total. "
            "Prefer exactly 2 tasks unless the query truly needs a third. "
            "Use only agents from: research, verifier. "
            "Each task must include task_id, description, dependencies, assigned_agent, required_tools. "
            "Allowed required_tools are web.search and llm.adk. "
            "Do not decompose into multiple parallel research tasks for a single user question unless absolutely necessary. "
            "Return strict JSON: {\"tasks\":[...]}."
        )
        try:
            payload = await self._llm_tool.complete(
                system_instruction="You are a planning agent. Return only valid JSON.",
                user_prompt=f"Intent: {intent}\nQuery: {query}\n{prompt}",
            )
            cleaned = payload.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
            parsed = json.loads(cleaned)
            tasks = parsed.get("tasks", [])
            if tasks:
                limited_tasks = [self._normalize_planned_task(task) for task in tasks[:3]]
                return PlanSpec(tasks=[TaskSpec(**task) for task in limited_tasks])
        except Exception as exc:
            log_event("n/a", "plan", "llm_planning_fallback", error=str(exc))
        return self.plan(query, intent)

    def _normalize_planned_task(self, task: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(task)
        required_tools = [str(tool) for tool in normalized.get("required_tools", [])]
        if self._llm_tool.enabled and normalized.get("assigned_agent") in {"research", "verifier"}:
            if "llm.adk" not in required_tools:
                required_tools.insert(0, "llm.adk")
        normalized["required_tools"] = required_tools
        return normalized

    async def execute(self, plan: PlanSpec, trace=None) -> list[TaskResult]:
        return await self._executor.execute(plan, trace=trace)

    def respond(self, query: str, intent: str, task_results: list[TaskResult]) -> str:
        _ = intent
        safe_query = sanitize_untrusted_text(query)
        return f"Query received: {safe_query}. Completed {len(task_results)} task(s)."

    def _build_default_executor(self) -> Executor:
        return DAGExecutor(agent_factory=self._default_factory)

    def aggregate(
        self,
        plan: PlanSpec,
        task_results: list[TaskResult],
        trace,
    ) -> dict[str, Any]:
        task_agent_map = {task.task_id: task.assigned_agent for task in plan.tasks}
        content_results = [
            result
            for result in task_results
            if result.status == "success"
            and result.output
            and task_agent_map.get(result.task_id) != "verifier"
        ]
        merged_draft = "\n".join(result.output for result in content_results).strip()
        citations: list[str] = []
        for result in content_results:
            for citation in result.citations:
                if citation not in citations:
                    citations.append(citation)

        trace_refs = [
            {"task_id": task.task_id, "agent": task.assigned_agent}
            for task in plan.tasks
        ]
        log_event(trace.trace_id, "aggregate", "merged draft built", draft_len=len(merged_draft))
        return {
            "draft": merged_draft,
            "citations": citations,
            "trace_refs": trace_refs,
        }

    async def verify_and_repair(
        self,
        plan: PlanSpec,
        task_results: list[TaskResult],
        aggregated: dict[str, Any],
        trace,
    ) -> tuple[list[TaskResult], dict[str, Any], TaskResult]:
        verifier = self._default_factory.create("verifier", agent_id="verifier:post-pass")
        verify_task = TaskSpec(
            task_id="post-verify",
            description="Verify merged draft and citations.",
            dependencies=[],
            assigned_agent="verifier",
            required_tools=[],
        )
        verify_context = {
            "draft": aggregated["draft"],
            "citations": aggregated["citations"],
            "request_id": trace.request_id,
            "trace_id": trace.trace_id,
        }
        verification = await verifier.run(verify_task, context=verify_context)
        trace.events.append(
            {
                "stage": "verify_post",
                "message": verification.output,
                "status": verification.status,
            }
        )
        log_event(trace.trace_id, "verify_post", "post-aggregation verification", status=verification.status)
        if verification.status == "success":
            return task_results, aggregated, verification

        # Targeted repair: retry only research tasks once, then re-aggregate and re-verify.
        repair_tasks = [task for task in plan.tasks if task.assigned_agent == "research"]
        if not repair_tasks:
            return task_results, aggregated, verification

        trace.events.append(
            {"stage": "repair", "message": f"retrying {len(repair_tasks)} research task(s)", "attempt": "1"}
        )
        log_event(trace.trace_id, "repair", "targeted repair retry", task_count=len(repair_tasks))
        repair_results = await self.execute(PlanSpec(tasks=repair_tasks), trace=trace)
        results_by_id = {result.task_id: result for result in task_results}
        for repair_result in repair_results:
            results_by_id[repair_result.task_id] = repair_result
        repaired_results = [results_by_id[result.task_id] for result in task_results]
        repaired_aggregated = self.aggregate(plan=plan, task_results=repaired_results, trace=trace)

        second_verification = await verifier.run(
            verify_task,
            context={
                "draft": repaired_aggregated["draft"],
                "citations": repaired_aggregated["citations"],
                "request_id": trace.request_id,
                "trace_id": trace.trace_id,
            },
        )
        trace.events.append(
            {
                "stage": "verify_post",
                "message": second_verification.output,
                "status": second_verification.status,
                "attempt": "2",
            }
        )
        log_event(
            trace.trace_id,
            "verify_post",
            "post-aggregation verification retry",
            status=second_verification.status,
        )
        return repaired_results, repaired_aggregated, second_verification

    def format_response(
        self,
        query: str,
        intent: str,
        plan: PlanSpec,
        task_results: list[TaskResult],
        aggregated: dict[str, Any],
        verification_result: TaskResult,
        trace,
        include_json: bool,
    ) -> tuple[str, dict[str, object] | None]:
        safe_query = sanitize_untrusted_text(query)
        draft = aggregated["draft"] or f"No draft content generated for query: {safe_query}"
        citations = aggregated["citations"]
        verification_suffix = (
            "Verified." if verification_result.status == "success" else "Verification issues remain."
        )
        answer = draft
        if citations:
            answer = f"{draft}\n\nCitations:\n" + "\n".join(f"- {c}" for c in citations)
        answer = f"{answer}\n\n{verification_suffix}"

        json_payload: dict[str, object] | None = None
        if include_json:
            json_payload = {
                "intent": intent,
                "plan": plan.model_dump(mode="json"),
                "citations": citations,
                "trace_refs": {
                    "trace_id": trace.trace_id,
                    "request_id": trace.request_id,
                    "tasks": aggregated["trace_refs"],
                },
                "verification": {
                    "status": verification_result.status,
                    "message": verification_result.output,
                },
                "task_result_ids": [result.task_id for result in task_results],
            }
        return answer, json_payload

    def persist_run(
        self,
        *,
        query: str,
        intent: str,
        plan: PlanSpec,
        task_results: list[TaskResult],
        trace,
        answer: str,
        json_payload: dict[str, object] | None,
    ) -> None:
        self._run_store.save_run(
            request_id=trace.request_id,
            trace_id=trace.trace_id,
            query=query,
            intent=intent,
            plan=plan,
            task_results=task_results,
            trace=trace,
            answer=answer,
            json_payload=json_payload,
        )
        log_event(trace.trace_id, "persistence", "run_saved", request_id=trace.request_id)

    def persist_curated_memory(self, *, trace, aggregated: dict[str, Any]) -> None:
        self._memory_store.write_from_aggregation(
            request_id=trace.request_id,
            trace_id=trace.trace_id,
            aggregated=aggregated,
        )
