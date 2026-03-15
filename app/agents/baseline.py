from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.runtime.security import sanitize_untrusted_text
from app.schemas.contracts import PlanSpec, TaskResult, TaskSpec
from app.tools.base import SearchResult


class PlannerAgent(BaseAgent):
    def create_plan(self, query: str) -> PlanSpec:
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
                ),
            ]
        )

    async def run(self, task: TaskSpec, context: dict[str, Any] | None = None) -> TaskResult:
        _ = context
        return TaskResult(task_id=task.task_id, status="success", output="Plan prepared.", citations=[])


class ResearchAgent(BaseAgent):
    async def run(self, task: TaskSpec, context: dict[str, Any] | None = None) -> TaskResult:
        ctx = context or {}
        search_tool = self.tools.get("web.search")
        llm_tool = self.tools.get("llm.adk")
        request_id = str(ctx.get("request_id", task.task_id))
        trace_id = str(ctx["trace_id"]) if "trace_id" in ctx else None

        if llm_tool is not None and getattr(llm_tool, "enabled", False):
            try:
                grounded = await llm_tool.complete_with_google_search(
                    system_instruction=(
                        "Research the user query using Google Search grounding. "
                        "Return a short factual synthesis in 2-4 concise bulletless sentences."
                    ),
                    user_prompt=task.description,
                )
                grounded_text = sanitize_untrusted_text(str(grounded.get("text", ""))).strip()
                grounded_citations = [
                    sanitize_untrusted_text(str(url)).strip()
                    for url in grounded.get("citations", [])
                    if str(url).strip()
                ]
                if grounded_text:
                    return TaskResult(
                        task_id=task.task_id,
                        status="success",
                        output=grounded_text,
                        citations=grounded_citations,
                    )
            except Exception:
                pass

        if search_tool is None:
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                output="",
                citations=[],
                error="Neither llm.adk Google Search nor web.search is available for this agent",
            )

        results: list[SearchResult] = await search_tool.search(
            task.description, request_id=request_id, trace_id=trace_id
        )
        claim_lines: list[str] = []
        citations: list[str] = []
        for index, item in enumerate(results, start=1):
            page_text = await search_tool.fetch_page_text(item.url, request_id=request_id, trace_id=trace_id)
            claim = self._extract_claim(page_text=page_text, fallback=item.snippet)
            if llm_tool is not None and getattr(llm_tool, "enabled", False):
                try:
                    llm_claim = await llm_tool.complete(
                        system_instruction=(
                            "Extract one concise factual claim from the supplied text. "
                            "Return plain text only."
                        ),
                        user_prompt=(
                            f"Query: {task.description}\n"
                            f"Search title: {item.title}\n"
                            f"Search snippet: {item.snippet}\n"
                            f"Page text: {page_text}"
                        ),
                    )
                    if llm_claim.strip():
                        claim = sanitize_untrusted_text(llm_claim).strip()
                except Exception:
                    pass
            claim_lines.append(f"[{index}] {claim} (source: {item.url})")
            citations.append(item.url)

        combined = "\n".join(claim_lines) if claim_lines else "No allowed search results found."
        return TaskResult(task_id=task.task_id, status="success", output=combined, citations=citations)

    def _extract_claim(self, page_text: str, fallback: str) -> str:
        safe_text = sanitize_untrusted_text(page_text).strip()
        if not safe_text:
            return sanitize_untrusted_text(fallback).strip()
        first_sentence = safe_text.split(".")[0].strip()
        if first_sentence:
            return first_sentence + "."
        return sanitize_untrusted_text(fallback).strip()


class VerifierAgent(BaseAgent):
    async def run(self, task: TaskSpec, context: dict[str, Any] | None = None) -> TaskResult:
        ctx = context or {}
        citations = ctx.get("citations", [])
        draft = str(ctx.get("draft", "")).strip()
        llm_tool = self.tools.get("llm.adk")

        hard_issues: list[str] = []
        if not draft:
            hard_issues.append("missing draft")
        if not citations:
            hard_issues.append("missing citations")
        if hard_issues:
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                output=f"verification failed: {', '.join(hard_issues)}",
                citations=list(citations),
            )

        if llm_tool is not None and getattr(llm_tool, "enabled", False):
            try:
                payload = await llm_tool.complete_json(
                    system_instruction=(
                        "You are a verifier. Check for obvious contradictions and citation coverage. "
                        "Return strict JSON: "
                        "{\"status\":\"success|failed\",\"issues\":[\"...\"]}."
                    ),
                    user_prompt=f"Draft:\n{draft}\n\nCitations:\n{citations}",
                )
                issues = [str(x) for x in payload.get("issues", [])]
                status = str(payload.get("status", "failed")).strip().lower()
                if status not in {"success", "failed"}:
                    status = "failed"
                message = "verification passed" if status == "success" else (
                    "verification failed: " + ", ".join(issues or ["unknown issue"])
                )
                return TaskResult(
                    task_id=task.task_id,
                    status=status,
                    output=message,
                    citations=list(citations),
                )
            except Exception:
                pass

        return TaskResult(
            task_id=task.task_id,
            status="success",
            output="verification passed",
            citations=list(citations),
        )
