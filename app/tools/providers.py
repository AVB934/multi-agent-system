from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlparse
from typing import Protocol

import httpx

from app.runtime.security import sanitize_untrusted_text
from app.tools.base import SearchResult


class WebSearchProvider(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...

    async def fetch_text(self, url: str) -> str: ...


@dataclass
class InMemoryWebSearchProvider:
    """Deterministic provider for dev/tests until real web integration is wired."""

    search_results_by_query: dict[str, list[SearchResult]] = field(default_factory=dict)
    page_text_by_url: dict[str, str] = field(default_factory=dict)
    search_calls: int = 0
    fetch_calls: int = 0

    async def search(self, query: str) -> list[SearchResult]:
        self.search_calls += 1
        safe_query = sanitize_untrusted_text(query)
        if safe_query in self.search_results_by_query:
            return list(self.search_results_by_query[safe_query])
        default_url = "https://example.com/stub-result"
        return [
            SearchResult(
                title=f"Stub result for: {safe_query}",
                url=default_url,
                snippet="Stubbed web search response.",
            )
        ]

    async def fetch_text(self, url: str) -> str:
        self.fetch_calls += 1
        return self.page_text_by_url.get(url, f"Stub page text for {url}.")


@dataclass
class DuckDuckGoWebSearchProvider:
    """Real web provider using DuckDuckGo HTML search plus direct page fetch."""

    user_agent: str = "mas-bot/0.1"
    timeout_seconds: float = 15.0
    max_results: int = 5
    search_calls: int = 0
    fetch_calls: int = 0

    async def search(self, query: str) -> list[SearchResult]:
        self.search_calls += 1
        safe_query = sanitize_untrusted_text(query).strip()
        if not safe_query:
            return []

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(safe_query)}"
        html = await self._get_text(url)
        return self._parse_search_results(html)[: self.max_results]

    async def fetch_text(self, url: str) -> str:
        self.fetch_calls += 1
        html = await self._get_text(url)
        return self._html_to_text(html)

    async def _get_text(self, url: str) -> str:
        headers = {"user-agent": self.user_agent}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _parse_search_results(self, html: str) -> list[SearchResult]:
        pattern = re.compile(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippets = re.findall(
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        parsed_snippets = [self._html_to_text(" ".join(parts)) for parts in snippets]

        results: list[SearchResult] = []
        for index, match in enumerate(pattern.finditer(html)):
            href = unescape(match.group("href"))
            url = self._normalize_result_url(href)
            if not url:
                continue
            title = self._html_to_text(match.group("title"))
            snippet = parsed_snippets[index] if index < len(parsed_snippets) else ""
            results.append(
                SearchResult(
                    title=title or url,
                    url=url,
                    snippet=snippet,
                )
            )
        return results

    def _normalize_result_url(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return href
        if parsed.path == "/l/" or parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [])
            if uddg:
                return unescape(uddg[0])
        return ""

    def _html_to_text(self, html: str) -> str:
        cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return sanitize_untrusted_text(cleaned)
