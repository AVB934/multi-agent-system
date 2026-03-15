from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.google_search_tool import google_search
from google.genai import types


class ADKGeminiTool:
    tool_id = "llm.adk"

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None) -> None:
        if not model.startswith("gemini-"):
            raise ValueError("ADKGeminiTool supports Gemini models only (model must start with 'gemini-').")
        self.model = model
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._redirect_cache: dict[str, str | None] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "ADKGeminiTool":
        return cls(
            model=os.getenv("MAS_GEMINI_MODEL", "gemini-2.0-flash"),
            api_key=os.getenv("GOOGLE_API_KEY"),
        )

    async def complete(self, *, system_instruction: str, user_prompt: str) -> str:
        result = await self._run_prompt(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            use_google_search=False,
        )
        return result["text"]

    async def complete_with_google_search(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
    ) -> dict[str, object]:
        return await self._run_prompt(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            use_google_search=True,
        )

    async def _run_prompt(
        self,
        *,
        system_instruction: str,
        user_prompt: str,
        use_google_search: bool,
    ) -> dict[str, object]:
        if not self.enabled:
            raise RuntimeError("GOOGLE_API_KEY is not configured for ADK Gemini")

        os.environ["GOOGLE_API_KEY"] = str(self.api_key)
        agent_tools = [google_search] if use_google_search else []
        agent = LlmAgent(
            name="mas_llm",
            model=self.model,
            instruction=system_instruction,
            tools=agent_tools,
        )
        runner = InMemoryRunner(agent=agent, app_name="mas_orchestrator")
        user_id = "mas_user"
        session_id = str(uuid4())
        await runner.session_service.create_session(
            app_name="mas_orchestrator",
            user_id=user_id,
            session_id=session_id,
        )

        content = types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
        final_text = ""
        citation_urls: list[str] = []
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if event.content and event.content.parts:
                parts_text = [part.text for part in event.content.parts if getattr(part, "text", None)]
                if parts_text:
                    final_text = "\n".join(parts_text).strip()
            citation_urls.extend(self._extract_urls_from_event(event))
            if event.is_final_response():
                break
        unique_urls: list[str] = []
        for url in citation_urls:
            if url not in unique_urls:
                unique_urls.append(url)
        return {"text": final_text.strip(), "citations": unique_urls}

    async def complete_json(self, *, system_instruction: str, user_prompt: str) -> dict[str, object]:
        raw = await self.complete(system_instruction=system_instruction, user_prompt=user_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned)

    def _extract_urls_from_event(self, event: object) -> list[str]:
        payload: list[str] = []
        grounding_metadata = getattr(event, "grounding_metadata", None)
        if grounding_metadata is not None:
            payload.extend(self._extract_urls_from_grounding_metadata(grounding_metadata))

        citation_metadata = getattr(event, "citation_metadata", None)
        if citation_metadata is not None:
            payload.extend(self._extract_urls_from_citation_metadata(citation_metadata))

        # Backward-compatible fallback in case ADK changes the metadata shape.
        if not payload:
            for attr in ("grounding_metadata", "citation_metadata"):
                value = getattr(event, attr, None)
                if value is None:
                    continue
                if hasattr(value, "model_dump"):
                    source = value.model_dump(mode="json")
                else:
                    source = value
                payload.extend(self._extract_urls_recursive(source))
        return self._dedupe_urls(payload)

    def _extract_urls_from_grounding_metadata(self, metadata: object) -> list[str]:
        chunks = getattr(metadata, "grounding_chunks", None)
        if chunks is None and hasattr(metadata, "model_dump"):
            chunks = metadata.model_dump(mode="json").get("grounding_chunks", [])
        urls: list[str] = []
        for chunk in chunks or []:
            web_chunk = getattr(chunk, "web", None)
            if web_chunk is None and isinstance(chunk, dict):
                web_chunk = chunk.get("web")
            url = self._normalize_citation_url(self._get_raw_field(web_chunk, "uri"))
            if url:
                urls.append(url)
        return urls

    def _extract_urls_from_citation_metadata(self, metadata: object) -> list[str]:
        citations = getattr(metadata, "citations", None)
        if citations is None and hasattr(metadata, "model_dump"):
            citations = metadata.model_dump(mode="json").get("citations", [])
        urls: list[str] = []
        for citation in citations or []:
            url = self._normalize_citation_url(self._get_raw_field(citation, "uri"))
            if url:
                urls.append(url)
        return urls

    def _get_raw_field(self, value: object, field_name: str) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            field = value.get(field_name)
        else:
            field = getattr(value, field_name, None)
        if field is None:
            return None
        return str(field)

    def _normalize_citation_url(self, url: str | None) -> str | None:
        if not url:
            return None
        candidate = url.strip()
        if "vertexaisearch.cloud.google.com/grounding-api-redirect/" in candidate:
            candidate = self._resolve_grounding_redirect(candidate) or candidate
        cleaned = self._clean_url(candidate)
        return cleaned or None

    def _resolve_grounding_redirect(self, url: str) -> str | None:
        if url in self._redirect_cache:
            return self._redirect_cache[url]

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        )
        resolved: str | None = None
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=10) as response:
                resolved = response.headers.get("Location") or response.geturl()
        except urllib.error.HTTPError as exc:
            resolved = exc.headers.get("Location") or exc.geturl()
        except Exception:
            resolved = None

        self._redirect_cache[url] = resolved
        return resolved

    def _clean_url(self, url: str) -> str | None:
        candidate = url.strip().rstrip(".,);")
        if not candidate.startswith(("http://", "https://")):
            return None
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if not host:
            return None
        if host == "vertexaisearch.cloud.google.com":
            return None
        if host in {"www.w3.org", "w3.org"} and parsed.path == "/2000/svg":
            return None
        return candidate

    def _dedupe_urls(self, urls: list[str]) -> list[str]:
        unique_urls: list[str] = []
        for url in urls:
            cleaned = self._clean_url(url)
            if cleaned and cleaned not in unique_urls:
                unique_urls.append(cleaned)
        return unique_urls

    def _extract_urls_recursive(self, value: object) -> list[str]:
        if isinstance(value, dict):
            urls: list[str] = []
            for child in value.values():
                urls.extend(self._extract_urls_recursive(child))
            return urls
        if isinstance(value, list):
            urls: list[str] = []
            for child in value:
                urls.extend(self._extract_urls_recursive(child))
            return urls
        if isinstance(value, str):
            return re.findall(r"https?://[^\s\"'<>]+", value)
        return []
