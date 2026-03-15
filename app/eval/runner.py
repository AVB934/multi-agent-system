from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.orchestrator import Orchestrator


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str


class EvalRunner:
    def __init__(self, orchestrator: Orchestrator) -> None:
        self.orchestrator = orchestrator

    async def run(self, input_jsonl_path: str, output_report_path: str | None = None) -> dict[str, object]:
        cases = self._load_cases(input_jsonl_path)
        details: list[dict[str, object]] = []
        total_tool_calls = 0
        citation_hits = 0
        latencies_ms: list[float] = []
        successes = 0

        for case in cases:
            started = time.perf_counter()
            response = await self.orchestrator.run(case.query, include_json=True)
            latency_ms = (time.perf_counter() - started) * 1000.0
            latencies_ms.append(latency_ms)

            tool_calls = self._count_tool_calls(response.trace.request_id)
            total_tool_calls += tool_calls
            citation_count = len(response.json_payload.get("citations", [])) if response.json_payload else 0
            if citation_count > 0:
                citation_hits += 1
            verification_status = (
                str(response.json_payload.get("verification", {}).get("status", ""))
                if response.json_payload
                else ""
            )
            success = verification_status == "success"
            if success:
                successes += 1

            details.append(
                {
                    "id": case.id,
                    "query": case.query,
                    "success": success,
                    "latency_ms": round(latency_ms, 3),
                    "tool_calls": tool_calls,
                    "citation_count": citation_count,
                    "verification_status": verification_status,
                    "trace_id": response.trace.trace_id,
                    "request_id": response.trace.request_id,
                }
            )

        metrics = self._compute_metrics(
            total=len(cases),
            successes=successes,
            latencies_ms=latencies_ms,
            total_tool_calls=total_tool_calls,
            citation_hits=citation_hits,
        )
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(cases),
            "metrics": metrics,
            "details": details,
        }

        report_path = output_report_path or self._default_report_path()
        self._write_report(report_path, report)
        return {
            "total_cases": len(cases),
            "metrics": metrics,
            "report_path": report_path,
        }

    def _load_cases(self, input_jsonl_path: str) -> list[EvalCase]:
        path = Path(input_jsonl_path)
        if not path.exists():
            raise FileNotFoundError(f"input jsonl not found: {input_jsonl_path}")

        cases: list[EvalCase] = []
        for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            query = str(payload.get("query", "")).strip()
            if not query:
                raise ValueError(f"missing query in eval row {index}")
            case_id = str(payload.get("id", f"case-{index}"))
            cases.append(EvalCase(id=case_id, query=query))

        if not cases:
            raise ValueError("no eval cases found")
        return cases

    def _compute_metrics(
        self,
        *,
        total: int,
        successes: int,
        latencies_ms: list[float],
        total_tool_calls: int,
        citation_hits: int,
    ) -> dict[str, float | int]:
        sorted_lat = sorted(latencies_ms)
        p95_index = max(int(0.95 * len(sorted_lat)) - 1, 0)
        return {
            "success": successes,
            "success_rate": round(successes / total if total else 0.0, 4),
            "avg_latency_ms": round(sum(latencies_ms) / total if total else 0.0, 3),
            "p95_latency_ms": round(sorted_lat[p95_index] if sorted_lat else 0.0, 3),
            "tool_calls": total_tool_calls,
            "citation_coverage": round(citation_hits / total if total else 0.0, 4),
        }

    def _count_tool_calls(self, request_id: str) -> int:
        try:
            web_tool = self.orchestrator._default_factory.available_tools.get("web.search")  # noqa: SLF001
            gateway = getattr(web_tool, "gateway", None)
            audit_logs = getattr(gateway, "audit_logs", [])
            return sum(1 for row in audit_logs if row.get("request_id") == request_id)
        except Exception:
            return 0

    def _default_report_path(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"/tmp/mas_eval_report_{stamp}.json"

    def _write_report(self, report_path: str, report: dict[str, object]) -> None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def run_eval_sync(orchestrator: Orchestrator, input_jsonl_path: str, output_report_path: str | None = None) -> dict[str, object]:
    return asyncio.run(EvalRunner(orchestrator).run(input_jsonl_path, output_report_path))
