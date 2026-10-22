"""The provider layer: configuration, the Groq client against a mocked transport (no quota spent), validation of what any model
returns, error normalisation, and Parts Intelligence / Agentic Shopping running through the provider abstraction end to end.
The opt-in live smoke test (RUN_LLM_LIVE_TESTS=true) makes three real requests."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm
from app.core.config import Settings, get_settings
from app.llm import LLMInvalidResponse, LLMUnavailable, create_llm
from app.llm.gemini import GeminiClient, gemini_schema
from app.llm.groq import ENDPOINT, GroqClient
from app.llm.structured import SHOPPING_SCHEMA, question_schema, to_llm_parse, to_shopping_parse
from app.main import app
from tests.support.live import live, live_model

KEY = "gsk_test_not_a_real_key_000"
INTENTS = {"MACHINE_LIST": "List machines", "PART_TO_MACHINE": "Machines a part fits", "PART_TO_SUPPLIER": "Suppliers of a part"}
EMPTY_ENTITIES = {k: None for k in ("part", "second_part", "machine", "supplier", "dealer", "assembly", "category", "order")}
EMPTY_FILTERS = {k: None for k in ("place", "place_kind", "proximity", "location", "brand", "target_kind", "single")}


def understood(intent, in_scope=True, clarify=False, question=None, **entities):
    return {"in_scope": in_scope, "domain": "parts_intelligence" if in_scope else "out_of_scope", "intent": intent,
            "entities": {**EMPTY_ENTITIES, **entities}, "filters": EMPTY_FILTERS, "requires_clarification": clarify,
            "clarification_question": question, "confidence": 0.9}


def shopping(**kw):
    base = {"in_scope": True, "machine": None, "part_type": None, "preference": "none", "delivery_place": None, "quantity": None,
            "clarification_question": None, "budget_max": None, "budget_currency": None, "availability": "none"}
    return {**base, **kw}


def completion(content, status=200, headers=None):
    body = {"choices": [{"message": {"content": content if isinstance(content, str) else json.dumps(content)}}], "usage": {"total_tokens": 42}}
    return httpx.Response(status, json=body if status == 200 else {"error": {"message": "provider internals"}}, headers=headers)


def groq(handler, **settings) -> GroqClient:
    return GroqClient(Settings(groq_api_key=KEY, **settings), httpx.Client(transport=httpx.MockTransport(handler)))


# ── 1. configuration ─────────────────────────────────────────────────────────────────────────────






# ── 2. missing key ───────────────────────────────────────────────────────────────────────────────


# ── 3–4. the client and structured extraction ────────────────────────────────────────────────────
def test_groq_request_is_openai_compatible_with_strict_schema_and_key_only_in_the_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return completion(understood("PART_TO_SUPPLIER", part="NVM-1010-HY"))

    parse = groq(handler, groq_model="qwen/qwen3.8-27b").parse_question("Who supplies NVM-1010-HY?", INTENTS)
    assert parse.intent == "PART_TO_SUPPLIER" and parse.entities == {"part": "NVM-1010-HY"} and parse.in_scope
    assert seen["url"] == ENDPOINT and KEY not in seen["url"] and seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    assert body["model"] == "qwen/qwen3.8-27b" and body["temperature"] == 0 and body["messages"][0]["role"] == "system"
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["properties"]["intent"]["enum"] == [*INTENTS, "UNSUPPORTED"]
    assert "Cypher" in body["messages"][0]["content"] and "Who supplies NVM-1010-HY?" in body["messages"][1]["content"]






# ── 5–6. validation ──────────────────────────────────────────────────────────────────────────────


def test_malformed_and_unexpected_output_is_rejected_not_trusted():
    allowed = [*INTENTS, "UNSUPPORTED"]
    for bad in ("not json", "[1, 2]", json.dumps({"intent": "MACHINE_LIST"}), json.dumps({**understood("MACHINE_LIST"), "in_scope": "yes"})):
        with pytest.raises(LLMInvalidResponse):
            to_llm_parse(bad, allowed)
    with pytest.raises(LLMInvalidResponse):
        to_shopping_parse(json.dumps({"machine": "NV-4500"}))
    with pytest.raises(LLMInvalidResponse):
        groq(lambda r: httpx.Response(200, json={"unexpected": True})).parse_question("q", INTENTS)
    with pytest.raises(LLMInvalidResponse):
        groq(lambda r: completion("")).parse_shopping_request("q")
















# ── 7–8. errors are normalised; retries are conservative ─────────────────────────────────────────




def test_invalid_key_and_daily_quota_are_never_retried(monkeypatch):
    monkeypatch.setattr("app.llm.groq.time.sleep", lambda s: None)
    for status, headers in ((401, None), (429, {"retry-after": "64000"})):
        calls = {"n": 0}

        def handler(request, s=status, h=headers):
            calls["n"] += 1
            return completion(None, status=s, headers=h)

        with pytest.raises(LLMUnavailable):
            groq(handler).parse_question("q", INTENTS)
        assert calls["n"] == 1






# ── 9–10. both features run through the abstraction (mocked Groq, live graph) ────────────────────
graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")

QUESTIONS = {
    "What machines are available?": understood("MACHINE_LIST"),
    "What parts fit the NV-4500?": understood("MACHINE_TO_PART", machine="NV-4500"),
    "What machines does NVM-1010-HY fit?": understood("PART_TO_MACHINE", part="NVM-1010-HY"),
    "Who supplies NVM-1010-HY?": understood("PART_TO_SUPPLIER", part="NVM-1010-HY"),
    "Where is NVM-1010-HY available?": understood("PART_TO_INVENTORY", part="NVM-1010-HY"),
    "Show provenance for NVM-1010-HY.": understood("PART_PROVENANCE", part="NVM-1010-HY"),
    "What is the capital of France?": understood("UNSUPPORTED", in_scope=False),
}
REQUESTS = {
    "I need a hydraulic hose for NV-4500.": shopping(machine="NV-4500", part_type="hydraulic hose"),
    "I need the cheapest hydraulic hose for NV-4500.": shopping(machine="NV-4500", part_type="hydraulic hose", preference="cheapest"),
    "I need a hydraulic hose for NV-4500 under €200.": shopping(machine="NV-4500", part_type="hydraulic hose", budget_max=200, budget_currency="EUR"),
    "I need a hydraulic hose for NV-4500 delivered to Zwolle tomorrow.": shopping(machine="NV-4500", part_type="hydraulic hose", delivery_place="Zwolle", preference="fastest"),
    "I need the fastest hydraulic hose for NV-4500.": shopping(machine="NV-4500", part_type="hydraulic hose", preference="fastest"),
}


def mocked_groq():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        user = body["messages"][1]["content"]
        if body.get("response_format") is None:  # the grounded wording call: repeat the draft answer
            return completion(json.loads(user)["draft_answer"])
        table = REQUESTS if user.startswith("Request: ") else QUESTIONS
        text = user.removeprefix("Request: ").split("Question: ")[-1]
        return completion(table[text])
    return groq(handler)


@pytest.fixture()
def api():
    model = mocked_groq()
    app.dependency_overrides[get_llm] = lambda: model
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_llm, None)






# ── opt-in live smoke test (three real requests) ─────────────────────────────────────────────────


# ── token budget ─────────────────────────────────────────────────────────────────────────────────
