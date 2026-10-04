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
def test_groq_is_the_default_provider_and_model_and_keys_never_show_in_repr():
    s = Settings(groq_api_key=KEY)
    assert s.llm_provider == "groq" and s.groq_model == "qwen/qwen3.8-27b" and s.llm_configured
    assert KEY not in repr(s)
    assert not Settings().llm_configured and not Settings(llm_provider="gemini", groq_api_key=KEY).llm_configured


def test_the_running_configuration_selects_groq():
    s = get_settings()
    assert s.llm_provider == "groq"
    if s.llm_configured:
        assert isinstance(create_llm(s), GroqClient)


def test_create_llm_picks_the_provider_and_rejects_unknown_ones():
    assert isinstance(create_llm(Settings(groq_api_key=KEY)), GroqClient)
    assert isinstance(create_llm(Settings(llm_provider="gemini", gemini_api_key="g-key")), GeminiClient)
    assert create_llm(Settings()) is None  # no key: the language routes answer 503, nothing else breaks
    with pytest.raises(ValueError):
        create_llm(Settings(llm_provider="other", groq_api_key=KEY))


# ── 2. missing key ───────────────────────────────────────────────────────────────────────────────
def test_missing_key_fails_cleanly():
    with pytest.raises(LLMUnavailable) as e:
        GroqClient(Settings())
    assert "GROQ_API_KEY" in str(e.value)


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


def test_shopping_constraints_are_extracted_and_typed():
    model = groq(lambda r: completion(shopping(machine="NV-4500", part_type="hydraulic hose", preference="cheapest", delivery_place="Zwolle",
                                               budget_max=200, budget_currency="eur", quantity=2)))
    p = model.parse_shopping_request("cheapest hydraulic hose for NV-4500 under €200, two of them, to Zwolle")
    assert (p.machine, p.part_type, p.preference, p.delivery_place, p.budget_max, p.budget_currency, p.quantity) == \
           ("NV-4500", "hydraulic hose", "cheapest", "Zwolle", 200.0, "EUR", 2)


def test_the_same_request_is_understood_once():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return completion(shopping(machine="NV-4500"))

    model = groq(handler)
    model.parse_shopping_request("I need a filter for my NV-4500")
    model.parse_shopping_request("i need a filter  for my NV-4500")
    assert calls["n"] == 1


# ── 5–6. validation ──────────────────────────────────────────────────────────────────────────────
def test_an_intent_outside_the_registry_is_rejected():
    with pytest.raises(LLMInvalidResponse):
        to_llm_parse(json.dumps(understood("DROP_DATABASE")), [*INTENTS, "UNSUPPORTED"])
    with pytest.raises(LLMInvalidResponse):
        groq(lambda r: completion(understood("RUN_CYPHER"))).parse_question("q", INTENTS)


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


def test_a_truncated_understanding_reply_is_retried_once_with_a_larger_cap():
    replies = ['{"in_scope": true, "intent": "MACHI', understood("MACHINE_LIST")]
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return completion(replies[min(len(bodies) - 1, 1)])
    assert groq(handler).parse_question("What machines are available?", INTENTS).intent == "MACHINE_LIST" and len(bodies) == 2
    # temperature is 0, so the identical request would be cut off at the identical place: the retry is the same request with a bigger cap
    assert [b["max_completion_tokens"] for b in bodies] == [320, 480] and [b["messages"] for b in bodies][0] == [b["messages"] for b in bodies][1]
    assert bodies[1]["response_format"]["json_schema"]["strict"] is True  # still strictly validated


def test_a_second_unusable_reply_is_a_controlled_failure_not_a_loop_or_a_guess():
    seen = []
    with pytest.raises(LLMInvalidResponse):
        groq(lambda r: (seen.append(1), completion("not json"))[1]).parse_question("q", INTENTS)
    assert len(seen) == 2  # one retry, never more
    seen.clear()
    with pytest.raises(LLMInvalidResponse):  # an intent the registry does not know is invalid too: retried once, then refused
        groq(lambda r: (seen.append(1), completion(understood("RUN_CYPHER")))[1]).parse_question("q", INTENTS)
    assert len(seen) == 2
    seen.clear()
    with pytest.raises(LLMInvalidResponse):  # the provider cannot produce the structure (HTTP 400 with a schema): the same path
        groq(lambda r: (seen.append(1), httpx.Response(400, json={"error": {"message": "x"}}))[1]).parse_question("q", INTENTS)
    assert len(seen) == 2


def test_a_provider_outage_is_not_retried_as_malformed_output():
    seen = []
    with pytest.raises(LLMUnavailable):
        groq(lambda r: (seen.append(1), httpx.Response(401, json={"error": {"message": "x"}}))[1]).parse_question("q", INTENTS)
    assert len(seen) == 1  # an invalid key is unavailable, not malformed: no second request


def test_malformed_model_output_through_the_api_is_a_502_and_never_reaches_neo4j_or_another_router():
    class NoGraph:
        def __getattr__(self, name):
            raise AssertionError(f"the graph was used: {name}")

    class AlwaysMalformed:
        name = "malformed"
        calls = 0

        def parse_question(self, question, intents):
            AlwaysMalformed.calls += 1
            raise LLMInvalidResponse("not valid structured output")

        def resolve_entities(self, question, intents):
            return ()

        def generate_grounded_response(self, *a):
            raise AssertionError("no answer may be written")

    from app.api.dependencies import get_graph
    app.dependency_overrides[get_graph] = lambda: NoGraph()
    app.dependency_overrides[get_llm] = lambda: AlwaysMalformed()
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/intelligence/query", json={"question": "Which machines use NVM-1010-AT?"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 502 and r.json()["error"]["code"] == "llm_invalid_response" and AlwaysMalformed.calls == 1  # no keyword router took over


def test_the_understanding_request_stays_inside_its_token_budget():
    from app.intelligence.registry import HINTS, answerable_intents
    from app.llm.prompts import UNDERSTAND_RULES, question_prompt

    intents = {i.value: HINTS[i] for i in answerable_intents()}
    request = {"system": UNDERSTAND_RULES, "prompt": question_prompt("Which machines use NVM-1010-AT?", intents), "schema": question_schema([*intents, "UNSUPPORTED"])}
    size = len(json.dumps(request, separators=(",", ":")))
    assert size < 6200, f"the understanding request grew to {size} characters (it was 8,600 before it was made compact; about 6 characters per token)"
    assert all(name in request["prompt"] for name in intents) and "Cypher" in UNDERSTAND_RULES  # every intent is still listed; the safety statements remain


def test_values_are_normalised_and_unknown_fields_dropped():
    p = to_llm_parse(json.dumps({**understood("MACHINE_LIST"), "entities": {**EMPTY_ENTITIES, "machine": "  NV-4500 ", "cypher": "MATCH (n) DETACH DELETE n"},
                                 "filters": {**EMPTY_FILTERS, "place_kind": "BUNKER", "single": True}}), [*INTENTS, "UNSUPPORTED"])
    assert p.entities == {"machine": "NV-4500"} and p.filters == {"single": True}
    s = to_shopping_parse(json.dumps(shopping(budget_max=-5, quantity=2.5, preference="free", availability="always")))
    assert s.budget_max is None and s.quantity is None and s.preference == "none" and s.availability == "none"
    s = to_shopping_parse("<think>budget</think>```json\n" + json.dumps(shopping(budget_max=True)) + "\n```")
    assert s.budget_max is None  # a boolean is not a number


def test_schemas_are_strict_and_convert_for_the_optional_gemini_provider():
    for schema in (question_schema(["A", "UNSUPPORTED"]), SHOPPING_SCHEMA):
        assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    g = gemini_schema(SHOPPING_SCHEMA)
    assert g["type"] == "OBJECT" and g["properties"]["budget_max"] == {"nullable": True, "type": "NUMBER"} and "additionalProperties" not in g


# ── 7–8. errors are normalised; retries are conservative ─────────────────────────────────────────
def test_errors_are_normalised_and_never_carry_provider_details():
    for status in (401, 403, 404, 429):
        with pytest.raises(LLMUnavailable) as e:
            groq(lambda r, s=status: completion(None, status=s)).parse_question("q", INTENTS)
        assert "provider internals" not in str(e.value) and KEY not in str(e.value)
    with pytest.raises(LLMInvalidResponse):  # Groq rejects output that fails the strict schema with a 400
        groq(lambda r: completion(None, status=400)).parse_question("q", INTENTS)


def test_timeout_and_connection_failures_are_unavailable():
    for exc in (httpx.ReadTimeout("slow"), httpx.ConnectError("down")):
        with pytest.raises(LLMUnavailable):
            groq(lambda r, e=exc: (_ for _ in ()).throw(e)).parse_question("q", INTENTS)


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


def test_a_short_rate_limit_and_an_overload_are_retried_once_each(monkeypatch):
    slept = []
    monkeypatch.setattr("app.llm.groq.time.sleep", slept.append)
    replies = iter([completion(None, status=429, headers={"retry-after": "2"}), completion(None, status=503), completion(understood("MACHINE_LIST"))])
    assert groq(lambda r: next(replies)).parse_question("q", INTENTS).intent == "MACHINE_LIST"
    assert slept == [2.0, 1.0]


def test_the_local_rate_limit_stops_a_retry_storm():
    model = groq(lambda r: completion(shopping()), llm_requests_per_minute=2)
    model.parse_shopping_request("a")
    model.parse_shopping_request("b")
    with pytest.raises(LLMUnavailable):
        model.parse_shopping_request("c")


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


@graph
@pytest.mark.parametrize("question,intent", [(q, d["intent"]) for q, d in QUESTIONS.items()])
def test_parts_intelligence_routes_through_the_provider(api, question, intent):
    r = api.post("/api/v1/intelligence/query", json={"question": question}).json()
    assert r["intent"] == intent and r["understood_by"] == "llm", r
    if intent == "MACHINE_LIST":
        assert r["results"] and r["clarification"] is None  # never "what part do you mean?"
    if intent == "UNSUPPORTED":
        assert r["results"] == []
    if intent in ("PART_TO_SUPPLIER", "PART_PROVENANCE", "PART_TO_MACHINE", "MACHINE_TO_PART"):
        assert r["results"], r


@graph
def test_agentic_shopping_routes_through_the_provider(api):
    out = {q: api.post("/api/v1/agent/recommend", json={"request": q}).json() for q in REQUESTS}
    base = out["I need a hydraulic hose for NV-4500."]
    assert base["state"] == "recommendation" and base["interpretation"]["machine"] == "NV-4500"
    cheap = out["I need the cheapest hydraulic hose for NV-4500."]
    prices = [c["part"]["price"]["amount"] for c in cheap["candidates"]]
    assert cheap["interpretation"]["preference"] == "cheapest" and prices == sorted(prices)
    budget = out["I need a hydraulic hose for NV-4500 under €200."]
    assert budget["interpretation"]["budget_max"] == 200 and all(c["part"]["price"]["amount"] <= 200 for c in budget["candidates"])
    zwolle = out["I need a hydraulic hose for NV-4500 delivered to Zwolle tomorrow."]
    assert zwolle["interpretation"]["delivery_place"] == "Zwolle" and zwolle["interpretation"]["preference"] == "fastest"
    assert out["I need the fastest hydraulic hose for NV-4500."]["interpretation"]["preference"] == "fastest"


# ── opt-in live smoke test (three real requests) ─────────────────────────────────────────────────
@live
def test_live_groq_smoke():
    model = live_model(worded=True)
    assert model.name == get_settings().llm_provider
    from app.intelligence.registry import REGISTRY, answerable_intents

    intents = {i.value: REGISTRY[i].description for i in answerable_intents()}
    assert model.parse_question("What machines are available?", intents).intent == "MACHINE_LIST"
    assert model.parse_question("What is the capital of France?", intents).in_scope is False
    s = model.parse_shopping_request("I need the cheapest hydraulic hose for my NV-4500 under €200")
    assert s.machine == "NV-4500" and s.preference == "cheapest" and s.budget_max == 200


# ── token budget ─────────────────────────────────────────────────────────────────────────────────
def test_only_needed_data_is_sent_and_replies_are_capped():
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        return completion("Two short sentences." if body.get("response_format") is None else shopping())

    model = groq(handler)
    evidence = [{"entity": f"P-{n}", "relationship": "FITS", "target": "M-1", "note": None, "extra": ""} for n in range(40)]
    model.generate_grounded_response("q", "PART_TO_MACHINE", evidence, "P-0 fits 40 machines.")
    model.parse_shopping_request("a filter for M-1")
    wording, shop = sent
    payload = json.loads(wording["messages"][1]["content"])
    assert len(payload["evidence"]) == 12 and all("note" not in e and "extra" not in e for e in payload["evidence"])
    assert ": " not in wording["messages"][1]["content"]  # compact JSON
    assert wording["max_completion_tokens"] == 120 and shop["max_completion_tokens"] == 150
