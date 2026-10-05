"""Parts Intelligence: a question can carry several constraints (what kind of part, which machine). The language model extracts them independently
(`need`, `entities.machine`); the backend chooses the approved query from the validated constraints and enforces each one:

    need + machine -> parts discovery: Part -[FITS]-> Machine, restricted to the need, confirmed fits only
    machine only   -> the machine's parts
    a named machine that does not resolve -> nothing is searched (never invented, never mapped to a near number, never dropped)

The model is scripted here (it returns exactly the structured reading the real model produces, including its worst labelling of the intent), so these
tests check the backend's half deterministically against the live graph, read-only."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_graph, get_llm
from app.core.config import get_settings
from app.llm import LLMParse
from app.main import app

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")

# the model's structured reading of each question: the intent as the model happened to label it, plus the independently extracted constraints
READINGS = {
    "hydralic for my bts machine": LLMParse("MACHINE_TO_PART", entities={"machine": "bts machine"}, need="hydraulic"),
    "hydraulic for BTS-500": LLMParse("PART_SEARCH", entities={"machine": "BTS-500"}, need="hydraulic"),
    "filter for my nv 3200": LLMParse("MACHINE_GRAPH", entities={"machine": "NV 3200"}, need="filter", requires_clarification=True,
                                      clarification_question="What do you want to know about the NV 3200?"),
    "bearing for NV-4500": LLMParse("MACHINE_TO_PART", entities={"machine": "NV-4500"}, need="bearing"),
    "battery for KFT-200": LLMParse("MACHINE_TO_PART", entities={"machine": "KFT-200"}, need="battery"),
    "hydraulic for NV-2100": LLMParse("PART_SEARCH", entities={"machine": "NV-2100"}, need="hydraulic"),
    "hydralic for nv200": LLMParse("MACHINE_TO_PART", entities={"machine": "nv200"}, need="hydraulic"),
    "NVM-1050-FL for NV-4500": LLMParse("PART_SEARCH", entities={"machine": "NV-4500", "part": "NVM-1050-FL"}, need="NVM-1050-FL"),
    "does NVM-1050-FL fit NV-4500": LLMParse("PART_TO_MACHINE", entities={"machine": "NV-4500", "part": "NVM-1050-FL"}),
    "brake parts for NV-2100": LLMParse("MACHINE_TO_PART", entities={"machine": "NV-2100", "category": "Brakes"}, need="brake"),
    "show me the filters": LLMParse("PART_SEARCH", need="filter"),
    "parts for NV-3200": LLMParse("MACHINE_TO_PART", entities={"machine": "NV-3200"}),
    "hydralic for my bts machine (older reading)": LLMParse("MACHINE_TO_PART", entities={"machine": "bts machine", "part": "hydralic"}),
}


class Scripted:
    name = "scripted"

    def parse_question(self, question, intents):
        return READINGS[question]

    def generate_grounded_response(self, *a, **k):
        from app.llm import LLMUnavailable

        raise LLMUnavailable("the deterministic answer is used")


@pytest.fixture()
def ask():
    app.dependency_overrides[get_llm] = lambda: Scripted()
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"user_id": "USR-EU-001"}).status_code == 200

    def _ask(question, selected=None):
        r = c.post("/api/v1/intelligence/query", json={"question": question, "selected": selected or []})
        assert r.status_code == 200, r.text
        return r.json()

    yield _ask
    app.dependency_overrides.pop(get_llm, None)


def fits(machine: str) -> dict[str, tuple]:
    """part_number -> (fitment status, category, name), straight from the graph: the oracle every result is checked against."""
    rows = get_graph().read("MATCH (p:Part)-[f:FITS]->(:Machine {model_code: $m}) RETURN p.part_number AS n, p.category AS c, p.name AS name, f.fitment_status AS s", m=machine)
    return {r["n"]: (r["s"], r["c"], r["name"]) for r in rows}


def results(d):
    return [r["title"] for r in d["results"]]


def assert_discovery(d, machine, need_words, *, category=None):
    """Every result fits the machine with CONFIRMED status, matches the need, and carries FITS evidence to that machine; no unrelated part leaks in."""
    oracle = fits(machine)
    for n in results(d):
        status, cat, name = oracle[n]  # KeyError = a part that does not fit this machine at all
        assert status == "CONFIRMED", (n, status)
        assert (category and cat == category) or any(w in f"{cat} {name}".lower() for w in need_words), f"{n} ({cat}, {name}) does not match {need_words}"
    evidenced = {e["entity"] for e in d["evidence"] if e["relationship"] == "FITS" and e["target"] == machine}
    assert evidenced == set(results(d)), (evidenced, results(d))  # every returned part has FITS evidence to the machine, and nothing else does


# 8  ambiguous "bts machine": ask which one; every choice is a real BTS machine; none is picked for the user
def test_hydraulic_for_a_bts_machine_asks_which_bts_machine(ask):
    d = ask("hydralic for my bts machine")
    assert d["scope"] == "NEEDS_CLARIFICATION" and d["results"] == []
    assert {c["label"] for c in d["clarification"]["candidates"]} == {"BTS-100", "BTS-250", "BTS-500", "BTS-750", "BTS-900"}
    assert d["intent"] == "PART_SEARCH"  # need + machine is parts discovery, never a machine-details question
    assert ("CATEGORY", "Hydraulics") in [(e["kind"], e["label"]) for e in d["entities"]]  # the need survived the clarification
    detail = {c["label"]: c["detail"] for c in d["clarification"]["candidates"]}
    assert "2 Hydraulics parts" in detail["BTS-250"] and "no Hydraulics part" in detail["BTS-500"]  # the picker says which have the part


# 1  the reported failure: after choosing the machine the hydraulic need must still decide the result
def test_choosing_a_bts_machine_keeps_the_hydraulic_constraint(ask):
    d = ask("hydralic for my bts machine", [{"kind": "MACHINE", "key": "BTS-750"}])
    assert results(d) == ["NVM-1090-HY"] and d["intent"] == "PART_SEARCH"  # NOT the machine's bearing and battery
    assert_discovery(d, "BTS-750", ["hydraul"], category="Hydraulics")
    d = ask("hydralic for my bts machine", [{"kind": "MACHINE", "key": "BTS-500"}])
    assert results(d) == [] and "no hydraulics part" in d["answer"]["summary"].lower() and "BTS-250" in d["answer"]["summary"]


# 2  explicit machine, category word
def test_hydraulic_for_bts_500_has_no_hydraulic_part_and_says_so(ask):
    d = ask("hydraulic for BTS-500")
    assert results(d) == [] and "BTS-500" in d["answer"]["summary"] and "contact" in d["answer"]["summary"].lower()
    assert set(fits("BTS-500")) == {"NVM-1080-ST"}  # the machine's only part is structural: it must not be offered for a hydraulic need


# 3  the second reported failure: the model labelled it a machine-details question and asked back; the need must still decide the query
def test_filter_for_nv_3200_is_part_discovery_not_a_machine_overview(ask):
    d = ask("filter for my nv 3200")
    assert d["intent"] == "PART_SEARCH" and ("MACHINE", "NV-3200") in [(e["kind"], e["label"]) for e in d["entities"]]
    assert d["clarification"] is None and results(d)
    assert_discovery(d, "NV-3200", ["filter"])
    assert len(results(d)) < len(fits("NV-3200"))  # not the machine's whole parts list


# 4/5/6  other machine + need pairs
@pytest.mark.parametrize("question,machine,words,category", [("bearing for NV-4500", "NV-4500", ["bearing"], None), ("battery for KFT-200", "KFT-200", ["battery"], None),
                                                               ("hydraulic for NV-2100", "NV-2100", ["hydraul"], "Hydraulics")])
def test_need_plus_machine_returns_only_confirmed_fits_that_match_the_need(ask, question, machine, words, category):
    d = ask(question)
    assert d["intent"] == "PART_SEARCH"
    assert_discovery(d, machine, words, category=category)
    if not results(d):  # a machine with no such part: a plain statement, nothing unrelated offered
        assert "no " in d["answer"]["summary"].lower()


# 7  a machine that does not exist is not invented, not mapped to a near model, and nothing is queried for it
def test_an_unknown_machine_is_not_invented_or_substituted(ask):
    d = ask("hydralic for nv200")
    assert d["scope"] == "NEEDS_CLARIFICATION" and d["results"] == [] and d["clarification"]["candidates"] == []
    assert "nv200" in d["clarification"]["question"] and d["clarification"]["code"] == "MACHINE_NOT_FOUND"
    assert not any(e["kind"] == "MACHINE" for e in d["entities"])  # NV-2100 (the nearest string) was not substituted
    assert "NV-2100" not in str(d["answer"]) and "NV-200" not in {e["label"] for e in d["entities"]}


# 9  exact part number + machine: that part, only if it fits
def test_exact_part_number_plus_machine(ask):
    d = ask("NVM-1050-FL for NV-4500")
    assert results(d) == ["NVM-1050-FL"] and fits("NV-4500")["NVM-1050-FL"][0] == "CONFIRMED"
    assert_discovery(d, "NV-4500", ["filter"])
    d = ask("does NVM-1050-FL fit NV-4500")  # the yes/no fitment intent is untouched
    assert d["intent"] == "PART_TO_MACHINE" and results(d) == ["NV-4500"]


# 10 category + machine
def test_category_plus_machine(ask):
    d = ask("brake parts for NV-2100")
    assert_discovery(d, "NV-2100", ["brake"], category="Brakes")


# no regression: a machine alone still lists its parts; a need alone still searches the catalogue
def test_machine_alone_and_need_alone_keep_their_queries(ask):
    d = ask("parts for NV-3200")
    assert d["intent"] == "MACHINE_TO_PART" and set(results(d)) <= set(fits("NV-3200")) and len(results(d)) >= 5
    d = ask("show me the filters")
    assert d["intent"] == "PART_SEARCH" and results(d) and all("filter" in f"{x['subtitle']} {x['facts']}".lower() for x in d["results"])


# an older model reading that put the need in `part` is still honoured (the constraint is never dropped)
def test_need_in_the_part_field_is_still_a_constraint(ask):
    d = ask("hydralic for my bts machine (older reading)", [{"kind": "MACHINE", "key": "BTS-750"}])
    assert results(d) == ["NVM-1090-HY"]
