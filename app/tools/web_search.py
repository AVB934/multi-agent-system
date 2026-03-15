from __future__ import annotations

import os

from app.tools.base import SearchResult
from app.tools.providers import DuckDuckGoWebSearchProvider, InMemoryWebSearchProvider, WebSearchProvider
from app.tools.tool_gateway import ToolGateway, ToolGatewayConfig


class StubWebSearchTool:
    """Web search tool wired through ToolGateway with configurable real/stub providers."""

    tool_id = "web.search"

    def __init__(
        self,
        gateway: ToolGateway | None = None,
        provider: WebSearchProvider | None = None,
    ) -> None:
        self.gateway = gateway or ToolGateway(config=self._gateway_config_from_env())
        self.provider = provider or self._provider_from_env()

    async def search(
        self, query: str, request_id: str = "default", trace_id: str | None = None
    ) -> list[SearchResult]:
        return await self.gateway.web_search(
            provider=self.provider, query=query, request_id=request_id, trace_id=trace_id
        )

    async def fetch_page_text(
        self, url: str, request_id: str = "default", trace_id: str | None = None
    ) -> str:
        return await self.gateway.web_fetch_text(
            provider=self.provider, url=url, request_id=request_id, trace_id=trace_id
        )

    def _provider_from_env(self) -> WebSearchProvider:
        provider_name = os.getenv("MAS_WEB_PROVIDER", "duckduckgo").strip().lower()
        if provider_name == "stub":
            return InMemoryWebSearchProvider(
                page_text_by_url={
                    "https://example.com/stub-result": (
                        "Example domain stub fact one. Example domain stub fact two."
                    )
                }
            )
        return DuckDuckGoWebSearchProvider()

    def _gateway_config_from_env(self) -> ToolGatewayConfig:
        raw_domains = os.getenv("MAS_WEB_ALLOWLIST", "").strip()
        allowlist = tuple(
            domain.strip().lower()
            for domain in raw_domains.split(",")
            if domain.strip()
        )
        max_calls = int(os.getenv("MAS_WEB_MAX_CALLS_PER_REQUEST", "20"))
        return ToolGatewayConfig(
            allowlist_domains=allowlist,
            max_calls_per_request=max_calls,
        )
