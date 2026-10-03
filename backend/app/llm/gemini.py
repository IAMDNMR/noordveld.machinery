"""Google Gemini client (REST, structured JSON output). The API key is sent in a header, never in a URL, and never logged."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.base import LLMInvalidResponse, LLMParse, LLMUnavailable

log = logging.getLogger(__name__)
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

UNDERSTAND_RULES = (
    "You classify questions for a machinery parts knowledge graph. Choose exactly one intent from the list. "
    "Extract the entity names exactly as the user wrote them (part numbers, machine models, supplier, dealer or assembly names, category words) into `mentions`. "
    "Do not invent entities. If the question is not about parts, machines, fitment, suppliers, dealers, assemblies, compliance, stock, relationships, provenance or data quality, "
    "use UNSUPPORTED. If it is too vague to answer, set requires_clarification and ask one short question."
)

GROUNDING_RULES = (
    "You must answer ONLY from the supplied evidence. Do not add facts that are not present in the evidence. Do not infer relationships. "
    "Do not infer interchangeability, alternatives or replacements. Do not infer inventory. Do not infer supplier relationships. "
    "Do not infer geographic business relationships. Do not convert missing information into a negative fact. "
    "If the evidence does not contain the requested information, say that the information is unavailable or not connected. "
    "Write at most two short plain sentences. Do not list every item; the interface shows the items. Do not use numbers that are not in the evidence or draft."
)


class RateLimiter:
    """Sliding one-minute window, shared by every request in the process (the free tier is 15/min)."""

    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._stamps and now - self._stamps[0] > 60:
                self._stamps.popleft()
            if len(self._stamps) >= self._per_minute:
                return False
            self._stamps.append(now)
            return True


class GeminiClient:
    name = "gemini"

    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")
        self._key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._http = http or httpx.Client(timeout=settings.gemini_timeout)
        self._limit = RateLimiter(settings.gemini_requests_per_minute)

    def _generate(self, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        if not self._limit.allow():
            raise LLMUnavailable("rate limit reached")
        config: dict[str, Any] = {"temperature": 0, "maxOutputTokens": 600, "thinkingConfig": {"thinkingBudget": 0}}
        if schema:
            config.update(responseMimeType="application/json", responseSchema=schema)
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
        try:
            response = self._http.post(ENDPOINT.format(model=self._model), json=body, headers={"x-goog-api-key": self._key})
        except httpx.HTTPError as exc:
            log.warning("gemini request failed: %s", type(exc).__name__)
            raise LLMUnavailable(type(exc).__name__) from exc
        if response.status_code != 200:
            log.warning("gemini returned HTTP %s", response.status_code)
            raise LLMUnavailable(f"HTTP {response.status_code}")
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMInvalidResponse("unexpected response shape") from exc

    def parse_question(self, question: str, intents: dict[str, str]) -> LLMParse:
        schema = {
            "type": "OBJECT",
            "properties": {
                "intent": {"type": "STRING", "enum": [*intents, "UNSUPPORTED"]},
                "mentions": {"type": "ARRAY", "items": {"type": "STRING"}},
                "requires_clarification": {"type": "BOOLEAN"},
                "clarification_question": {"type": "STRING", "nullable": True},
            },
            "required": ["intent", "mentions", "requires_clarification"],
        }
        listing = "\n".join(f"- {name}: {desc}" for name, desc in intents.items())
        text = self._generate(UNDERSTAND_RULES, f"Intents:\n{listing}\n\nQuestion: {question}", schema)
        try:
            data = json.loads(text)
            return LLMParse(
                intent=str(data["intent"]),
                mentions=tuple(str(m) for m in data.get("mentions", []) if isinstance(m, str))[:6],
                requires_clarification=bool(data.get("requires_clarification", False)),
                clarification_question=data.get("clarification_question") or None,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMInvalidResponse("not valid structured output") from exc

    def resolve_entities(self, question: str, intents: dict[str, str]) -> tuple[str, ...]:
        return self.parse_question(question, intents).mentions

    def generate_grounded_response(self, question: str, intent: str, evidence: list[dict[str, Any]], draft: str) -> str:
        payload = json.dumps({"question": question, "intent": intent, "evidence": evidence[:40], "draft_answer": draft}, ensure_ascii=False)
        return self._generate(GROUNDING_RULES, payload, None).strip()
