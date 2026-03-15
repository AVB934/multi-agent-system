from __future__ import annotations

from app.persistence.base import MemoryPolicy, RunStore
from app.runtime.logging import log_event
from app.runtime.security import sanitize_untrusted_text


class CuratedMemoryStore:
    """Write-only curated memory managed by the orchestrator."""

    def __init__(self, run_store: RunStore, policy: MemoryPolicy | None = None) -> None:
        self.run_store = run_store
        self.policy = policy or MemoryPolicy()

    def write_from_aggregation(
        self,
        *,
        request_id: str,
        trace_id: str,
        aggregated: dict[str, object],
    ) -> int:
        draft = sanitize_untrusted_text(str(aggregated.get("draft", ""))).strip()
        citations = [str(c) for c in aggregated.get("citations", [])]

        if self.policy.require_citations and not citations:
            log_event(trace_id, "memory", "skip_curated_memory", reason="missing_citations")
            return 0
        if len(draft) < self.policy.min_content_length:
            log_event(trace_id, "memory", "skip_curated_memory", reason="content_too_short")
            return 0

        entries = [draft[:2000]]
        entries = entries[: self.policy.max_entries_per_run]
        for index, entry in enumerate(entries, start=1):
            self.run_store.insert_curated_memory(
                request_id=request_id,
                memory_key=f"summary_{index}",
                content=entry,
                citations=citations,
            )
        log_event(trace_id, "memory", "curated_memory_written", entries=len(entries))
        return len(entries)
