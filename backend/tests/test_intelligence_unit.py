"""Parts Intelligence without Neo4j or a live model: registry, Cypher safety, grounding, Gemini-first routing and data-truth behaviour.

`FakeLLM` stands in for Gemini. Unless a test hands it an explicit parse, it answers like a model would (tests/support/keyword_model.py is a
test double; the application itself contains no keyword routing).
"""
from __future__ import annotations

import re
from typing import Any

import httpx
import json

import pytest

from app.core.config import Settings
from app.graph.queries import intelligence as queries
from app.intelligence.identifiers import identifiers
from tests.support.keyword_model import model_parse
from app.intelligence.grounding import is_grounded
from app.intelligence.models import Intent
from app.intelligence.registry import REGISTRY, answerable_intents
from app.intelligence.service import IntelligenceService
from app.llm import LLMError, LLMParse, LLMUnavailable, create_llm
from app.llm.base import LLMInvalidResponse
from app.llm.gemini import GeminiClient
from app.llm.structured import RateLimiter
from app.schemas.intelligence import QueryRequest, SelectedEntity


# ── registry and Cypher safety ────────────────────────────────────────────────────────────────────




def _all_cypher() -> dict[str, str]:
    found = {n: v for n, v in vars(queries).items() if n.isupper() and isinstance(v, str)}
    found.update({f"{n}.{k}": t for n, v in vars(queries).items() if n.isupper() and isinstance(v, dict) for k, t in v.items()})  # e.g. SUBJECT per kind
    return found


def test_cypher_is_read_only():
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b|apoc\.(create|merge|refactor)|dbms\.", re.I)
    for name, text in _all_cypher().items():
        assert not forbidden.search(text), f"{name} contains a write or admin operation"




# ── exact identifiers (entity assistance only: they never choose an intent) ──────────────────────


# ── grounding (hallucination prevention) ──────────────────────────────────────────────────────────
EVIDENCE: list[dict[str, Any]] = [{"entity": "P-1", "relationship": "FITS", "target": "M-2", "data_class": "SOURCE_DERIVED"}]








# ── optional Gemini provider (Groq is covered in test_llm_providers.py) ─────────────────────────────────────────────────────────────────────────────────
def _gemini(handler) -> GeminiClient:
    settings = Settings(gemini_api_key="test-key-123", gemini_model="m-test")
    return GeminiClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))


def _reply(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


INTENTS = {"PART_TO_MACHINE": "machines a part fits"}














# ── service behaviour with a fake graph ───────────────────────────────────────────────────────────
class FakeRepo:
    """Just enough graph for routing tests. `data` can omit a relationship to prove it is never invented."""

    def __init__(self, resolve: dict[str, list[dict]] | None = None, **data: Any) -> None:
        self._resolve, self.data = resolve or {}, data

    def resolve(self, mention: str) -> list[dict]:
        return self._resolve.get(mention.lower(), [])

    def __getattr__(self, name: str):
        if name in self.data:
            value = self.data[name]
            return value if callable(value) else (lambda *a, **k: value)
        return lambda *a, **k: []

    def category(self, part_id): return {}


def row(kind: str, id: str, label: str, tier: int = 0, detail: str | None = None) -> dict:
    return {"kind": kind, "id": id, "label": label, "detail": detail, "data_status": "SOURCE_DERIVED", "tier": tier}


class NoParts:
    def search(self, **kw): return 0, []
    def summaries(self, ids): return []


class FakeLLM:
    name = "fake"

    def __init__(self, parse: LLMParse | Exception | None = None, reply: str | Exception = "") -> None:
        self.parse, self.reply, self.calls = parse, reply, 0

    def parse_question(self, question, intents):
        self.calls += 1
        if self.parse is None:
            return model_parse(question)  # a model that understands the question
        if isinstance(self.parse, Exception):
            raise self.parse
        return self.parse

    def resolve_entities(self, question, intents): return ()

    def generate_grounded_response(self, question, intent, evidence, draft):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def service(repo: FakeRepo, llm: Any = None) -> IntelligenceService:
    return IntelligenceService(repo, NoParts(), llm if llm is not None else FakeLLM())  # type: ignore[arg-type]


PART = row("PART", "PRT-1", "AB-1000-XY")
MACHINE = row("MACHINE", "MCH-1", "ZZ-1")


def ask(svc: IntelligenceService, question: str, **kw):
    return svc.query(QueryRequest(question=question, **kw))


FIT = [{"machine_id": "MCH-1", "model_code": "ZZ-1", "name": "Zed", "machine_type": "Loader", "family": "Z", "fitment_status": "CONFIRMED", "condition_note": None, "data_status": "SOURCE_DERIVED"}]


def test_every_question_goes_to_the_model_first_and_its_intent_is_what_runs():
    llm = FakeLLM(parse=LLMParse("PART_TO_MACHINE", ("AB-1000-XY",)))
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT)
    r = ask(service(repo, llm), "Which machines use AB-1000-XY?")
    assert (r.intent, r.understood_by, r.total) == ("PART_TO_MACHINE", "llm", 1) and llm.calls == 1
    assert r.evidence[0].relationship == "FITS" and r.provenance[0].data_class == "SOURCE_DERIVED"  # the answer is the graph's, not the model's




def test_model_entities_are_resolved_against_the_graph_not_trusted():
    repo = FakeRepo({"ab-1000-xy": [PART]}, suppliers=[])
    r = ask(service(repo, FakeLLM(parse=LLMParse("PART_TO_SUPPLIER", ("ZQ-0000-XX",)))), "who supplies that?")
    assert r.results == [] and r.clarification is not None  # an entity the graph does not hold is asked about, never invented


def test_no_model_means_a_clear_error_never_a_silent_keyword_router():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=FIT)
    for llm in (FakeLLM(parse=LLMUnavailable("rate limit")), FakeLLM(parse=LLMInvalidResponse("bad json"))):
        with pytest.raises(LLMError):
            ask(service(repo, llm), "Which machines use AB-1000-XY?")
    with pytest.raises(LLMUnavailable):
        ask(IntelligenceService(repo, NoParts(), None), "Which machines use AB-1000-XY?")  # type: ignore[arg-type]










def test_ambiguous_entity_returns_candidates_not_a_choice():
    repo = FakeRepo({"loader": [row("MACHINE", "A", "ZZ-1", 2), row("MACHINE", "B", "ZZ-2", 2)]})
    r = ask(service(repo), "which parts fit the loader")
    assert r.clarification and {c.label for c in r.clarification.candidates} == {"ZZ-1", "ZZ-2"} and r.results == []




def test_llm_unsupported_or_unknown_intent_is_rejected_without_a_query():
    for parse in (LLMParse("DROP_EVERYTHING", ("x",)), LLMParse("UNSUPPORTED")):
        r = ask(service(FakeRepo(), FakeLLM(parse)), "tell me something vague about stuff")
        assert r.intent == "UNSUPPORTED" and r.results == []




def test_model_summary_is_discarded_when_it_invents_facts():
    repo = FakeRepo({"ab-1000-xy": [PART]}, fitment=[{"machine_id": "MCH-1", "model_code": "ZZ-1", "name": "Zed", "machine_type": None, "family": None, "fitment_status": "CONFIRMED",
                                                      "condition_note": None, "data_status": "SOURCE_DERIVED"}])
    bad = ask(service(repo, FakeLLM(reply="AB-1000-XY is interchangeable with AB-2000-XY and has 40 in stock.")), "Which machines use AB-1000-XY?")
    good = ask(service(repo, FakeLLM(reply="AB-1000-XY is associated with ZZ-1 in the graph.")), "Which machines use AB-1000-XY?")
    assert bad.answer.source == "template" and "interchangeable" not in bad.answer.summary
    assert good.answer.source == "llm"




# ── data truth ────────────────────────────────────────────────────────────────────────────────────






def test_unknown_stock_is_not_zero():
    r = ask(service(FakeRepo({"ab-1000-xy": [PART]}, warehouses=[], dealers=[])), "stock of AB-1000-XY")
    assert r.results == [] and "unknown" in r.answer.summary and "0 " not in r.answer.summary.replace("not the same as zero", "")
    assert any("not connected" in w.lower() for w in r.warnings)




# ── hard-code audit ───────────────────────────────────────────────────────────────────────────────


# ── demo qualifier in worded answers (QA fix 5) ───────────────────────────────────────────────────


SUPPLIER_ROW = {"supplier_id": "S1", "name": "Acme Seals (demo)", "city": "X", "country_code": "NL", "status": None, "is_primary": True, "lead_time_days": 3,
                "supplier_part_number": None, "categories": [], "data_status": "SYNTHETIC_DEMO"}






def ev_row():
    from app.schemas.intelligence import Evidence
    return Evidence(entity="AB-1000-XY", entity_kind="PART", relationship="SUPPLIED_BY", target="Acme Seals (demo)", target_kind="SUPPLIER", data_class="SYNTHETIC_DEMO")






# ── entity context: an answer always says what it is about ───────────────────────────────────────
PART_SUBJECT = {"label": "AB-1000-XY", "name": "Bucket, general purpose", "data_status": "SOURCE_DERIVED", "source": "Catalogue", "category": "Attachments", "subcategory": "Bucket", "part_status": "VERIFIED"}
FIT2 = FIT + [{**FIT[0], "machine_id": "MCH-2", "model_code": "ZZ-2", "name": "Zed Two"}]










# ── audit regressions: search plurals, naming one of several candidates, alternatives routing ──────────








# ── a misspelled category is still understood; an empty machine+category result says so and points to the same-family models ──
CATS = [{"id": "CAT-HY", "label": "Hydraulics", "data_status": "SOURCE_DERIVED"}, {"id": "CAT-BR", "label": "Brakes", "data_status": "SOURCE_DERIVED"}]






# ── casual requests ───────────────────────────────────────────────────────────────────────────────────────────




