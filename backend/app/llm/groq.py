"""Groq Cloud provider (OpenAI-compatible chat completions, strict JSON-schema output).

The key travels only in the Authorization header of requests to api.groq.com. It is never logged, never in a URL, never in an
error message, and never returned by the API. Every failure is normalised to LLMUnavailable or LLMInvalidResponse.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.base import LLMInvalidResponse, LLMUnavailable
from app.llm.structured import MAX_OUTPUT_TOKENS, StructuredLLM, record

log = logging.getLogger("app.llm")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
TRANSIENT = (500, 502, 503, 504)
MAX_RATE_WAIT = 8.0  # a per-minute token limit usually clears in seconds: wait once for that, never for a daily quota


class GroqClient(StructuredLLM):
    name = "groq"

    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        if not settings.groq_api_key:
            raise LLMUnavailable("GROQ_API_KEY is not configured")
        super().__init__(settings.llm_requests_per_minute)
        self._key = settings.groq_api_key
        self._model = settings.groq_model
        self._http = http or httpx.Client(timeout=settings.llm_timeout)

    def _complete(self, kind: str, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_completion_tokens": MAX_OUTPUT_TOKENS.get(kind, 250),
            "reasoning_effort": "none",  # language understanding, not deliberation: answer directly
        }
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": kind, "strict": True, "schema": schema}}
        started, retries, overloads, waited = time.perf_counter(), 0, 0, False
        while True:
            try:
                response = self._http.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {self._key}"})
            except httpx.TimeoutException as exc:
                record(self.name, self._model, kind, started, "timeout", retries)
                raise LLMUnavailable("timed out") from exc
            except httpx.HTTPError as exc:
                record(self.name, self._model, kind, started, f"connection:{type(exc).__name__}", retries)
                raise LLMUnavailable(type(exc).__name__) from exc
            status = response.status_code
            if status in TRANSIENT and overloads < 2:  # provider overload: brief backoff, at most twice
                overloads, retries = overloads + 1, retries + 1
                time.sleep(1.0 * overloads)
                continue
            if status == 429 and not waited:
                wait = _retry_after(response)
                if wait is not None and wait <= MAX_RATE_WAIT:
                    waited, retries = True, retries + 1
                    time.sleep(wait)
                    continue
            break
        if status != 200:
            outcome = {401: "invalid_key", 403: "forbidden", 404: "model_unavailable", 429: "rate_limited"}.get(status, f"http_{status}")
            record(self.name, self._model, kind, started, outcome, retries)
            if status == 400 and schema:
                raise LLMInvalidResponse("the model could not produce the required structure")
            raise LLMUnavailable(outcome)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            tokens = (data.get("usage") or {}).get("total_tokens")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            record(self.name, self._model, kind, started, "bad_shape", retries)
            raise LLMInvalidResponse("unexpected response shape") from exc
        if not isinstance(text, str) or not text.strip():
            record(self.name, self._model, kind, started, "empty", retries, tokens)
            raise LLMInvalidResponse("empty response")
        record(self.name, self._model, kind, started, "ok", retries, tokens)
        return text


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
