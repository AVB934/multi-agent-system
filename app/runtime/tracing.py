from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.contracts import RunTrace


def new_trace() -> RunTrace:
    return RunTrace(trace_id=str(uuid4()), request_id=str(uuid4()))


def mark_trace_complete(trace: RunTrace, status: str, event: str) -> RunTrace:
    trace.events.append({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event})
    trace.status = status  # type: ignore[assignment]
    trace.finished_at = datetime.now(timezone.utc)
    return trace

