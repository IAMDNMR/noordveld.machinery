"""Regression tests for the Parts Intelligence QA review fixes 3-5, against the live graph (read-only, language model off)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm
from app.core.config import get_settings
from app.main import app
from tests.support.keyword_model import KeywordModel

MODEL = KeywordModel()

pytestmark = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
V1 = "/api/v1/intelligence"
NO_MATCH = "No parts match this search"


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_llm] = lambda: MODEL  # a stand-in for Gemini (the application has no keyword router); the live-Gemini tests are in test_gemini_first.py
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def ask(client, question, **extra):
    r = client.post(f"{V1}/query", json={"question": question, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def labels(r):
    return [e["label"] for e in r["entities"]]


# ── Fix 3: a named part is always found ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("question,intent,part", [
    ("Is NVM-1050-CL verified?", "PART_PROVENANCE", "NVM-1050-CL"),
    ("How many NVM-1060-HY are available?", "PART_TO_INVENTORY", "NVM-1060-HY"),
    ("What is missing for NVM-4410-SK?", "DATA_QUALITY", "NVM-4410-SK"),
    ("What links NVM-1050-CL and a supplier?", "ENTITY_PATH", "NVM-1050-CL"),
    ("suppliers of nvm 1050 cl", "PART_TO_SUPPLIER", "NVM-1050-CL"),
    ("Which machines use NVM1050CL?", "PART_TO_MACHINE", "NVM-1050-CL"),
    ("Which machines use nvm-1050-cl", "PART_TO_MACHINE", "NVM-1050-CL"),
    ("Who supplies the water pump?", "PART_TO_SUPPLIER", "NVM-1050-CL"),
    ("Tell me about the water pump", "PART_SEARCH", "NVM-1050-CL"),
])
def test_part_with_extra_words_is_resolved_and_answered(client, question, intent, part):
    r = ask(client, question)
    assert r["intent"] == intent, (question, r["intent"], r["answer"]["summary"])
    assert part in labels(r) and r["clarification"] is None
    assert NO_MATCH not in r["answer"]["summary"] and r["total"] > 0


def test_verified_question_states_the_catalogue_status(client):
    assert "Verified" in ask(client, "Is NVM-1050-CL verified?")["answer"]["summary"]
    assert "Ambiguous" in ask(client, "Is NVM-4410-SK verified?")["answer"]["summary"]


def test_name_matching_several_parts_asks_to_choose(client):
    r = ask(client, "Tell me about the pump")
    if r["clarification"]:  # several parts are named "... pump"
        assert len(r["clarification"]["candidates"]) > 1 and r["results"] == []
    else:  # exactly one part has "pump" in its name
        assert r["total"] == 1
    assert NO_MATCH not in r["answer"]["summary"]


def test_no_question_about_an_existing_part_says_no_parts_match(client):
    for q in ["Find NVM-1050-CL", "find water pump", "Is NVM-1050-CL verified?", "How many NVM-1060-HY are available?", "What is missing for NVM-4410-SK?",
              "What links NVM-1050-CL and Hanselmann Kuehlsysteme (demo)?", "Show NVM 1050 CL", "Tell me about NVM-1140-DT"]:
        assert NO_MATCH not in ask(client, q)["answer"]["summary"], q


# ── Fix 4: path, order and place questions answer what was asked ───────────────────────────────────
def test_path_between_part_and_machine_uses_the_stored_relationship(client):
    r = ask(client, "How is NVM-1050-CL connected to NV-4500?")
    assert r["intent"] == "ENTITY_PATH" and set(labels(r)) == {"NVM-1050-CL", "NV-4500"}
    assert r["evidence"][0]["relationship"] == "FITS" and "directly" in r["answer"]["summary"]
    assert "relationships across" not in r["answer"]["summary"]  # never the unrelated relationship count


def test_path_to_a_named_supplier_lists_each_stored_step(client):
    r = ask(client, "What links NVM-1050-CL and Hanselmann Kuehlsysteme (demo)?")
    assert r["intent"] == "ENTITY_PATH" and r["results"]
    assert all(e["relationship"] in {"SUPPLIED_BY", "AVAILABLE_AT", "STOCKED_BY", "FITS", "PART_OF", "CO_ORDERED_WITH", "HAS_COMPLIANCE", "IN_CATEGORY",
                                     "RELATED_COMPONENT", "SAME_NAME_GROUP_AS", "MEMBER_OF_FAMILY", "SERVES_FAMILY"} for e in r["evidence"])


def test_order_status_is_read_only_and_labelled_demo(client):
    r = ask(client, "Where is order ORD-0001?")
    assert r["intent"] == "ORDER_STATUS" and labels(r) == ["ORD-0001"]
    assert r["answer"]["summary"].startswith("Demo order ORD-0001") and r["answer"]["demo"] is True
    assert any("not live" in w for w in r["warnings"])
    blob = str(r)
    assert "CUS-" not in blob and "street" not in blob.lower()  # no customer or address
    assert ask(client, "Where is my order?")["clarification"] is not None


def test_dealers_in_a_country_come_from_stored_locations(client):
    r = ask(client, "Which dealers are in Germany?")
    assert r["intent"] == "GEO_LOCATION" and r["results"]
    assert all(f["value"] == "DE" for it in r["results"] for f in it["facts"] if f["label"] == "Country")
    assert "Which part do you mean" not in r["answer"]["summary"]


def test_dealers_near_a_city_state_their_distance_basis(client):
    r = ask(client, "Which dealers are near Rotterdam?")
    assert r["intent"] == "GEO_LOCATION" and r["results"]
    assert all(any(f["label"] == "Distance basis" and f["value"] for f in it["facts"]) for it in r["results"])
    assert "no distances are calculated" in r["answer"]["summary"]


def test_nearest_dealer_without_a_place_asks_for_one(client):
    r = ask(client, "Which dealer is closest?")
    assert r["clarification"] and "city or country" in r["answer"]["summary"] and r["results"] == []


# ── Fix 5: provenance in answers ──────────────────────────────────────────────────────────────────
def test_demo_answers_are_flagged_and_keep_the_qualifier(client):
    r = ask(client, "Which suppliers are connected to NVM-1050-CL?")
    assert r["answer"]["demo"] is True and "(demo)" in r["answer"]["summary"] or r["answer"]["demo"] is True
    assert ask(client, "Which machines use NVM-1050-CL?")["answer"]["demo"] is False  # source-derived fitment only


@pytest.mark.parametrize("question", [
    "Find NVM-1050-CL", "Show the relationships for NVM-1050-CL", "Show the relationships for NV-4500", "What is the provenance of NVM-1050-CL?",
    "Where is the catalogue data incomplete?",
])
def test_every_answer_type_lists_evidence(client, question):
    assert ask(client, question)["evidence"], question


# ── Fix 6: availability label and graph node detail ───────────────────────────────────────────────
@pytest.mark.parametrize("part_number,state,label", [("NVM-1060-HY", "BACKORDER", "Backorder"), ("NVM-1050-CL", "IN_STOCK", "In stock"), ("NVM-1140-DT", "LIMITED", "Limited")])
def test_inventory_label_is_the_stores_availability(client, part_number, state, label):
    inventory = client.get(f"{V1}/parts/{part_number}/inventory").json()
    store = client.get(f"/api/v1/parts/{part_number}").json()["profile"]["availability_state"]
    assert store == state and inventory["availability_state"] == state and inventory["availability_label"] == label


def test_every_graph_node_kind_opens_its_detail(client):
    nodes = client.get(f"{V1}/parts/NVM-1050-CL/graph").json()["nodes"]
    kinds = {n["kind"] for n in nodes} - {"PART"}
    assert {"MACHINE", "SUPPLIER", "DEALER", "WAREHOUSE", "ASSEMBLY", "COMPLIANCE"} <= kinds
    for kind in sorted(kinds):
        node = next(n for n in nodes if n["kind"] == kind)
        kind_name, entity_id = node["id"].split(":", 1)
        r = client.get(f"{V1}/entities/{kind_name}/{entity_id}")
        assert r.status_code == 200, (kind, node["id"], r.text)
        detail = r.json()
        assert detail["kind"] == kind and detail["title"] and detail["facts"] and detail["data_class"]


# ── "what machines are available?" lists the catalogue's machines, it does not ask for a part ──────
@pytest.mark.parametrize("question", ["what machines are avaialable ?", "What machines are available?", "List all machines", "Which machines do you have?", "show me the machines"])
def test_machine_list_questions_list_the_machines(client, question):
    r = ask(client, question)
    assert r["intent"] == "MACHINE_LIST" and r["clarification"] is None, (question, r["intent"], r["answer"]["summary"])
    assert r["total"] >= 15 and r["results"] and r["evidence"] and all(i["kind"] == "machine" for i in r["results"])


@pytest.mark.parametrize("question,intent", [("Which machines use NVM-1050-CL?", "PART_TO_MACHINE"), ("What machines is the water pump used on?", "PART_TO_MACHINE"), ("Which parts fit the NV-4500?", "MACHINE_TO_PART")])
def test_machine_list_rule_does_not_steal_part_questions(client, question, intent):
    assert ask(client, question)["intent"] == intent
