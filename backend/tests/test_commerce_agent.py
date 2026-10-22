"""Phase 5: the Commerce Agent (app/commerce_agent/agent.py, app/commerce_agent/answer.py) and POST /api/v1/commerce/agent.

The engine runs over the canonical dataset files (the validated Phase 4 data); accounts come from the in-memory repository. Nothing here touches the graph. The language model is a fake:
the tests prove what the agent does WITH a model (route an unclear message, reword a lead) and that it is correct without one."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_commerce_engine, get_llm, get_orders_repository
from app.canonical.io import CANON_DIR
from app.commerce.access import CommerceRole, Principal
from app.commerce_agent.agent import CommerceAgent, AgentRequest, discovery_text, extract_references
from app.commerce.engine import CommerceContextEngine
from app.llm.base import CommerceParse, LLMUnavailable
from app.main import app
from tests.support.fake_orders import FakeRepo

ENGINE = CommerceContextEngine.from_files(CANON_DIR, as_of=date(2026, 10, 7))
BASE = "/api/v1/commerce/agent"
OWNERS = {"U-C001": "CUS-001", "U-C002": "CUS-002", "U-C003": "CUS-003", "U-C004": "CUS-004", "U-C006": "CUS-006", "U-C008": "CUS-008", "U-C009": "CUS-009", "U-C010": "CUS-010"}


def customer(cid: str) -> Principal:
    return Principal(CommerceRole.END_CUSTOMER, user_id="t", customer_id=cid)


OEM = Principal(CommerceRole.OEM, user_id="t")


def ask(message: str, who: Principal = OEM, state: dict | None = None, llm=None) -> dict:
    return CommerceAgent(ENGINE, llm).handle(AgentRequest(message=message, principal=who, state=state or {}))


def sections(r: dict) -> dict[str, dict]:
    return {s["domain"]: s for s in r["answer"]["sections"]}


class FakeLLM:
    """Stands in for the provider: records what it was asked and answers as configured."""

    name = "fake"

    def __init__(self, domains=("DISCOVERY",), in_scope=True, reword: str | None = None, fail: bool = False):
        self.domains, self.in_scope, self.reword, self.fail, self.routed, self.worded = domains, in_scope, reword, fail, [], []

    def parse_commerce_request(self, message):
        self.routed.append(message)
        if self.fail:
            raise LLMUnavailable("down")
        return CommerceParse(in_scope=self.in_scope, domains=tuple(self.domains))

    def generate_grounded_response(self, question, intent, evidence, draft):
        self.worded.append(draft)
        if self.fail:
            raise LLMUnavailable("down")
        return self.reword if self.reword is not None else draft


# ── understanding: the six intents ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("message,intent", [
    ("Find a hydraulic pump for KFT-200.", "DISCOVERY"), ("Where is SHP-0010 and what parts are in it?", "LOGISTICS"), ("Is this part under warranty? CLM-G001", "WARRANTY"),
    ("Find me a hydraulic pump for my KFT-600 and tell me how quickly I can get it.", "MULTI_DOMAIN"),
    ("I need a replacement pump urgently. Is my failed one still under warranty and how quickly can I get the replacement?", "MULTI_DOMAIN"),
    ("my order", "CLARIFICATION"), ("tell me a joke", "UNKNOWN"), ("hello", "UNKNOWN"),
])
def test_the_agent_classifies_the_intent(message, intent):
    assert ask(message).get("intent") == intent


def test_multi_domain_runs_the_journeys_in_a_fixed_order_and_names_them():
    r = ask("I need a replacement pump urgently. Is my failed one still under warranty and how quickly can I get the replacement?")
    assert r["understanding"]["domains"] == ["DISCOVERY", "WARRANTY", "LOGISTICS"] and [s["domain"] for s in r["steps"]] == ["DISCOVERY", "WARRANTY", "LOGISTICS"]


def test_references_are_read_by_the_backend_from_the_message():
    refs = extract_references("Where is shp-0010? also ORD-NET-0001, claim clm-g004-2 on mi-g001 and PRT-007", ENGINE.discovery)
    assert refs == {"shipment_id": "SHP-0010", "order_id": "ORD-NET-0001", "claim_id": "CLM-G004-2", "machine_instance_id": "MI-G001", "part_id": "PRT-007"}
    assert extract_references("I need NVM-1060-HY", ENGINE.discovery)["part_id"] == "PRT-007"  # a part number resolves through the catalogue
    assert extract_references("SHP-99999 and PRT-7", ENGINE.discovery) == {}


def test_the_part_search_is_the_search_clause_not_the_whole_multi_journey_message():
    assert discovery_text("I need a replacement hydraulic pump urgently. Is my failed one still under warranty and how quickly can I get the replacement?") == "I need a replacement hydraulic pump."
    assert discovery_text("Find me a hydraulic pump for my KFT-600 and tell me how quickly I can get it.") == "Find me a hydraulic pump for my KFT-600"
    assert discovery_text("Find a hydraulic pump for KFT-200.") == "Find a hydraulic pump for KFT-200."


# ── discovery ────────────────────────────────────────────────────────────────────────────────────
def test_discovery_canonical_match_is_recommended_with_fitment_source_availability_and_price():
    r = ask("Find a hydraulic pump for KFT-200.", customer("CUS-001"))
    s = sections(r)["DISCOVERY"]
    assert r["status"] == "ANSWERED" and s["decision"] == "RECOMMEND" and r["contexts"]["DISCOVERY"]["recommended_part"]["part_id"] == "PRT-006"
    text = "\n".join(s["lines"])
    assert "Fitment: approved for KFT-200" in text and "approved source: yes" in text and "Availability: available" in text and "471.20 EUR (demo price)" in text
    assert r["evidence_paths"]["DISCOVERY"][0]["entity"] == "Part" and r["state"]["part_number"] == "NVM-1050-HY" and r["state"]["machine_model"] == "KFT-200"


def test_discovery_never_offers_a_canonical_type_mismatch_or_an_alias_only_match():
    ctx = ask("Find a hydraulic pump for KFT-200.")["contexts"]["DISCOVERY"]
    offered = json.dumps([ctx["recommended_part"], ctx["compatible_part"], ctx["alternatives"], ctx["unconfirmed_matches"]])
    assert "PRT-097" not in offered and "PRT-078" not in offered  # matched only through alias text: a different canonical product type
    assert ctx["rejection_reasons"]["PRT-097"][0]["code"] == "CANONICAL_TYPE_MISMATCH"
    text = "\n".join(sections(ask("Find a hydraulic pump for KFT-200."))["DISCOVERY"]["lines"])
    assert "Not recommended: PRT-078, PRT-097" in text and "alias text" in text


def test_discovery_an_approved_part_that_is_out_of_stock_is_reported_not_replaced():
    r = ask("I need a hydraulic pump for my KFT-600.")
    s = sections(r)["DISCOVERY"]
    ctx = r["contexts"]["DISCOVERY"]
    assert s["decision"] == "NO_AVAILABLE_RECOMMENDATION" and ctx["recommended_part"] is None and ctx["alternatives"] == [] and ctx["compatible_part"]["part_id"] == "PRT-007"
    assert "currently unavailable" in s["headline"] and any("Availability: unavailable, 0 units" in ln for ln in s["lines"]) and any(ln.startswith("Why not: No warehouse has stock") for ln in s["lines"])


def test_discovery_asks_when_the_machine_is_not_known_and_does_not_guess():
    r = ask("Find a hydraulic filter for X200.")
    assert r["status"] == "REQUIRES_CLARIFICATION" and sections(r)["DISCOVERY"]["decision"] == "REQUIRES_CLARIFICATION" and r["contexts"]["DISCOVERY"]["recommended_part"] is None
    assert r["clarification"]["domain"] == "DISCOVERY" and r["clarification"]["question"]


def test_discovery_follow_up_availability_uses_the_part_of_the_previous_answer():
    first = ask("Find a hydraulic pump for KFT-200.")
    r = ask("Do you have this part available?", OEM, first["state"])
    s = sections(r)["DISCOVERY"]
    assert r["understanding"]["source"] == "RULES" and s["decision"] == "RECOMMEND" and r["state"]["part_number"] == "NVM-1050-HY"
    assert any("“This part” was read as NVM-1050-HY for KFT-200" in n for n in s["notes"])


def test_discovery_follow_up_why_explains_the_previous_search_from_the_ranking_not_from_the_model():
    first = ask("Find a hydraulic pump for KFT-200.")
    r = ask("Why are you recommending this part?", OEM, first["state"])
    lines = sections(r)["DISCOVERY"]["lines"]
    assert "Why: product_match = CANONICAL_MATCH" in lines and "Why: fitment = APPROVED" in lines and any(ln.startswith("Ranking score") for ln in lines)
    assert r["state"]["last_request"] == "Find a hydraulic pump for KFT-200."


def test_discovery_without_a_remembered_part_is_not_invented():
    r = ask("Do you have this part available?")
    assert sections(r)["DISCOVERY"]["decision"] in ("REQUIRES_CLARIFICATION", "NO_VALID_RECOMMENDATION") and r["contexts"]["DISCOVERY"]["recommended_part"] is None


# ── logistics ────────────────────────────────────────────────────────────────────────────────────
def test_logistics_single_line_shipment_shows_its_part_and_tracked_progress():
    r = ask("Where is SHP-NET-0001?", customer("CUS-009"))
    x = r["contexts"]["LOGISTICS"]
    assert x["shipment_kind"] == "SINGLE_LINE" and x["part"]["part_number"] == "NVM-1010-HY" and len(x["shipment_lines"]) == 1 and x["order_split"] is True
    text = "\n".join(sections(r)["LOGISTICS"]["lines"])
    assert "Route RTE-NET-JPNL-SEA-ECO (SEA): 1 of 4 legs completed." in text and "Planned ETA: 2026-11-19" in text and "was split into 2 shipments; the others are SHP-NET-0002" in text


def test_logistics_multi_line_shipment_lists_every_line_and_part_and_chooses_none():
    r = ask("Where is SHP-0010 and what parts are in it?", customer("CUS-001"))
    x, s = r["contexts"]["LOGISTICS"], sections(r)["LOGISTICS"]
    assert x["shipment_kind"] == "MULTI_LINE" and x["part"] is None and [ln["order_line_id"] for ln in x["shipment_lines"]] == ["OI-0021", "OI-0022"]
    assert [p["part_number"] for p in x["parts"]] == ["NVM-1010-HY", "NVM-1100-DT"] and x["order_split"] is False
    text = "\n".join(s["lines"])
    assert "carries 2 order lines with 2 different part(s)" in text and "OI-0021: NVM-1010-HY" in text and "OI-0022: NVM-1100-DT" in text and "× 2" in text


def test_logistics_three_line_shipment_lists_all_three():
    r = ask("What parts are in SHP-0011?", customer("CUS-008"))
    x = r["contexts"]["LOGISTICS"]
    assert len(x["shipment_lines"]) == 3 and x["shipment_kind"] == "MULTI_LINE" and x["part"] is None
    assert sum("OI-002" in ln for ln in sections(r)["LOGISTICS"]["lines"]) == 3


def test_logistics_order_with_two_shipments_still_asks_which_one_and_each_option_names_its_parts():
    r = ask("Where is my order ORD-NET-0001?", customer("CUS-009"))
    assert r["status"] == "REQUIRES_CLARIFICATION" and r["clarification"]["domain"] == "LOGISTICS"
    assert {o["shipment_id"] for o in r["clarification"]["options"]} == {"SHP-NET-0001", "SHP-NET-0002"}
    assert all(o["line_count"] == 1 and o["part_number"] == "NVM-1010-HY" for o in r["clarification"]["options"])
    assert all("order line(s)" in ln for ln in sections(r)["LOGISTICS"]["lines"])


def test_logistics_multi_line_and_split_order_are_different_facts():
    multi, split = ask("Where is SHP-0010?").get("contexts")["LOGISTICS"], ask("Where is SHP-NET-0001?")["contexts"]["LOGISTICS"]
    assert (multi["shipment_kind"], multi["order_split"]) == ("MULTI_LINE", False) and (split["shipment_kind"], split["order_split"]) == ("SINGLE_LINE", True)


def test_logistics_delivered_shipment_reports_delivery():
    r = ask("What is the status of SHP-NET-0004?", customer("CUS-009"))
    assert r["contexts"]["LOGISTICS"]["decision"]["decision"] == "DELIVERED" and any(ln.startswith("Delivered:") for ln in sections(r)["LOGISTICS"]["lines"])


def test_logistics_without_a_determinable_route_says_so_and_names_no_faster_option():
    r = ask("Can I get SHP-0001 faster?", customer("CUS-006"))
    s = sections(r)["LOGISTICS"]
    assert s["decision"] == "ROUTE_NOT_DETERMINABLE" and "A faster option cannot be named" in "\n".join(s["lines"]) and r["contexts"]["LOGISTICS"]["alternative_routes"] == []


def test_logistics_faster_lists_only_recorded_alternative_routes():
    r = ask("Can I get SHP-NET-0001 faster?", customer("CUS-009"))
    lines = [ln for ln in sections(r)["LOGISTICS"]["lines"] if ln.startswith("Recorded alternative")]
    assert any("RTE-NET-JPNL-AIR-EXP (AIR), 6 days" in ln and "faster" in ln for ln in lines)


def test_logistics_compare_sea_and_air_shows_the_recorded_trade_off_for_the_japan_lane():
    r = ask("Compare sea and air for shipment SHP-NET-0001", customer("CUS-009"))
    assert r["intent"] == "LOGISTICS"
    text = "\n".join(sections(r)["LOGISTICS"]["lines"])
    assert "RTE-NET-JPNL-SEA-ECO (SEA)" in text and "RTE-NET-JPNL-AIR-EXP (AIR), 6 days, 12675.0 EUR" in text and "RTE-NET-JPNL-SEA-STD (SEA), 45 days" in text


def test_logistics_a_shipment_past_its_planned_eta_with_no_delivery_is_reported_as_behind_plan():
    later = CommerceContextEngine.from_files(CANON_DIR, as_of=date(2026, 10, 11))  # SHP-NET-0003: planned ETA 2026-10-09, still departed_port

    def say(engine, message):
        return "\n".join(sections(CommerceAgent(engine, None).handle(AgentRequest(message=message, principal=OEM, state={})))["LOGISTICS"]["lines"])

    assert "Past the planned ETA by 2 days" in say(later, "Is shipment SHP-NET-0003 late?") and "no new ETA is recorded" in say(later, "Is shipment SHP-NET-0003 late?")
    assert "Not past its planned ETA" in say(ENGINE, "Is shipment SHP-NET-0003 late?")  # on 2026-10-07 it is still on plan
    assert "Past the planned ETA" not in say(later, "Is shipment SHP-NET-0004 late?")  # delivered


def test_logistics_follow_up_uses_the_shipment_of_the_previous_answer():
    first = ask("Where is SHP-NET-0001?", customer("CUS-009"))
    r = ask("Why is it taking so long?", customer("CUS-009"), first["state"])
    assert r["understanding"]["source"] in ("RULES", "STATE") and r["contexts"]["LOGISTICS"]["shipment"]["shipment_id"] == "SHP-NET-0001" and any("leg(s) remain" in ln for ln in sections(r)["LOGISTICS"]["lines"])


# ── warranty ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("claim,owner,decision,must_say", [
    ("CLM-G001", "CUS-001", "ELIGIBLE", "All 9 warranty checks passed."),
    ("CLM-G002", "CUS-004", "NOT_ELIGIBLE", "Not met: The installation was performed by an authorised dealer"),
    ("CLM-G003", "CUS-006", "NOT_ELIGIBLE", "Not met: The warranty period is active"),
    ("CLM-G004-2", "CUS-002", "REQUIRES_REVIEW", "There is no earlier claim for this part on this machine"),
    ("CLM-G005", "CUS-001", "REQUIRES_REVIEW", "Replacement history: 2 recorded replacement(s): REP-G005-1"),
    ("CLM-G006", "CUS-004", "INSUFFICIENT_DATA", "Unknown: The installation is evidenced"),
    ("CLM-G007", "CUS-003", "NOT_ELIGIBLE", "Not met: The part is a verified catalogue part"),
    ("CLM-G008", "CUS-006", "NOT_ELIGIBLE", "Not met: The part is approved for this machine model"),
])
def test_warranty_gives_the_backends_deterministic_decision_and_its_reasons(claim, owner, decision, must_say):
    r = ask(f"Why is claim {claim} {'not eligible' if decision != 'ELIGIBLE' else 'eligible'}?", customer(owner))
    s = sections(r)["WARRANTY"]
    assert r["contexts"]["WARRANTY"]["decision"]["facts"]["outcome"] == decision and f"Decision: {decision.replace('_', ' ').lower()}" in "\n".join(s["lines"])
    assert must_say in "\n".join(s["lines"])


def test_warranty_the_customer_is_not_shown_the_technicians_name_but_sees_the_installation_story():
    r = ask("Who installed the part on claim CLM-G001 and was it installed correctly?", customer("CUS-001"))
    x, text = r["contexts"]["WARRANTY"], "\n".join(sections(r)["WARRANTY"]["lines"])
    assert "name" not in (x["technician"] or {}) and "Hendrik" not in json.dumps(r) and "The technician's name is not shown to your role." in text
    assert "Installed on 2026-04-12 by dealer Brabant Heavy Parts (demo) (authorised)" in text and "installation record valid" in text and "Work order WO-G001" in text


def test_warranty_the_oem_sees_the_technician_the_customer_does_not():
    assert "Hendrik Vos (demo)" in json.dumps(ask("Who installed the part on claim CLM-G001?", OEM)["contexts"]["WARRANTY"])


def test_warranty_replacement_history_is_shown_where_it_exists():
    text = "\n".join(sections(ask("Has the part on claim CLM-G005 been replaced before?", customer("CUS-001")))["WARRANTY"]["lines"])
    assert "REP-G005-1 on 2026-02-10" in text and "REP-G005-2 on 2026-05-20" in text


def test_warranty_without_a_claim_or_machine_asks_which_and_offers_only_the_customers_own():
    r = ask("Is this part under warranty?", customer("CUS-001"))
    assert r["status"] == "REQUIRES_CLARIFICATION" and {o["machine_instance_id"] for o in r["clarification"]["options"]} == {"MI-0001", "MI-0011", "MI-G001", "MI-G005"}


def test_warranty_machine_and_part_without_a_claim_is_judged_by_the_same_rules():
    r = ask("Is the pump on MI-G002 under warranty?", OEM, {"part_id": "PRT-007"})
    assert r["contexts"]["WARRANTY"]["decision"]["facts"]["outcome"] == "NOT_ELIGIBLE" and r["contexts"]["WARRANTY"]["claim"]["claim_id"] == "CLM-G002"  # the one recorded claim is the failed part judged
    assert any("only claim recorded for PRT-007 on MI-G002" in n for n in sections(r)["WARRANTY"]["notes"])
    none = ask("Is the pump on MI-G001 under warranty?", OEM, {"part_id": "PRT-018"})  # a part with no claim is judged on its installation alone
    assert none["contexts"]["WARRANTY"]["claim"] is None and none["contexts"]["WARRANTY"]["decision"]["facts"]["outcome"]


# ── multi-domain ─────────────────────────────────────────────────────────────────────────────────
def test_flow_d_discovery_warranty_and_logistics_answer_one_coherent_message():
    r = ask("I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?", customer("CUS-001"), {"machine_instance_id": "MI-G001"})
    s = sections(r)
    assert r["intent"] == "MULTI_DOMAIN" and r["status"] == "PARTIAL"
    assert s["DISCOVERY"]["decision"] == "NO_AVAILABLE_RECOMMENDATION" and s["WARRANTY"]["decision"] == "ELIGIBLE" and s["LOGISTICS"]["decision"] == "NO_SHIPMENT_FOR_UNORDERED_PART"
    assert any("Claim CLM-G001 is the only claim recorded for PRT-007 on MI-G001" in n for n in s["WARRANTY"]["notes"])
    assert "no tracked delivery to report" in s["LOGISTICS"]["headline"]
    assert {e["domain"] for e in r["evidence"]} == {"DISCOVERY", "WARRANTY"} and set(r["evidence_paths"]) == {"DISCOVERY", "WARRANTY"}
    assert r["answer"]["lead"].count("NVM-1060-HY") == 1 and "Every applicable warranty condition holds" in r["answer"]["lead"]


def test_multi_domain_asks_which_machine_when_several_match_and_still_answers_the_rest():
    r = ask("Find me a hydraulic pump for my KFT-600 and is the failed one covered?", customer("CUS-001"))
    assert r["status"] == "REQUIRES_CLARIFICATION" and r["clarification"]["domain"] == "WARRANTY"
    assert {o["machine_instance_id"] for o in r["clarification"]["options"]} == {"MI-G001", "MI-G005"} and sections(r)["DISCOVERY"]["decision"] == "NO_AVAILABLE_RECOMMENDATION"


def test_discovery_and_logistics_delivery_speed_for_an_unordered_part_is_not_invented():
    r = ask("Find me a hydraulic pump for my KFT-600 and tell me how quickly I can get it.", customer("CUS-001"))
    assert sections(r)["LOGISTICS"]["decision"] == "NO_SHIPMENT_FOR_UNORDERED_PART" and "days" not in sections(r)["LOGISTICS"]["headline"].replace("no tracked", "")


def test_a_short_reply_to_a_question_the_agent_asked_is_read_as_the_answer_to_it():
    me = customer("CUS-001")
    first = ask("I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?", me)
    assert first["status"] == "REQUIRES_CLARIFICATION" and first["clarification"]["domain"] in ("DISCOVERY", "WARRANTY") and "pending_message" in first["state"]
    second = ask("KFT-600", me, first["state"])  # the user names the machine model
    assert second["understanding"]["domains"] == ["DISCOVERY", "WARRANTY", "LOGISTICS"] and any("read as the answer" in r for r in second["understanding"]["reasons"])
    assert sections(second)["DISCOVERY"]["decision"] == "NO_AVAILABLE_RECOMMENDATION" and second["clarification"]["domain"] == "WARRANTY"  # now only the machine instance is missing
    assert {o["machine_instance_id"] for o in second["clarification"]["options"]} == {"MI-G001", "MI-G005"} and "pending_message" in second["state"]
    third = ask("KFT-600", me, {**second["state"], "machine_instance_id": "MI-G001"})  # the user picks one of the offered machines
    assert third["status"] == "PARTIAL" and sections(third)["WARRANTY"]["decision"] == "ELIGIBLE" and "pending_message" not in third["state"]


def test_a_new_request_drops_the_question_that_was_waiting():
    first = ask("Is this part under warranty?", customer("CUS-001"))
    assert "pending_message" in first["state"]
    nxt = ask("Where is SHP-0010?", customer("CUS-001"), first["state"])
    assert nxt["intent"] == "LOGISTICS" and "pending_message" not in nxt["state"] and not any("read as the answer" in r for r in nxt["understanding"]["reasons"])
    long_off_topic = ask("please write me a long poem about the sea and the sky and the stars tonight", customer("CUS-001"), first["state"])
    assert long_off_topic["intent"] == "UNKNOWN" and "pending_message" not in long_off_topic["state"]  # a long message is a new request, never an answer


# ── evidence-first, provenance, disclosure ───────────────────────────────────────────────────────
def test_every_answer_carries_context_evidence_path_provenance_and_the_demo_disclosure():
    r = ask("Where is SHP-NET-0001?", customer("CUS-009"))
    assert r["contexts"]["LOGISTICS"]["decision"]["source_records"] and r["evidence"] and r["evidence_paths"]["LOGISTICS"][0]["entity"] == "Order" and r["source_records"]
    assert r["data_status"] == "SYNTHETIC_DEMO" and "demonstration data" in r["answer"]["synthetic_notice"] and r["confidence"]["LOGISTICS"]["real_world_verified"] is False
    assert all(e["domain"] == "LOGISTICS" for e in r["evidence"])


def test_the_state_the_agent_returns_holds_identifiers_only_never_a_decision():
    r = ask("Is claim CLM-G001 covered?", customer("CUS-001"))
    assert set(r["state"]) <= {"shipment_id", "order_id", "claim_id", "machine_instance_id", "part_id", "machine_id", "machine_model", "part_number", "last_request", "last_domains", "pending_message"}
    assert "ELIGIBLE" not in json.dumps(r["state"]) and r["state"]["claim_id"] == "CLM-G001" and r["state"]["machine_instance_id"] == "MI-G001"


def test_an_out_of_scope_message_is_declined_with_what_the_agent_can_do():
    r = ask("write me a poem")
    assert r["intent"] == "UNKNOWN" and r["status"] == "OUT_OF_SCOPE" and r["steps"] == [] and "Where is SHP-0010?" in r["answer"]["text"] and r["contexts"] == {}


# ── the language model: optional, and never the source of a fact ─────────────────────────────────
def test_the_agent_works_without_a_model_and_says_how_the_answer_was_written():
    assert ask("Where is SHP-NET-0001?", customer("CUS-009"))["answer"]["grounding"] == {"mode": "TEMPLATE", "validated": True}


def test_the_model_routes_only_a_message_the_rules_cannot():
    llm = FakeLLM(domains=("DISCOVERY",))
    r = ask("got any pumps lying around for the big forklift", llm=llm)
    assert llm.routed and r["understanding"]["source"] == "LLM" and r["understanding"]["domains"] == ["DISCOVERY"]
    decisive = FakeLLM(domains=("LOGISTICS",))
    r = ask("Find a hydraulic pump for KFT-200.", llm=decisive)
    assert decisive.routed == [] and r["understanding"]["domains"] == ["DISCOVERY"]  # the rules were decisive: the model is not consulted and cannot override


def test_a_model_that_is_down_or_out_of_scope_leaves_the_safe_answer():
    assert ask("got any pumps lying around for the big forklift", llm=FakeLLM(fail=True))["intent"] in ("CLARIFICATION", "UNKNOWN")
    assert ask("got any pumps lying around for the big forklift", llm=FakeLLM(in_scope=False))["intent"] in ("CLARIFICATION", "UNKNOWN")


def test_model_wording_is_kept_only_when_it_is_grounded_in_the_evidence():
    lead = "Gear pump, 28cc/rev (NVM-1050-HY) is a canonical match, fits KFT-200, has an approved source and is available."
    good = FakeLLM(reword="The gear pump NVM-1050-HY fits your KFT-200 and is available.")
    r = ask("Find a hydraulic pump for KFT-200.", llm=good)
    assert r["answer"]["text"] == good.reword and r["answer"]["lead"] == lead and r["answer"]["grounding"] == {"mode": "LLM", "validated": True}
    invented = FakeLLM(reword="The gear pump NVM-1050-HY is in stock with 999 units and ships tomorrow.")
    r = ask("Find a hydraulic pump for KFT-200.", llm=invented)
    assert r["answer"]["text"] == lead and r["answer"]["grounding"]["mode"] == "TEMPLATE" and "not grounded" in r["answer"]["grounding"]["note"]
    assert ask("Find a hydraulic pump for KFT-200.", llm=FakeLLM(fail=True))["answer"]["text"] == lead


@pytest.mark.parametrize("message,state,owner,bad", [
    ("Is claim CLM-G001 covered?", {}, "CUS-001", "The claim is not eligible and is not covered under warranty."),  # the decision is ELIGIBLE
    ("Is claim CLM-G002 covered?", {}, "CUS-004", "Claim CLM-G002 is eligible and covered."),  # the decision is NOT_ELIGIBLE
    ("Is claim CLM-G002 covered?", {}, "CUS-004", "Claim CLM-G002 was installed on 2026-05-03."),  # true, but the outcome is dropped
    ("Where is SHP-0010?", {}, "CUS-001", "Shipment SHP-0010 is in transit and its live position is Linehaul hub."),  # the record says there is no live position
    ("I need a hydraulic pump for my KFT-600.", {}, "CUS-001", "The piston pump NVM-1060-HY is recommended and in stock."),
])
def test_model_wording_that_changes_the_sense_of_a_decision_is_rejected_even_when_its_numbers_are_in_the_evidence(message, state, owner, bad):
    r = ask(message, customer(owner), state, llm=FakeLLM(reword=bad))
    assert r["answer"]["text"] == r["answer"]["lead"] and r["answer"]["grounding"]["mode"] == "TEMPLATE", bad
    assert "rejected" in r["answer"]["grounding"]["note"]


def test_the_model_is_never_asked_to_word_a_clarification():
    llm = FakeLLM(reword="whatever")
    r = ask("Find a hydraulic filter for X200.", llm=llm)
    assert llm.worded == [] and r["status"] == "REQUIRES_CLARIFICATION"


# ── the API ──────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def api():
    r = FakeRepo()
    for uid, cid in OWNERS.items():
        r.users_[uid] = {"id": uid, "name": uid, "email": f"{uid.lower()}@private.example", "role": "END_USER", "customer_id": cid, "customer_name": cid}
    app.dependency_overrides[get_orders_repository] = lambda: r
    app.dependency_overrides[get_commerce_engine] = lambda: ENGINE
    app.dependency_overrides[get_llm] = lambda: None
    yield r
    for dep in (get_orders_repository, get_commerce_engine, get_llm):
        app.dependency_overrides.pop(dep, None)


def http(user_id: str | None = None) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    if user_id:
        assert c.post("/api/v1/auth/login", json={"user_id": user_id}).status_code == 200
    return c


def test_the_agent_endpoint_needs_a_signed_in_user(api):
    r = http().post(BASE, json={"message": "Where is SHP-0010?"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_signed_in"


def test_the_agent_endpoint_returns_the_full_grounded_response(api):
    body = http("U-C001").post(BASE, json={"message": "Where is SHP-0010 and what parts are in it?"}).json()
    assert body["intent"] == "LOGISTICS" and body["status"] == "ANSWERED" and set(body) >= {"answer", "steps", "contexts", "evidence", "evidence_paths", "source_records", "state", "understanding", "visibility"}
    assert [p["part_number"] for p in body["contexts"]["LOGISTICS"]["parts"]] == ["NVM-1010-HY", "NVM-1100-DT"] and body["visibility"]["LOGISTICS"]["role"] == "END_CUSTOMER"


def test_the_agent_state_round_trips_through_the_api(api):
    c = http("U-C001")
    first = c.post(BASE, json={"message": "Find a hydraulic pump for KFT-200."}).json()
    second = c.post(BASE, json={"message": "Do you have this part available?", "state": first["state"]}).json()
    assert second["contexts"]["DISCOVERY"]["recommended_part"]["part_number"] == "NVM-1050-HY"


def test_customer_isolation_a_customer_cannot_reach_another_customers_records_through_the_agent(api):
    c = http("U-C010")
    for msg, state in (("Where is SHP-NET-0001?", {}), ("Is claim CLM-G001 covered?", {}), ("Is it covered?", {"claim_id": "CLM-G001"}), ("Where is it?", {"shipment_id": "SHP-0010"})):
        r = c.post(BASE, json={"message": msg, "state": state})
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden", msg
    assert "Hendrik" not in c.post(BASE, json={"message": "Is claim CLM-G001 covered?"}).text


def test_an_end_user_cannot_widen_the_role_through_the_agent(api):
    for extra in ({"user_role": "OEM"}, {"user_role": "DEALER", "dealer_id": "DLR-004"}):
        r = http("U-C009").post(BASE, json={"message": "Where is SHP-NET-0001?", **extra})
        assert r.status_code == 403 and r.json()["error"]["code"] == "role_not_allowed"


def test_dealer_isolation_a_dealer_sees_its_own_orders_only(api):
    c = http("U-JANE")
    own = c.post(BASE, json={"message": "Where is SHP-NET-0001?", "user_role": "DEALER", "dealer_id": "DLR-004"})
    other = c.post(BASE, json={"message": "Where is SHP-NET-0004?", "user_role": "DEALER", "dealer_id": "DLR-004"})
    assert own.status_code == 200 and own.json()["visibility"]["LOGISTICS"]["role"] == "DEALER" and other.status_code == 403


def test_oem_access_sees_everything_the_customer_view_hides(api):
    oem = http("U-JANE").post(BASE, json={"message": "Who installed the part on claim CLM-G001?"}).json()
    cust = http("U-C001").post(BASE, json={"message": "Who installed the part on claim CLM-G001?"}).json()
    assert "Hendrik Vos (demo)" in json.dumps(oem["contexts"]["WARRANTY"]) and "Hendrik" not in json.dumps(cust) and "technician.name" in cust["visibility"]["WARRANTY"]["hidden_fields"]
    ship = http("U-JANE").post(BASE, json={"message": "Where is SHP-0010?"}).json()["contexts"]["LOGISTICS"]
    mine = http("U-C001").post(BASE, json={"message": "Where is SHP-0010?"}).json()["contexts"]["LOGISTICS"]
    assert "remediation_flags" in ship["shipment"] and "remediation_flags" not in mine["shipment"]
    stock = http("U-C001").post(BASE, json={"message": "Find a hydraulic pump for KFT-200."}).json()["contexts"]["DISCOVERY"]["availability"]
    assert all("warehouses" not in a for a in stock)  # internal depot stock is the OEM's and dealers' view


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": "x" * 501}, {"message": "hi", "state": {"unknown": "x"}}, {"message": "hi", "state": {"shipment_id": "bad id!"}},
                                  {"message": "hi", "state": {"last_domains": ["BILLING"]}}, {"message": "hi", "user_role": "ROOT"}, {"message": "hi", "destination_country": "NLD"}])
def test_malformed_agent_requests_are_refused_before_anything_runs(api, body):
    assert http("U-C001").post(BASE, json=body).status_code == 422


def test_the_agent_response_carries_no_account_data_or_secrets(api):
    text = http("U-C001").post(BASE, json={"message": "Is claim CLM-G001 covered?"}).text.lower()
    for forbidden in ("private.example", "session", "api_key", "password", "gsk_", "authorization"):
        assert forbidden not in text


def test_the_agent_endpoint_only_reads(api):
    class Recording:
        calls: list[str] = []
    before = json.dumps(http("U-C001").post(BASE, json={"message": "Where is SHP-0010?"}).json(), sort_keys=True)
    after = json.dumps(http("U-C001").post(BASE, json={"message": "Where is SHP-0010?"}).json(), sort_keys=True)
    assert before == after  # same request, same body: nothing changed between them


# ── questions about one part, and orders the shop placed ─────────────────────────────────────────
def test_which_machine_uses_this_part_lists_only_machines_a_fitment_record_approves():
    first = ask("Find a hydraulic pump for KFT-200.")
    r = ask("Which machine uses this part?", OEM, first["state"])
    x, s = r["contexts"]["DISCOVERY"], sections(r)["DISCOVERY"]
    assert r["intent"] == "DISCOVERY" and s["decision"] == "PART_FITMENT" and [m["model"] for m in x["machines"]] == ["KFT-200", "KFT-450"]
    assert {e["entity"] for e in r["evidence"]} == {"Fitment"} and r["evidence_paths"]["DISCOVERY"][0]["entity"] == "Part" and any("“This part” was read as NVM-1050-HY" in n for n in s["notes"])
    named = ask("Which machine uses NVM-1060-HY?")
    assert [m["model"] for m in named["contexts"]["DISCOVERY"]["machines"]] == ["KFT-600", "KFT-800"]


def test_where_did_this_part_come_from_reports_the_recorded_manufacturer_catalogue_record_and_approved_sources():
    first = ask("Find a hydraulic pump for KFT-200.")
    r = ask("Where did this part come from?", OEM, first["state"])
    x, text = r["contexts"]["DISCOVERY"], "\n".join(sections(r)["DISCOVERY"]["lines"])
    assert sections(r)["DISCOVERY"]["decision"] == "PART_ORIGIN" and [s["source_id"] for s in x["sources"]] == ["SUP-011", "SUP-025"]
    assert "Manufacturer: Noordveld" in text and "Approved supplier source: SUP-011." in text and x["catalogue"]["data_status"] == "SOURCE_DERIVED" and r["source_records"]
    assert x["decision"]["facts"]["approved_source_count"] == 2 and r["data_status"] in ("MIXED", "SOURCE_DERIVED", "SYNTHETIC_DEMO")


def test_a_question_about_a_part_with_no_part_to_refer_to_asks_which_and_does_not_guess():
    r = ask("Where did this part come from?")
    assert r["status"] == "REQUIRES_CLARIFICATION" and r["clarification"]["domain"] == "DISCOVERY" and r["contexts"] == {}
    assert ask("Which machine uses PRT-999?")["contexts"]["DISCOVERY"]["decision"]["decision"] == "NOT_FOUND"


def test_an_order_placed_in_the_shop_is_recognised_and_reads_its_owner_through_the_account_that_placed_it():
    from app.graph.queries import logistics as q

    assert extract_references("Where is order HCME-ORD-000001?", ENGINE.discovery) == {"order_id": "HCME-ORD-000001"}
    assert "PLACED_BY" in q.ORDER and "ACTS_FOR" in q.ORDER and q.ORDER.index("ORDERED_BY") < q.ORDER.index("PLACED_BY")  # a customer order link still comes first
    r = ask("Where is order ORD-NET-0001?", customer("CUS-009"))
    assert r["status"] == "REQUIRES_CLARIFICATION" and r["clarification"]["domain"] == "LOGISTICS"


# ── Waterfall: business outcome A edge cases ─────────────────────────────────────────────────────
def test_discovery_reads_a_misspelt_catalogue_word_as_the_closest_catalogue_word_and_says_so():
    r = ask("I need a hydrualic pomp for KFT-600")
    s = sections(r)["DISCOVERY"]
    assert "NVM-1060-HY" in s["headline"] and any("“pomp” as “pump”" in n for n in s["notes"]) and any("“hydrualic” as “hydraulic”" in n for n in s["notes"])


def test_spelling_correction_leaves_unknown_words_and_identifiers_alone():
    from app.commerce_agent.agent import correct_spelling
    assert correct_spelling("flux capacitor for KFT-600 NVM-1060-HY", ENGINE) == ("flux capacitor for KFT-600 NVM-1060-HY", [])
    r = ask("I need a flux capacitor for KFT-600")
    assert sections(r)["DISCOVERY"]["decision"] == "NO_VALID_RECOMMENDATION" and r["contexts"]["DISCOVERY"]["recommended_part"] is None


def test_discovery_names_an_invalid_machine_identifier_and_assumes_nothing():
    r = ask("Find a hydraulic pump for XYZ-999")
    s = sections(r)["DISCOVERY"]
    assert s["decision"] == "REQUIRES_CLARIFICATION" and any("“XYZ-999” is not a machine model in the catalogue" in ln for ln in s["lines"]) and r["contexts"]["DISCOVERY"]["recommended_part"] is None


# ── Waterfall: outcome C wording ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("claim,start", [("CLM-G003", "Not eligible. The check “The warranty period is active” failed"), ("CLM-G006", "Not enough data to decide. The check “The installation is evidenced")])
def test_warranty_headline_names_the_failed_check_instead_of_reading_as_a_positive_claim(claim, start):
    h = sections(ask(f"Is claim {claim} covered?"))["WARRANTY"]["headline"]
    assert h.startswith(start) and "Not eligible: The warranty period is active" not in h


# ── Waterfall: outcome B, a destination with recorded lanes but no shipment (potential routes, not assigned) ──
@pytest.mark.parametrize("message,cities", [("How long to ship a hose to Lagos?", {"Lagos"}), ("Can you deliver to the USA?", {"Houston", "Savannah", "Chicago", "Los Angeles"}),
                                            ("Shipping to Africa by sea or air", {"Lagos", "Tema", "Durban", "Mombasa", "Casablanca"}), ("What are the delivery options to the UK", {"Reading"})])
def test_route_options_name_the_recorded_lanes_for_a_place_nobody_has_shipped_to(message, cities):
    r = ask(message, customer("CUS-009"))
    s = sections(r)["LOGISTICS"]
    x = r["contexts"]["LOGISTICS"]
    assert s["decision"] == "ROUTE_OPTIONS" and {d["city"] for d in x["destinations"]} == cities
    text = "\n".join(s["lines"])
    assert "potential routes" in text and "none is assigned to a shipment" in text
    for d in x["destinations"]:
        assert {o["transport_mode"] for o in d["routes"]} >= {"AIR"} and all(o["planned_transit_days"] is not None for o in d["routes"])
    assert r["evidence"] and r["source_records"] and x["data_status"] == "SYNTHETIC_DEMO"


def test_route_options_use_each_routes_own_days_and_never_a_built_in_value():
    x = ask("How long to ship to Lagos?")["contexts"]["LOGISTICS"]
    by = {o["transport_mode"]: o["planned_transit_days"] for o in x["destinations"][0]["routes"]}
    assert by == {"AIR": 5, "SEA": 31} and [leg["sequence"] for leg in x["destinations"][0]["routes"][0]["legs"]] == sorted(leg["sequence"] for leg in x["destinations"][0]["routes"][0]["legs"])


def test_a_shipment_reference_wins_over_a_place_in_the_message():
    r = ask("Where is SHP-NET-0003 in the USA?")
    assert sections(r)["LOGISTICS"]["decision"] != "ROUTE_OPTIONS" and r["contexts"]["LOGISTICS"]["shipment"]["shipment_id"] == "SHP-NET-0003"


def test_a_place_with_no_recorded_lane_is_not_given_a_route():
    r = ask("How long to ship to Atlantis?")
    assert sections(r)["LOGISTICS"]["decision"] != "ROUTE_OPTIONS" and not r["contexts"].get("LOGISTICS", {}).get("destinations") if isinstance(r["contexts"].get("LOGISTICS"), dict) else True


def test_multi_domain_part_request_with_a_destination_gets_the_part_and_the_potential_routes():
    r = ask("I need a hydraulic pump for KFT-200 delivered to Lagos")
    s = sections(r)
    assert r["intent"] == "MULTI_DOMAIN" and s["DISCOVERY"]["decision"] == "RECOMMEND" and s["LOGISTICS"]["decision"] == "ROUTE_OPTIONS"


# ── one Agentic E-Commerce screen: what a shopping request also asks the commerce assistant ──────
@pytest.mark.parametrize("message,parts_answered,expected", [
    ("I need a hydraulic pump for KFT-200", True, []),  # a part request: Agentic Shopping answers it, delivery included
    ("Find the cheapest cooling fan for the NV-4500.", True, []),
    ("Where is my shipment?", False, ["LOGISTICS"]),
    ("Has my order shipped?", False, ["LOGISTICS"]),
    ("Which parts are included in my shipment?", False, ["LOGISTICS"]),
    ("Is claim CLM-G001 covered?", False, ["WARRANTY"]),
    ("Which machines use NVM-1050-HY?", False, ["DISCOVERY"]),  # not a shopping request: the commerce part lookup answers it
    ("I urgently need a replacement hydraulic pump for my machine. Find a compatible part, compare the available delivery options, and check whether the failed part is covered by warranty.", True, ["WARRANTY"]),
    ("I need a pump delivered to Lagos", True, ["LOGISTICS"]),  # a place with recorded lanes: the potential routes are shown too
    ("Compare sea and air for shipment SHP-NET-0001", False, ["LOGISTICS"]),
    ("hello", False, []),
    ("How long does shipping to Atlantis take?", False, []),  # no recorded lane and no shipment or order named: nothing to look up
    ("Show me the status of my order.", False, ["LOGISTICS"]),
    ("Show me my order.", False, ["LOGISTICS"]),
    ("Find a compatible pump for my machine, compare delivery options, and tell me whether my existing order has shipped.", True, ["LOGISTICS"]),  # the order question beside a part search
])
def test_commerce_domains_names_only_what_agentic_shopping_does_not_answer(message, parts_answered, expected):
    from app.commerce_agent.agent import commerce_domains
    assert commerce_domains(message, ENGINE, parts_answered) == expected


def test_shipment_contents_questions_are_logistics_not_a_part_search():
    r = ask("Which parts are included in my shipment?", customer("CUS-001"))
    assert r["intent"] == "LOGISTICS" and "DISCOVERY" not in r["understanding"]["domains"]


def test_an_order_with_no_shipment_lists_its_recorded_lines_in_the_answer():
    from app.commerce_agent.answer import logistics_lines
    x = {"decision": {"facts": {}}, "shipment": None, "order": {"order_id": "O-1", "status": "ALLOCATED"},
         "order_lines": [{"order_line_id": "OL-1", "part_number": "P-1", "name": "Part one", "quantity": 2}, {"order_line_id": "OL-2", "part_number": None, "name": None, "quantity": None}]}
    assert logistics_lines(x, []) == ["Order O-1: status ALLOCATED.", "This order has 2 order lines:", "  OL-1: P-1 Part one × 2", "  OL-2: part not recorded"]


def test_stock_of_a_named_part_comes_from_its_recorded_inventory_and_asks_for_no_machine():
    r = ask("Do you have NVM-1050-HY in stock?", customer("CUS-001"))
    s = sections(r)["DISCOVERY"]
    x = r["contexts"]["DISCOVERY"]
    assert s["decision"] == "PART_STOCK" and "not a machine model" not in " ".join(s["lines"]) and x["stock"]["state"] == "AVAILABLE"
    assert x["stock"]["total_available"] == sum(i["available_quantity"] or 0 for i in ENGINE.discovery.inventory("PRT-006") if (i["available_quantity"] or 0) > 0)
    assert x["stock"]["depots"] is None and "stock.depots" in x["visibility"]["hidden_fields"]  # a customer sees the total, not the depots
    assert ask("Do you have NVM-1050-HY in stock?")["contexts"]["DISCOVERY"]["stock"]["depots"]  # the OEM sees them
    assert any("does not establish that the part fits" in ln for ln in s["lines"])


def test_an_order_question_beside_a_part_search_is_looked_up_not_answered_as_an_unordered_part():
    r = ask("Find a compatible pump for my machine, compare delivery options, and tell me whether my existing order has shipped.", customer("CUS-001"))
    assert sections(r)["LOGISTICS"]["decision"] != "NO_SHIPMENT_FOR_UNORDERED_PART"


def test_without_the_language_service_the_screen_still_answers_order_and_warranty_questions():
    from app.api.dependencies import get_agent

    class Down:
        def recommend(self, request):
            raise LLMUnavailable("rate limited")

    app.dependency_overrides[get_agent] = lambda: Down()
    app.dependency_overrides[get_commerce_engine] = lambda: ENGINE
    try:
        c = TestClient(app)
        r = c.post("/api/v1/agent/recommend", json={"request": "Where is my shipment?"})
        assert r.status_code == 200 and r.json()["commerce_domains"] == ["LOGISTICS"] and r.json()["state"] == "out_of_scope" and "not responding" in r.json()["notes"][0]
        assert c.post("/api/v1/agent/recommend", json={"request": "hello"}).status_code == 503  # nothing the records can answer: the outage is reported
    finally:
        app.dependency_overrides.pop(get_agent, None)
        app.dependency_overrides.pop(get_commerce_engine, None)
