"""What every provider shares: the output schemas, strict validation of what the model returns, rate limiting, call metrics, and
the four LLMClient operations built on one primitive, `_complete(kind, system, prompt, schema) -> str`.

A provider only implements `_complete` (transport, retries, error normalisation). It never sees a database, and nothing it
returns reaches a query before it has passed the validators below: intent against the approved list, entity kinds against
ENTITY_KEYS, enums against their values, numbers as numbers.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict, deque
from typing import Any

from app.llm.base import LLMInvalidResponse, LLMParse, LLMUnavailable, ShoppingParse
from app.llm.prompts import GROUNDING_RULES, SHOPPING_RULES, UNDERSTAND_RULES, question_prompt, shopping_prompt

log = logging.getLogger("app.llm")

# Token budget: replies are short structures or two sentences, and only the evidence the wording needs is sent.
# "question_retry" is the single second attempt after an unusable reply: temperature is 0, so the same cap would truncate the same way
MAX_OUTPUT_TOKENS = {"question": 320, "question_retry": 480, "shopping": 150, "grounded_answer": 120}
MAX_EVIDENCE_ITEMS = 12  # records sent to the wording step: the summary record plus up to 11 results

ENTITY_KEYS = ("part", "second_part", "machine", "supplier", "dealer", "assembly", "category", "order", "warehouse")
FILTER_KEYS = ("place", "place_kind", "proximity", "location", "brand", "target_kind", "single")

# ── schemas (standard JSON Schema; strict-mode compatible: every property required, nullable via type arrays) ─────────
_STR = {"type": ["string", "null"]}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def question_schema(intents: list[str]) -> dict[str, Any]:
    return _obj({
        "in_scope": {"type": "boolean"},
        "intent": {"type": "string", "enum": intents},
        "entities": _obj({k: _STR for k in ENTITY_KEYS}),
        "need": _STR,
        "filters": _obj({
            "place": _STR, "place_kind": {"type": ["string", "null"], "enum": ["DEALER", "SUPPLIER", "WAREHOUSE", None]},
            "proximity": {"type": ["string", "null"], "enum": ["in", "near", None]}, "location": _STR, "brand": _STR, "target_kind": _STR,
            "single": {"type": ["boolean", "null"]},
        }),
        "requires_clarification": {"type": "boolean"},
        "clarification_question": _STR,
    })


SHOPPING_SCHEMA = _obj({
    "in_scope": {"type": "boolean"}, "machine": _STR, "part_type": _STR,
    "preference": {"type": "string", "enum": ["cheapest", "fastest", "none"]}, "delivery_place": _STR,
    "quantity": {"type": ["integer", "null"]}, "clarification_question": _STR,
    "budget_max": {"type": ["number", "null"]}, "budget_currency": _STR,
    "availability": {"type": "string", "enum": ["require", "prefer", "future", "none"]},
})


# ── validation ───────────────────────────────────────────────────────────────────────────────────
def _load(text: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # reasoning models may prepend their thinking
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LLMInvalidResponse("not valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMInvalidResponse("not a JSON object")
    return data


def _text(v: Any) -> str | None:
    return v.strip() or None if isinstance(v, str) else None


def to_llm_parse(text: str, allowed: list[str]) -> LLMParse:
    """The model's reading of a question, validated. An intent outside `allowed` is rejected: the model cannot invent one."""
    data = _load(text)
    try:
        intent = data["intent"]
        if intent not in allowed:
            raise LLMInvalidResponse("intent outside the approved registry")
        if not isinstance(data["in_scope"], bool) or not isinstance(data.get("requires_clarification", False), bool):
            raise LLMInvalidResponse("scope verdict is not a boolean")
        entities = {k: v.strip() for k, v in (data.get("entities") or {}).items() if k in ENTITY_KEYS and isinstance(v, str) and v.strip()}
        filters: dict[str, Any] = {}
        for k, v in (data.get("filters") or {}).items():
            if k not in FILTER_KEYS or v in (None, "", False):
                continue
            if k == "single":
                filters[k] = v is True
            elif isinstance(v, str):
                filters[k] = v.strip()
        if filters.get("place_kind") not in (None, "DEALER", "SUPPLIER", "WAREHOUSE"):
            filters.pop("place_kind")
        if filters.get("proximity") not in (None, "in", "near"):
            filters.pop("proximity")
        confidence = data.get("confidence")
        return LLMParse(
            intent=intent,
            mentions=tuple(entities.values())[:6],
            requires_clarification=bool(data.get("requires_clarification", False)),
            clarification_question=_text(data.get("clarification_question")),
            filters={k: v for k, v in filters.items() if v not in (None, "")},
            entities=entities,
            in_scope=data["in_scope"] and data.get("domain", "parts_intelligence") == "parts_intelligence",
            need=_text(data.get("need")),
            confidence=float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None,
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise LLMInvalidResponse("not valid structured output") from exc


def to_shopping_parse(text: str) -> ShoppingParse:
    """The model's reading of a purchase request, validated and normalised. A budget must be a positive number; nothing is guessed."""
    data = _load(text)
    try:
        if not isinstance(data["in_scope"], bool):
            raise LLMInvalidResponse("scope verdict is not a boolean")
        qty, budget = data.get("quantity"), data.get("budget_max")
        number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
        return ShoppingParse(
            in_scope=data["in_scope"], machine=_text(data.get("machine")), part_type=_text(data.get("part_type")),
            preference=data.get("preference") if data.get("preference") in ("cheapest", "fastest") else "none",
            delivery_place=_text(data.get("delivery_place")),
            quantity=int(qty) if number(qty) and float(qty).is_integer() and 0 < qty < 1000 else None,
            clarification_question=_text(data.get("clarification_question")),
            budget_max=float(budget) if number(budget) and budget > 0 else None,
            budget_currency=(_text(data.get("budget_currency")) or "").upper() or None,
            availability=data.get("availability") if data.get("availability") in ("require", "prefer", "future") else "none",
        )
    except (KeyError, TypeError) as exc:
        raise LLMInvalidResponse("not valid structured output") from exc


def compact_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only what the wording can use: the first MAX_EVIDENCE_ITEMS records, without empty fields. The draft already carries the totals."""
    return [{k: v for k, v in item.items() if v not in (None, "", [], {})} for item in evidence[:MAX_EVIDENCE_ITEMS]]


# ── rate limiting and metrics ────────────────────────────────────────────────────────────────────
class RateLimiter:
    """Sliding one-minute window, shared by every request in the process."""

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


def record(provider: str, model: str, kind: str, started: float, outcome: str, retries: int = 0, tokens: int | None = None) -> None:
    """One line per model call: provider, model, request type, latency, outcome, retries, tokens. Never a key, header or prompt."""
    log.info("llm call provider=%s model=%s kind=%s latency_ms=%d outcome=%s retries=%d tokens=%s",
             provider, model, kind, (time.perf_counter() - started) * 1000, outcome, retries, tokens if tokens is not None else "-")


# ── the operations, shared by every provider ─────────────────────────────────────────────────────
class StructuredLLM:
    """Implements LLMClient on top of `_complete`. Identical requests are understood once per process (saves quota)."""

    name = "base"
    _model = ""
    CACHE_SIZE = 256

    def __init__(self, per_minute: int) -> None:
        self._limit = RateLimiter(per_minute)
        self._cache: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._cache_lock = threading.Lock()

    def _complete(self, kind: str, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        raise NotImplementedError

    def _guarded(self, kind: str, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        if not self._limit.allow():
            log.warning("llm call provider=%s kind=%s outcome=local_rate_limit", self.name, kind)
            raise LLMUnavailable("rate limit reached")
        return self._complete(kind, system, prompt, schema)

    def _cached(self, kind: str, text: str, make):
        key = (kind, " ".join(text.lower().split()))
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        value = make()
        with self._cache_lock:
            self._cache[key] = value
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return value

    def parse_question(self, question: str, intents: dict[str, str]) -> LLMParse:
        allowed = [*intents, "UNSUPPORTED"]

        def understand() -> LLMParse:
            prompt, schema = question_prompt(question, intents), question_schema(allowed)
            try:
                return to_llm_parse(self._guarded("question", UNDERSTAND_RULES, prompt, schema), allowed)
            except LLMInvalidResponse:  # one retry, with a larger output cap: a reply cut off at the cap would be cut off again at the same cap
                log.info("llm call provider=%s kind=question outcome=invalid_retry", self.name)
                return to_llm_parse(self._guarded("question_retry", UNDERSTAND_RULES, prompt, schema), allowed)

        return self._cached("question", question + "\x00" + ",".join(allowed), understand)

    def resolve_entities(self, question: str, intents: dict[str, str]) -> tuple[str, ...]:
        return self.parse_question(question, intents).mentions

    def parse_shopping_request(self, request: str) -> ShoppingParse:
        return self._cached("shopping", request, lambda: to_shopping_parse(self._guarded("shopping", SHOPPING_RULES, shopping_prompt(request), SHOPPING_SCHEMA)))

    def generate_grounded_response(self, question: str, intent: str, evidence: list[dict[str, Any]], draft: str) -> str:
        payload = json.dumps({"question": question, "intent": intent, "draft_answer": draft, "evidence": compact_evidence(evidence)},
                             ensure_ascii=False, separators=(",", ":"))
        text = self._guarded("grounded_answer", GROUNDING_RULES, payload, None)
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
