from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool(Protocol):
    tool_id: str

    async def search(
        self, query: str, request_id: str = "default", trace_id: str | None = None
    ) -> list[SearchResult]: ...

    async def fetch_page_text(
        self, url: str, request_id: str = "default", trace_id: str | None = None
    ) -> str: ...
