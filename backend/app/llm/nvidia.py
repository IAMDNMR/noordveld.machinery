"""NVIDIA NIM provider (OpenAI-compatible chat completions) for the Design Studio conversation.

Selected with `AI_PROVIDER=nvidia`; the planner model (`NVIDIA_PLANNER_MODEL`) writes the plan. The key travels only in the
Authorization header to integrate.api.nvidia.com and never appears in a log, URL, error or response. Reasoning is switched off
(`enable_thinking: false`): the conversation needs a direct, structured answer quickly, and a reasoning model would spend its
whole token budget thinking. Every failure becomes LLMUnavailable or LLMInvalidResponse.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.base import LLMInvalidResponse, LLMUnavailable
from app.llm.structured import JSON_KINDS, MAX_OUTPUT_TOKENS, StructuredLLM, record

log = logging.getLogger("app.llm")
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
TRANSIENT = (500, 502, 503, 504)


class NvidiaClient(StructuredLLM):
    name = "nvidia"

    def __init__(
        self, settings: Settings, http: httpx.Client | None = None, model: str | None = None
    ) -> None:
        if not settings.nvidia_api_key:
            raise LLMUnavailable("NVIDIA_API_KEY is not configured")
        super().__init__(settings.llm_requests_per_minute)
        self._key = settings.nvidia_api_key
        self._model = model or settings.nvidia_planner_model or settings.nvidia_fast_model
        if not self._model:
            raise LLMUnavailable("NVIDIA_PLANNER_MODEL is not configured")
        self._http = http or httpx.Client(
            timeout=max(settings.llm_timeout, 45.0)
        )  # a large planner model needs more than a classifier does

    def _complete(self, kind: str, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4 if kind.startswith("studio_frontend") else 0,
            "max_tokens": MAX_OUTPUT_TOKENS.get(kind, 250),
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if schema:
            body["nvext"] = {"guided_json": schema}
        elif kind in JSON_KINDS:
            body["response_format"] = {"type": "json_object"}
        started, retries = time.perf_counter(), 0
        while True:
            try:
                response = self._http.post(
                    ENDPOINT,
                    json=body,
                    headers={"Authorization": f"Bearer {self._key}"},
                    timeout=480.0
                    if kind.startswith("studio_frontend")
                    else 300.0
                    if kind in {"studio_blueprint", "studio_frontend"}
                    else 240.0
                    if kind == "studio_turn"
                    else self._http.timeout,
                )
            except httpx.TimeoutException as exc:
                record(self.name, self._model, kind, started, "timeout", retries)
                raise LLMUnavailable("timed out") from exc
            except httpx.HTTPError as exc:
                if isinstance(exc, (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError)) and retries < 2:
                    retries += 1  # a dropped connection is not a refusal: try the same request again
                    time.sleep(2.0 * retries)
                    continue
                record(
                    self.name,
                    self._model,
                    kind,
                    started,
                    f"connection:{type(exc).__name__}",
                    retries,
                )
                raise LLMUnavailable(type(exc).__name__) from exc
            if (
                response.status_code in TRANSIENT and retries < 2
            ):  # "temporarily overloaded" usually clears within seconds
                retries += 1
                time.sleep(1.0 * retries)
                continue
            if response.status_code == 429 and retries < 4:
                # A burst of generation calls can hit the per-minute limit: wait as long as the service asks, then try again.
                retries += 1
                try:
                    wait = float(response.headers.get("retry-after", ""))
                except ValueError:
                    wait = 15.0 * retries
                time.sleep(min(max(wait, 5.0), 60.0))
                continue
            break
        if response.status_code != 200:
            outcome = {
                401: "invalid_key",
                403: "forbidden",
                404: "model_unavailable",
                429: "rate_limited",
            }.get(response.status_code, f"http_{response.status_code}")
            record(self.name, self._model, kind, started, outcome, retries)
            if response.status_code == 400:
                raise LLMInvalidResponse("the model rejected the request")
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
