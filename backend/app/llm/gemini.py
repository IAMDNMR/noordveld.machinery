"""Google Gemini provider (optional; LLM_PROVIDER=gemini). REST with structured JSON output. The key is sent in a header, never in a
URL, and never logged. Prompts, schemas and validation are shared with every provider (app/llm/structured.py)."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.base import LLMInvalidResponse, LLMUnavailable
from app.llm.structured import MAX_OUTPUT_TOKENS, StructuredLLM, record

log = logging.getLogger("app.llm")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Standard JSON Schema -> Gemini's OpenAPI subset (upper-case types, `nullable`, no additionalProperties)."""
    out: dict[str, Any] = {}
    kind = schema.get("type")
    if isinstance(kind, list):
        out["nullable"] = "null" in kind
        kind = next(k for k in kind if k != "null")
    if kind:
        out["type"] = kind.upper()
    if "enum" in schema:
        out["enum"] = [v for v in schema["enum"] if v is not None]
    if "properties" in schema:
        out["properties"] = {k: gemini_schema(v) for k, v in schema["properties"].items()}
        out["required"] = list(schema.get("required", []))
    return out


class GeminiClient(StructuredLLM):
    name = "gemini"

    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")
        super().__init__(settings.llm_requests_per_minute)
        self._key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._http = http or httpx.Client(timeout=settings.llm_timeout)

    def _complete(self, kind: str, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        # newer models (3.5+) reject thinkingBudget and take thinkingLevel; both mean "answer directly, no long reasoning"
        version = re.match(r"gemini-(\d+(?:\.\d+)?)", self._model)
        thinking = {"thinkingLevel": "minimal"} if version and float(version.group(1)) >= 3.5 else {"thinkingBudget": 0}
        config: dict[str, Any] = {"temperature": 0, "maxOutputTokens": MAX_OUTPUT_TOKENS.get(kind, 250), "thinkingConfig": thinking}
        if schema:
            config.update(responseMimeType="application/json", responseSchema=gemini_schema(schema))
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
        started = time.perf_counter()
        for attempt in range(3):  # Google's 500/503 ("overloaded") are usually gone within seconds; quota (429) is never retried
            try:
                response = self._http.post(ENDPOINT.format(model=self._model), json=body, headers={"x-goog-api-key": self._key})
            except httpx.HTTPError as exc:
                record(self.name, self._model, kind, started, f"connection:{type(exc).__name__}", attempt)
                raise LLMUnavailable(type(exc).__name__) from exc
            if response.status_code not in (500, 503) or attempt == 2:
                break
            time.sleep(1.5 * (attempt + 1))
        if response.status_code != 200:
            record(self.name, self._model, kind, started, f"http_{response.status_code}", attempt)
            raise LLMUnavailable(f"HTTP {response.status_code}")
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as exc:
            record(self.name, self._model, kind, started, "bad_shape", attempt)
            raise LLMInvalidResponse("unexpected response shape") from exc
        record(self.name, self._model, kind, started, "ok", attempt, (data.get("usageMetadata") or {}).get("totalTokenCount"))
        return text
