from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.runtime.logging import log_event
from app.runtime.security import sanitize_untrusted_text
from app.tools.base import SearchResult
from app.tools.providers import WebSearchProvider


class ToolPolicyError(RuntimeError):
    pass


class ToolRateLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolGatewayConfig:
    allowlist_domains: tuple[str, ...] = ()
    max_calls_per_request: int = 20


@dataclass
class ToolGateway:
    config: ToolGatewayConfig = field(default_factory=ToolGatewayConfig)
    cache: dict[str, Any] = field(default_factory=dict)
    audit_logs: list[dict[str, str]] = field(default_factory=list)
    _request_call_counts: dict[str, int] = field(default_factory=dict)

    async def web_search(
        self,
        provider: WebSearchProvider,
        query: str,
        request_id: str,
        trace_id: str | None = None,
    ) -> list[SearchResult]:
        safe_query = sanitize_untrusted_text(query)
        cache_key = f"search::{safe_query}"
        if cache_key in self.cache:
            results = list(self.cache[cache_key])
            self._audit("web.search", request_id, trace_id, cache_hit="true", query=safe_query, count=str(len(results)))
            return results

        self._consume_request_budget(request_id)
        raw_results = await provider.search(safe_query)
        results = [result for result in raw_results if self._is_allowed_url(result.url)]
        self.cache[cache_key] = list(results)
        self._audit("web.search", request_id, trace_id, cache_hit="false", query=safe_query, count=str(len(results)))
        return results

    async def web_fetch_text(
        self,
        provider: WebSearchProvider,
        url: str,
        request_id: str,
        trace_id: str | None = None,
    ) -> str:
        if not self._is_allowed_url(url):
            self._audit("web.fetch", request_id, trace_id, cache_hit="false", url=url, error="domain_not_allowed")
            raise ToolPolicyError(f"domain not allowed: {url}")

        cache_key = f"fetch::{url}"
        if cache_key in self.cache:
            text = str(self.cache[cache_key])
            self._audit("web.fetch", request_id, trace_id, cache_hit="true", url=url, bytes=str(len(text)))
            return text

        self._consume_request_budget(request_id)
        raw_text = await provider.fetch_text(url)
        text = sanitize_untrusted_text(raw_text)
        self.cache[cache_key] = text
        self._audit("web.fetch", request_id, trace_id, cache_hit="false", url=url, bytes=str(len(text)))
        return text

    def _consume_request_budget(self, request_id: str) -> None:
        used = self._request_call_counts.get(request_id, 0) + 1
        if used > self.config.max_calls_per_request:
            raise ToolRateLimitError(
                f"request {request_id} exceeded max tool calls: {used}>{self.config.max_calls_per_request}"
            )
        self._request_call_counts[request_id] = used

    def _is_allowed_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        if not self.config.allowlist_domains:
            return True
        for allowed in self.config.allowlist_domains:
            domain = allowed.lower()
            if host == domain or host.endswith(f".{domain}"):
                return True
        return False

    def _audit(self, action: str, request_id: str, trace_id: str | None, **fields: str) -> None:
        entry = {
            "action": action,
            "request_id": request_id,
            "trace_id": trace_id or "",
            **{key: str(value) for key, value in fields.items()},
        }
        self.audit_logs.append(entry)
        if trace_id:
            log_event(trace_id, "tool_gateway", action, request_id=request_id, **fields)
