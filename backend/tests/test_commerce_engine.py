"""Phase 4: the Commerce Context Engine over the canonical dataset files (no database). Discovery, logistics and warranty contexts, golden scenarios, the common contract,
provenance, evidence paths, missing-data behaviour, authorization, visibility and determinism. The live-graph checks are at the end and skip when the graph is unreachable."""
from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.canonical.io import CANON_DIR
from app.commerce import contract as c
from app.commerce.access import AccessDenied, CommerceRole, Principal, principal_for
from app.commerce.discovery import WEIGHTS, DiscoveryContextBuilder
from app.commerce.engine import CommerceContextEngine
from app.commerce.intent import select_intent
from app.commerce.service import AgenticCommerceService, ServiceRequest
from app.core.config import get_settings
from app.core.roles import Role
from app.services.orders import User
from tests.support import commerce as t

AS_OF = date(2026, 10, 7)
GOLDEN_WARRANTY = {"CLM-G001": "ELIGIBLE", "CLM-G002": "NOT_ELIGIBLE", "CLM-G003": "NOT_ELIGIBLE", "CLM-G004-2": "REQUIRES_REVIEW", "CLM-G005": "REQUIRES_REVIEW",
                   "CLM-G006": "INSUFFICIENT_DATA", "CLM-G007": "NOT_ELIGIBLE", "CLM-G008": "NOT_ELIGIBLE"}


@pytest.fixture(scope="module")
def engine() -> CommerceContextEngine:
    return CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)


def P(role: str, **kw) -> Principal:
    return Principal(CommerceRole(role), user_id="u", **kw)


def memory_builder(**datasets) -> DiscoveryContextBuilder:
    return DiscoveryContextBuilder(t.MemoryDiscoveryReader(**datasets), date(2026, 10, 7), "2026-10-07T00:00:00Z")


def ok_dataset(**over):
    base = {"fitment": [t.fit()], "approved_sources": [t.source()], "inventory": [t.stock()], "pricing": [t.price()]}
    return {**base, **over}


# ── the common contract ──────────────────────────────────────────────────────────────────────────
COMMON = ("context_id", "context_type", "generated_at", "data_status", "source_records", "evidence", "confidence", "missing", "warnings")


def all_contexts(engine):
    return [engine.build_discovery_context("I need a hydraulic pump for my KFT-600."), engine.build_logistics_context(shipment_id="SHP-NET-0001"), engine.build_warranty_context(claim_id="CLM-G001")]


def test_every_context_carries_the_common_metadata_and_a_decision(engine):
    for ctx in all_contexts(engine):
        d = ctx.to_dict()
        assert all(k in d for k in COMMON), ctx.context_type
        assert d["decision"]["status"] in c.STATUSES and set(d["decision"]) >= {"status", "decision", "summary", "facts", "reasons", "evidence", "source_records", "missing", "warnings", "recommended_next_action"}
        assert d["evidence_path"] and [s["step"] for s in d["evidence_path"]] == list(range(1, len(d["evidence_path"]) + 1))
        assert d["source_records"] and all(r["entity"] and r["id"] for r in d["source_records"])
        assert d["context_id"].startswith("CTX-") and d["confidence"]["level"] in ("COMPLETE", "PARTIAL", "INSUFFICIENT")
        json.dumps(d)  # plain JSON, nothing to serialise specially


def test_nothing_is_called_verified_on_demonstration_data(engine):
    for ctx in all_contexts(engine):
        assert ctx.confidence["verified"] is False and "not verified" in ctx.confidence["basis"]
    assert c.confidence_for(c.SUCCESS, [{"data_status": "SOURCE_DERIVED"}], [])["verified"] is True  # only graph-supported data can ever be called verified
    assert c.confidence_for(c.SUCCESS, [{"data_status": "SOURCE_DERIVED"}], ["price:P-1"])["verified"] is False
    assert c.confidence_for(c.INSUFFICIENT_DATA, [{"data_status": "REAL"}], [])["verified"] is False


def test_the_same_request_on_the_same_data_gives_the_same_structured_result():
    first = [x.to_dict() for x in all_contexts(CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF))]
    second = [x.to_dict() for x in all_contexts(CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF))]
    assert json.dumps(first, sort_keys=False) == json.dumps(second, sort_keys=False)  # identical, including key order and generated_at (pinned to the reference day)
    other_day = [x.to_dict() for x in all_contexts(CommerceContextEngine.from_files(CANON_DIR, as_of=date(2026, 10, 8)))]
    assert [x["context_id"] for x in first] != [x["context_id"] for x in other_day]  # the reference day is part of the identity


def test_with_a_real_clock_only_generated_at_may_differ():
    a = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF, clock=lambda: datetime(2026, 10, 7, 1, tzinfo=timezone.utc)).build_warranty_context(claim_id="CLM-G001").to_dict()
    b = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF, clock=lambda: datetime(2026, 10, 7, 9, tzinfo=timezone.utc)).build_warranty_context(claim_id="CLM-G001").to_dict()
    assert a["generated_at"] != b["generated_at"] and a["context_id"] == b["context_id"]
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


# ── discovery: golden scenarios on the real data ─────────────────────────────────────────────────
def test_discovery_positive_kft600_hydraulic_pump_gets_an_approved_fitting_available_part_with_an_approved_source(engine):
    ctx = engine.build_discovery_context("I need a hydraulic pump for my KFT-600.")
    assert ctx.machine["resolution"] == "RESOLVED" and ctx.machine["model"] == "KFT-600" and ctx.machine["machine_id"] == "MCH-009" and ctx.machine["via"] == "model_identifier"
    rec = ctx.recommended_part
    assert ctx.decision.status == c.SUCCESS and ctx.decision.decision == "RECOMMEND" and rec["part_id"] == "PRT-097"
    assert (rec["fitment"], rec["approved_source"], rec["availability"]) == ("APPROVED", True, "AVAILABLE")
    # the recommendation rests on records: the approved fitment, the approved sources and the stock, in that order
    assert [s["entity"] for s in ctx.evidence_path] == ["Part", "Fitment", "ApprovedSource", "Inventory", "Price"]
    fitment = next(r for r in ctx.fitment_results if r["part_id"] == "PRT-097")
    assert fitment["state"] == "APPROVED" and fitment["fitment_id"] == ctx.evidence_path[1]["id"]
    assert next(a for a in ctx.approved_sources if a["part_id"] == "PRT-097")["has_approved_source"] is True


def test_the_fitting_pump_that_is_out_of_stock_is_rejected_not_hidden_and_not_recommended(engine):
    ctx = engine.build_discovery_context("I need a hydraulic pump for my KFT-600.")
    assert "PRT-007" in ctx.rejection_reasons and [r["code"] for r in ctx.rejection_reasons["PRT-007"]] == ["NOT_AVAILABLE"]  # PRT-007 fits and has an approved source: no stock anywhere
    assert ctx.decision.facts["valid_candidates"] == 1 and ctx.decision.facts["rejected_candidates"] == len(ctx.rejection_reasons)
    assert ctx.recommended_part["part_id"] != "PRT-007"
    seven = next(x for x in ctx.candidate_parts if x["part_id"] == "PRT-007")
    assert seven["validation"] == "REJECTED" and seven["rank"] is None
    assert next(a for a in ctx.availability if a["part_id"] == "PRT-007")["state"] == "NOT_AVAILABLE"
    assert [r["code"] for r in ctx.rejection_reasons["PRT-006"]] == ["NO_FITMENT"] and [r["code"] for r in ctx.rejection_reasons["PRT-078"]] == ["NO_FITMENT"]  # pumps for other machines


def test_the_recommendation_says_how_good_the_vocabulary_match_is(engine):
    ctx = engine.build_discovery_context("I need a hydraulic pump for my KFT-600.")
    assert ctx.recommended_part["semantic_match"] == "MEDIUM"  # 'hydraulic pump' is only an alias of this lubrication pump; not claimed as a perfect match
    assert any("secondary vocabulary" in w for w in ctx.warnings)
    assert ctx.recommended_part["explanation"]["lines"][:3] == ["fitment = APPROVED", "approved_source = YES", "availability = AVAILABLE"]
    assert ctx.confidence["verified"] is False


def test_discovery_negative_a_pump_that_fits_other_machines_only_gives_no_valid_recommendation(engine):
    ctx = engine.build_discovery_context("I need a hydraulic pump for my NV-2100")
    assert ctx.machine["machine_id"] == "MCH-001" and ctx.recommended_part is None
    assert (ctx.decision.status, ctx.decision.decision) == (c.NOT_FOUND, "NO_VALID_RECOMMENDATION")
    assert {r["code"] for rs in ctx.rejection_reasons.values() for r in rs} >= {"NO_FITMENT"} and ctx.candidate_parts  # candidates were found and each one is explained
    assert all(x["validation"] == "REJECTED" for x in ctx.candidate_parts) and ctx.evidence_path == []
    assert ctx.decision.reasons and ctx.decision.recommended_next_action


def test_discovery_insufficient_an_unknown_machine_identifier_requires_clarification_and_is_not_guessed(engine):
    ctx = engine.build_discovery_context("I need a hydraulic filter for my X200.")
    assert (ctx.decision.status, ctx.decision.decision) == (c.REQUIRES_CLARIFICATION, "REQUIRES_CLARIFICATION") and ctx.recommended_part is None
    assert ctx.machine["resolution"] == "NOT_RESOLVED" and ctx.machine["machine_id"] is None and ctx.machine["unmatched_identifiers"] == ["x200"]
    assert [s["model"] for s in ctx.machine["suggestions"]] == ["KFT-200"]  # offered as a question; never used as the machine
    assert ctx.candidate_parts and all(x["validation"] == "NOT_VALIDATED" for x in ctx.candidate_parts)
    assert ctx.fitment_results == [] and ctx.rejection_reasons == {} and "machine" in ctx.missing


@pytest.mark.parametrize("text,resolution", [("I need a hydraulic pump", "NOT_STATED"), ("hydraulic pump for my KFT", "AMBIGUOUS"), ("a pump for my loader", "AMBIGUOUS"),
                                              ("pump for the KFT-600 or the NV-2100", "AMBIGUOUS")])
def test_an_ambiguous_or_missing_machine_is_always_a_question(engine, text, resolution):
    ctx = engine.build_discovery_context(text)
    assert ctx.decision.status == c.REQUIRES_CLARIFICATION and ctx.machine["resolution"] == resolution and ctx.recommended_part is None
    if resolution == "AMBIGUOUS":
        assert len(ctx.machine["options"]) >= 2


def test_a_request_with_no_part_in_it_asks_which_part(engine):
    ctx = engine.build_discovery_context("I need a part for my KFT-600")
    assert ctx.decision.status == c.REQUIRES_CLARIFICATION and "part" in ctx.missing and ctx.clarification["kind"] == "part_unspecified"


def test_the_machine_can_come_from_an_id_or_an_owned_instance_never_from_a_guess(engine):
    by_id = engine.build_discovery_context("hydraulic pump", machine_id="MCH-007")
    assert by_id.machine["via"] == "machine_id" and by_id.recommended_part["part_id"] == "PRT-006"
    assert engine.build_discovery_context("hydraulic pump", machine_id="MCH-999").decision.status == c.NOT_FOUND
    owner = P("END_CUSTOMER", customer_id="CUS-001")
    via = engine.build_discovery_context("hydraulic pump", principal=owner, machine_instance_id="MI-G001")
    assert via.machine["via"] == "machine_instance" and via.machine["machine_id"] == "MCH-009"
    with pytest.raises(AccessDenied):
        engine.build_discovery_context("hydraulic pump", principal=P("END_CUSTOMER", customer_id="CUS-004"), machine_instance_id="MI-G001")


def test_a_part_number_is_looked_up_exactly(engine):
    ctx = engine.build_discovery_context("NVM-1060-HY for my KFT-600")
    assert ctx.extracted["part_identifiers"] == ["PRT-007"] and ctx.candidate_parts[0]["semantic_match"]["via"] == "IDENTIFIER"
    assert ctx.decision.decision == "NO_VALID_RECOMMENDATION" and [r["code"] for r in ctx.rejection_reasons["PRT-007"]] == ["NOT_AVAILABLE"]


# ── discovery: every rejection reason, on small controlled data ──────────────────────────────────
def build(text="gear pump for my ZX-100", **datasets):
    return memory_builder(**ok_dataset(**datasets)).build(text)


def codes(ctx, pid="P-1"):
    return [r["code"] for r in ctx.rejection_reasons.get(pid, [])]


def test_the_all_green_candidate_is_recommended_with_its_price():
    ctx = build()
    assert ctx.decision.decision == "RECOMMEND" and ctx.recommended_part["part_id"] == "P-1" and ctx.recommended_part["price"]["unit_price"] == 10.0
    assert ctx.recommended_part["semantic_match"] == "HIGH" and ctx.rejection_reasons == {}


def test_no_fitment_not_approved_and_deprecated_fitment_are_told_apart():
    assert codes(build(fitment=[])) == ["NO_FITMENT"]
    assert codes(build(fitment=[t.fit(status="CONDITIONAL", approval="CONDITIONAL")])) == ["NOT_APPROVED"]
    assert codes(build(fitment=[t.fit(approval="NOT_APPROVED", status="NOT_APPROVED")])) == ["NOT_APPROVED"]
    assert codes(build(fitment=[t.fit(status="DEPRECATED", approval="DEPRECATED")])) == ["DEPRECATED"]
    assert codes(build(fitment=[t.fit(valid_to="2026-01-01")])) == ["DEPRECATED"]  # in the past: no longer in force
    assert build(fitment=[t.fit(valid_to="2026-12-31")]).decision.decision == "RECOMMEND"


def test_a_part_without_an_approved_source_is_never_recommended_however_well_it_fits():
    ctx = build(approved_sources=[])
    assert ctx.recommended_part is None and codes(ctx) == ["NO_APPROVED_SOURCE"] and ctx.decision.decision == "NO_VALID_RECOMMENDATION"
    assert ctx.rejection_reasons["P-1"][0]["source"]["basis"] == "ABSENCE_OF_RECORD"
    assert codes(build(approved_sources=[t.source(status="NOT_APPROVED")])) == ["NO_APPROVED_SOURCE"]
    assert codes(build(approved_sources=[t.source(valid_to="2026-06-30")])) == ["NO_APPROVED_SOURCE"]


def test_out_of_region_needs_a_known_destination_and_a_regional_restriction():
    restricted = {"approved_sources": [t.source(regions=["US"])]}
    assert codes(memory_builder(**ok_dataset(**restricted)).build("gear pump for my ZX-100", destination_country="NL")) == ["OUT_OF_REGION"]
    assert build(**restricted).decision.decision == "RECOMMEND"  # destination unknown: not applied, and said so
    assert any("No destination country" in w for w in build(**restricted).warnings)
    assert memory_builder(**ok_dataset(**restricted)).build("gear pump for my ZX-100", destination_country="US").decision.decision == "RECOMMEND"
    assert memory_builder(**ok_dataset(approved_sources=[t.source(regions=["EUROPE"])])).build("gear pump for my ZX-100", destination_country="DE").decision.decision == "RECOMMEND"


def test_unavailable_part_and_unknown_stock_are_both_kept_out_of_the_recommendation_for_different_reasons():
    assert codes(build(inventory=[t.stock(qty=0, status="OUT_OF_STOCK")])) == ["NOT_AVAILABLE"]
    assert codes(build(inventory=[])) == ["NOT_AVAILABLE"]
    unknown = build(inventory=[{**t.stock(qty=0, status="UNKNOWN"), "available_quantity": None}])
    assert unknown.recommended_part is None and codes(unknown) == ["AVAILABILITY_UNKNOWN"]  # unknown is neither 'available' nor 'out of stock'
    assert "availability:P-1" in unknown.missing and unknown.availability[0]["state"] == "UNKNOWN" and unknown.availability[0]["total_available"] is None


def test_low_stock_is_still_available_but_scores_lower():
    ctx = build(inventory=[t.stock(qty=2, status="LOW_STOCK")])
    assert ctx.decision.decision == "RECOMMEND" and ctx.ranking[0]["components"]["availability_score"] == 0.5


def test_unverified_and_deprecated_parts_are_rejected_by_their_catalogue_status():
    assert codes(memory_builder(**ok_dataset(parts=[t.part(status="UNVERIFIED")])).build("gear pump for my ZX-100")) == ["NOT_APPROVED"]
    assert codes(memory_builder(**ok_dataset(parts=[t.part(status="DEPRECATED")])).build("gear pump for my ZX-100")) == ["DEPRECATED"]


def test_a_missing_price_is_missing_not_zero():
    ctx = build(pricing=[])
    assert ctx.decision.decision == "RECOMMEND" and ctx.recommended_part["price"]["unit_price"] is None and "price:P-1" in ctx.missing and ctx.confidence["level"] == "PARTIAL"


def test_a_rejected_candidate_can_have_several_reasons_all_kept():
    ctx = build(fitment=[], approved_sources=[], inventory=[])
    assert codes(ctx) == ["NO_FITMENT", "NO_APPROVED_SOURCE", "NOT_AVAILABLE"]


def test_ranking_is_transparent_deterministic_and_breaks_ties_by_part_id():
    parts = [t.part("P-2", "Gear pump"), t.part("P-1", "Gear pump"), t.part("P-3", "Gear pump")]
    ds = {"parts": parts, "fitment": [t.fit(p["part_id"]) for p in parts], "approved_sources": [t.source(p["part_id"]) for p in parts],
          "inventory": [t.stock("P-1"), t.stock("P-2"), t.stock("P-3", qty=3, status="LOW_STOCK")], "pricing": [t.price(p["part_id"]) for p in parts]}
    ctx = memory_builder(**ds).build("gear pump for my ZX-100")
    assert [r["part_id"] for r in ctx.ranking] == ["P-1", "P-2", "P-3"]  # equal scores by id, then the low-stock part below both
    assert ctx.ranking[2]["components"]["availability_score"] == 0.5 and ctx.ranking[2]["outranked_by_top"] == [{"component": "availability_score", "top": 1.0, "this": 0.5}]
    assert ctx.ranking[0]["total_score"] > ctx.ranking[2]["total_score"] and ctx.scoring["weights"] == WEIGHTS
    assert ctx.recommended_part["part_id"] == "P-1"


def test_weights_are_an_explicit_policy_that_sums_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0 and set(WEIGHTS) == {"fitment_score", "approval_score", "availability_score", "semantic_match_score", "regional_score"}


def test_a_stronger_vocabulary_match_ranks_above_a_weaker_one_with_everything_else_equal():
    parts = [t.part("P-1", "Gear pump"), t.part("P-2", "Lift cylinder", aliases=["gear pump"], common_names=["gear pump"])]
    ds = {"parts": parts, "categories": [{"category_id": "C-1", "name": "Hydraulics"}, {"category_id": "S-1", "name": "Misc"}], "fitment": [t.fit(p["part_id"]) for p in parts],
          "approved_sources": [t.source(p["part_id"]) for p in parts], "inventory": [t.stock(p["part_id"]) for p in parts], "pricing": []}
    ctx = memory_builder(**ds).build("gear pump for my ZX-100")
    assert [r["part_id"] for r in ctx.ranking] == ["P-1", "P-2"] and ctx.ranking[0]["explanation"]["semantic_match"] == "HIGH" and ctx.ranking[1]["explanation"]["semantic_match"] == "MEDIUM"


def test_regional_stock_is_a_ranking_component_only_when_the_destination_is_known():
    parts = [t.part("P-1", "Gear pump"), t.part("P-2", "Gear pump")]
    ds = {"parts": parts, "locations": [t.whouse("WH-EU", "EUROPE", "NL"), t.whouse("WH-US", "USA", "US")], "fitment": [t.fit(p["part_id"]) for p in parts],
          "approved_sources": [t.source(p["part_id"]) for p in parts], "inventory": [t.stock("P-1", "WH-US"), t.stock("P-2", "WH-EU")], "pricing": []}
    unknown = memory_builder(**ds).build("gear pump for my ZX-100")
    assert [r["part_id"] for r in unknown.ranking] == ["P-1", "P-2"] and unknown.ranking[0]["components"]["regional_score"] is None
    nl = memory_builder(**ds).build("gear pump for my ZX-100", destination_country="NL")
    assert [r["part_id"] for r in nl.ranking] == ["P-2", "P-1"] and nl.ranking[0]["components"]["regional_score"] == 1.0 and nl.ranking[1]["components"]["regional_score"] == 0.0


# ── logistics ────────────────────────────────────────────────────────────────────────────────────
def test_logistics_golden_the_sea_shipment_where_is_my_pump(engine):
    ctx = engine.build_logistics_context(shipment_id="SHP-NET-0001")
    f = ctx.decision.facts
    assert ctx.decision.status == c.SUCCESS and ctx.current_status == "IN_TRANSIT" and f["shipment_status"] == "IN_TRANSIT" and ctx.route["route_id"] == "RTE-NET-JPNL-SEA-ECO"
    assert (f["completed_leg_count"], f["remaining_leg_count"], f["position"]) == (1, 3, "on_leg")
    assert [x["sequence"] for x in ctx.completed_legs] == [1] and [x["sequence"] for x in ctx.remaining_legs] == [2, 3, 4]
    assert ctx.planned_eta["planned_eta"] == "2026-11-19" and ctx.planned_eta["days_to_eta"] == 43 and f["planned_eta"] == "2026-11-19"
    assert ctx.current_location["known"] is False and any("no live position" in w for w in ctx.warnings)  # at sea: nothing invented
    assert ctx.origin["name"].startswith("Chubu") and ctx.destination["location_id"] == "DLR-004" and ctx.part["part_number"] == "NVM-1010-HY" and ctx.order["order_id"] == "ORD-NET-0001"
    assert [l["order_line_id"] for l in ctx.order_lines] == ["OL-NET-0001"] and ctx.order_lines[0]["quantity"] == 50
    assert [s["entity"] for s in ctx.evidence_path] == ["Order", "Shipment", "Route", "TrackingEvent"]
    assert ctx.requires_review is False and ctx.route_resolution_status == "LINKED"


def test_logistics_comparison_is_calculated_from_the_route_records_only(engine):
    ctx = engine.build_logistics_context(shipment_id="SHP-NET-0001")
    routes = {r["route_id"]: r for r in json.loads((CANON_DIR / "logistics" / "network_routes.json").read_text(encoding="utf-8"))["records"]}
    cur, air = routes["RTE-NET-JPNL-SEA-ECO"], routes["RTE-NET-JPNL-AIR-EXP"]
    assert (ctx.route["planned_transit_days"], ctx.route["estimated_cost"]) == (91, 2835.0) and (air["total_estimated_days"] if "total_estimated_days" in air else air["planned_transit_days"], air["estimated_cost"]) == (6, 12675.0)
    alt = next(a for a in ctx.decision.facts["alternatives"] if a["route_id"] == "RTE-NET-JPNL-AIR-EXP")
    assert alt["transport_mode"] == "AIR" and alt["planned_transit_days"] == 6 and alt["estimated_cost"] == 12675.0
    assert alt["days_vs_current"] == air_days(routes, air) - cur_days(routes, cur) == -85 and alt["cost_vs_current"] == round(air["estimated_cost"] - cur["estimated_cost"], 2) == 9840.0
    assert ctx.decision.facts["fastest_route_id"] == "RTE-NET-JPNL-AIR-EXP" and ctx.decision.facts["lowest_cost_route_id"] == "RTE-NET-JPNL-SEA-ECO"
    assert len(ctx.alternative_routes) == 2 and ctx.transport_comparison["options"]


def air_days(routes, r):
    return r.get("planned_transit_days", r.get("total_estimated_days"))


def cur_days(routes, r):
    return r.get("planned_transit_days", r.get("total_estimated_days"))


def test_the_application_contains_no_rule_about_how_fast_or_dear_a_mode_is():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[1] / "app" / "commerce").glob("*.py"))
    assert not re.search(r"(air|sea)_is_|faster_than|x_faster|\b(SEA|AIR)\b\s*[:=]\s*\d", src) and not re.search(r"days\s*[:=]\s*\d{2}", src)


def test_logistics_in_transit_by_air_a_delivered_shipment_and_a_us_shipment(engine):
    air = engine.build_logistics_context(shipment_id="SHP-NET-0002")
    assert air.current_status == "OUT_FOR_DELIVERY" and air.decision.facts["completed_leg_count"] == 3 and air.current_location["known"] is True
    done = engine.build_logistics_context(shipment_id="SHP-NET-0004")
    assert done.decision.decision == "DELIVERED" and done.decision.facts["delivered"] is True and done.remaining_legs == [] and done.decision.facts["days_to_eta"] is None
    assert done.shipment["actual_eta"] == "2026-09-23" and done.decision.status == c.SUCCESS
    us = engine.build_logistics_context(shipment_id="SHP-NET-0003")
    assert us.destination["country_code"] == "US" and us.decision.facts["remaining_leg_count"] == 2


def test_the_eleven_unresolved_shipments_are_insufficient_data_and_need_review(engine):
    ids = [r["shipment_id"] for r in csv.DictReader(open(CANON_DIR / "logistics" / "shipments.csv", encoding="utf-8")) if r["route_resolution_status"] == "ROUTE_NOT_DETERMINABLE"]
    assert len(ids) == 11
    for sid in ids:
        ctx = engine.build_logistics_context(shipment_id=sid)
        assert ctx.decision.status == c.INSUFFICIENT_DATA and ctx.decision.decision == "ROUTE_NOT_DETERMINABLE" and ctx.requires_review is True, sid
        assert ctx.route is None and ctx.route_legs == [] and ctx.completed_legs == [] and ctx.remaining_legs == [] and ctx.alternative_routes == [] and ctx.transport_comparison is None
        assert "route" in ctx.missing and ctx.route_resolution_status == "ROUTE_NOT_DETERMINABLE" and ctx.decision.facts["alternatives"] == []
        assert ctx.current_status and ctx.confidence["level"] == "INSUFFICIENT"  # what IS known (the status) is still given


def test_an_unknown_shipment_and_an_order_without_shipment_are_not_found(engine):
    assert engine.build_logistics_context(shipment_id="SHP-NOPE").decision.status == c.NOT_FOUND
    assert engine.build_logistics_context(order_id="ORD-NOPE").decision.status == c.NOT_FOUND
    assert engine.build_logistics_context().decision.status == c.REQUIRES_CLARIFICATION  # nothing to go on


def test_an_order_with_two_shipments_asks_which_one(engine):
    ctx = engine.build_logistics_context(order_id="ORD-NET-0001")
    assert ctx.decision.status == c.REQUIRES_CLARIFICATION and [o["shipment_id"] for o in ctx.clarification["options"]] == ["SHP-NET-0001", "SHP-NET-0002"]
    assert engine.build_logistics_context(order_id="ORD-NET-0002").shipment["shipment_id"] == "SHP-NET-0003"


# ── warranty ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("claim,expected", sorted(GOLDEN_WARRANTY.items()))
def test_warranty_golden_scenarios_through_the_public_engine(engine, claim, expected):
    ctx = engine.build_warranty_context(claim_id=claim)
    assert ctx.decision.decision == expected
    assert ctx.decision.status == (c.SUCCESS if expected == "ELIGIBLE" else expected)
    assert ctx.claim["claim_id"] == claim and ctx.decision_factors and ctx.decision.reasons


def test_the_engine_agrees_with_the_phase_3_evaluator_on_every_claim_in_the_data():
    from app.lifecycle.context import WarrantyContextBuilder
    from app.lifecycle.readers import FileReader

    reader = FileReader(CANON_DIR)
    builder = WarrantyContextBuilder(reader, AS_OF)
    e = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)
    for cid in reader.claim_ids():
        assert e.build_warranty_context(claim_id=cid).decision.decision == builder.for_claim(cid).outcome, cid


def test_warranty_contract_fields_and_the_eligible_scenario_facts(engine):
    ctx = engine.build_warranty_context(claim_id="CLM-G001")
    for name in ("machine", "current_part", "installation", "dealer", "technician", "work_order", "fitment", "approved_source", "warranty_policy", "coverage_start", "coverage_end",
                 "replacement_history", "prior_claims", "evidence", "decision", "decision_factors", "missing", "provenance"):
        assert hasattr(ctx, name), name
    f = ctx.decision.facts
    assert f["coverage_active"] is True and f["authorized_dealer"] is True and f["approved_part"] is True and ctx.dealer["dealer_id"] == "DLR-004"
    assert ctx.coverage_start and ctx.coverage_end and ctx.missing == [] and ctx.confidence["level"] == "COMPLETE"


def test_every_decision_factor_names_its_source_record_and_no_boolean_is_unexplained(engine):
    for claim in GOLDEN_WARRANTY:
        ctx = engine.build_warranty_context(claim_id=claim)
        for fac in ctx.decision_factors:
            assert fac["sources"], (claim, fac["code"])  # a source record, or the record that was searched when the factor rests on an absence
            assert all(s["entity"] != "Record" and s["id"] for s in fac["sources"]), (claim, fac["code"], fac["sources"])
            assert fac["detail"] and fac["basis"] in ("RECORDS", "ABSENCE_OF_RECORD") and fac["result"] in (True, False, None)
    dealer = next(x for x in engine.build_warranty_context(claim_id="CLM-G001").decision_factors if x["name"] == "authorised_dealer_install")
    assert dealer["result"] is True and dealer["sources"] == [{"entity": "Dealer", "id": "DLR-004"}]
    failed = next(x for x in engine.build_warranty_context(claim_id="CLM-G002").decision_factors if x["name"] == "authorised_dealer_install")
    assert failed["result"] is False and failed["sources"][0]["entity"] == "Dealer"


def test_warranty_evidence_path_follows_the_traceability_chain(engine):
    ctx = engine.build_warranty_context(claim_id="CLM-G001")
    order = [s["entity"] for s in ctx.evidence_path]
    assert order[:6] == ["MachineInstance", "Installation", "WorkOrder", "Dealer", "WarrantyPolicy", "WarrantyClaim"] and set(order[6:]) == {"Evidence"} and len(order) > 6
    assert ctx.evidence and all(e["entity"] == "Evidence" for e in ctx.evidence) and ctx.traceability["installed_now"]


def test_warranty_missing_data_is_listed_and_never_filled_in(engine):
    g6 = engine.build_warranty_context(claim_id="CLM-G006")
    assert g6.decision.status == c.INSUFFICIENT_DATA and {"technician", "work_order"} <= set(g6.missing) and g6.technician is None and g6.work_order is None
    assert g6.confidence["level"] == "INSUFFICIENT" and g6.decision.recommended_next_action
    g8 = engine.build_warranty_context(claim_id="CLM-G008")
    assert g8.fitment is None and "fitment" in g8.missing and g8.decision.status == c.NOT_ELIGIBLE  # a missing fitment is a definite failure, and still listed as missing
    assert engine.build_warranty_context(claim_id="CLM-NOPE").decision.status == c.NOT_FOUND
    assert engine.build_warranty_context(machine_instance_id="MI-NOPE", part_id="PRT-007").decision.status == c.NOT_FOUND


def test_warranty_by_machine_and_part_and_the_clarification_when_neither_is_given(engine):
    by_part = engine.build_warranty_context(machine_instance_id="MI-G001", part_id="PRT-007")
    assert by_part.decision.status in (c.SUCCESS, c.NOT_ELIGIBLE, c.REQUIRES_REVIEW, c.INSUFFICIENT_DATA) and by_part.installation["machine_instance_id"] == "MI-G001"
    ask = engine.build_warranty_context()
    assert ask.decision.status == c.REQUIRES_CLARIFICATION and ask.decision.facts["options"] == []  # the OEM must name one


def test_the_engine_adds_no_warranty_rule_it_only_maps_the_evaluator_outcome():
    src = (Path(__file__).resolve().parents[1] / "app" / "commerce" / "warranty.py").read_text(encoding="utf-8")
    assert not re.search(r"authori[sz]ed_status|coverage_period_days|timedelta|AUTHORISED\b", src) and "WarrantyContextBuilder" in src


# ── authorization (before any context is built) ──────────────────────────────────────────────────
def test_customer_ownership_of_shipments(engine):
    owner = P("END_CUSTOMER", customer_id="CUS-009")
    other = P("END_CUSTOMER", customer_id="CUS-010")
    assert engine.build_logistics_context(principal=owner, shipment_id="SHP-NET-0001").decision.status == c.SUCCESS
    for call in (dict(shipment_id="SHP-NET-0001"), dict(order_id="ORD-NET-0001")):
        with pytest.raises(AccessDenied):
            engine.build_logistics_context(principal=other, **call)
    # a missing record and somebody else's record are refused identically: the answer never confirms that it exists
    with pytest.raises(AccessDenied) as missing:
        engine.build_logistics_context(principal=other, shipment_id="SHP-NOPE")
    with pytest.raises(AccessDenied) as foreign:
        engine.build_logistics_context(principal=other, shipment_id="SHP-NET-0001")
    assert str(missing.value) == str(foreign.value)
    assert [o["shipment_id"] for o in engine.build_logistics_context(principal=owner).clarification["options"]] == ["SHP-NET-0001", "SHP-NET-0002"]  # 'my shipments' lists only theirs
    assert engine.build_logistics_context(principal=other).shipment["shipment_id"] == "SHP-NET-0003"


def test_customer_ownership_of_machines_and_warranty(engine):
    mine, theirs = P("END_CUSTOMER", customer_id="CUS-001"), P("END_CUSTOMER", customer_id="CUS-004")
    assert engine.build_warranty_context(principal=mine, claim_id="CLM-G001").decision.decision == "ELIGIBLE"
    assert engine.build_warranty_context(principal=mine, machine_instance_id="MI-G001", part_id="PRT-007").installation
    for call in (dict(claim_id="CLM-G001"), dict(machine_instance_id="MI-G001", part_id="PRT-007"), dict(claim_id="CLM-NOPE")):
        with pytest.raises(AccessDenied):
            engine.build_warranty_context(principal=theirs, **call)
    options = engine.build_warranty_context(principal=mine).decision.facts["options"]
    assert {o["machine_instance_id"] for o in options} == {"MI-0001", "MI-0011", "MI-G001", "MI-G005"} and not any(o["machine_instance_id"] == "MI-G002" for o in options)
    no_customer = P("END_CUSTOMER")
    with pytest.raises(AccessDenied):
        engine.build_warranty_context(principal=no_customer, claim_id="CLM-G001")


def test_dealer_visibility(engine):
    d4, d97, d2 = P("DEALER", dealer_id="DLR-004"), P("DEALER", dealer_id="DLR-097"), P("DEALER", dealer_id="DLR-002")
    assert engine.build_logistics_context(principal=d4, shipment_id="SHP-NET-0001").decision.status == c.SUCCESS  # their order
    assert engine.build_logistics_context(principal=d97, shipment_id="SHP-NET-0003").decision.status == c.SUCCESS
    with pytest.raises(AccessDenied):
        engine.build_logistics_context(principal=d97, shipment_id="SHP-NET-0001")
    assert engine.build_logistics_context(principal=d4, order_id="ORD-NET-0001").decision.status == c.REQUIRES_CLARIFICATION  # the order's shipments are theirs
    assert engine.build_warranty_context(principal=d4, claim_id="CLM-G001").decision.decision == "ELIGIBLE"  # they installed and filed it
    with pytest.raises(AccessDenied):
        engine.build_warranty_context(principal=d2, claim_id="CLM-G001")
    assert engine.build_warranty_context(principal=d2, claim_id="CLM-G002").decision.decision == "NOT_ELIGIBLE"
    assert engine.build_logistics_context(principal=d4).decision.status == c.REQUIRES_CLARIFICATION and engine.build_logistics_context(principal=d4).clarification["options"] == []  # no listing for a dealer


def test_oem_sees_everything_and_a_missing_record_is_simply_not_found(engine):
    oem = P("OEM")
    assert engine.build_logistics_context(principal=oem, shipment_id="SHP-NET-0001").decision.status == c.SUCCESS
    assert engine.build_warranty_context(principal=oem, claim_id="CLM-G002").decision.decision == "NOT_ELIGIBLE"
    assert engine.build_logistics_context(principal=oem, shipment_id="SHP-NOPE").decision.status == c.NOT_FOUND
    assert engine.build_warranty_context(principal=oem, claim_id="CLM-NOPE").decision.status == c.NOT_FOUND
    assert engine.build_logistics_context(principal=oem).decision.status == c.REQUIRES_CLARIFICATION


def test_a_dealer_cannot_see_shipments_of_other_dealers_orders_through_an_order_id(engine):
    with pytest.raises(AccessDenied):
        engine.build_logistics_context(principal=P("DEALER", dealer_id="DLR-097"), order_id="ORD-NET-0001")


def user(role, customer_id=None):
    return User(id="U-1", name="n", email="e@x.example", role=role, customer_id=customer_id)


def test_the_account_can_narrow_its_commerce_role_but_never_widen_it():
    assert principal_for(user(Role.END_USER, "CUS-001")).role == CommerceRole.END_CUSTOMER
    assert principal_for(user(Role.END_USER, "CUS-001"), "END_CUSTOMER").customer_id == "CUS-001"
    for wanted, dealer in (("OEM", None), ("DEALER", "DLR-004")):
        with pytest.raises(AccessDenied):
            principal_for(user(Role.END_USER, "CUS-001"), wanted, dealer)
    assert principal_for(user(Role.ORDER_PROCESSOR)).role == CommerceRole.OEM
    dealer = principal_for(user(Role.ORDER_PROCESSOR), "DEALER", "DLR-004")
    assert dealer.role == CommerceRole.DEALER and dealer.dealer_id == "DLR-004"
    for wanted, dealer_id in (("DEALER", None), ("END_CUSTOMER", None), ("OEM", "DLR-004")):
        with pytest.raises(AccessDenied):
            principal_for(user(Role.ORDER_PROCESSOR), wanted, dealer_id)


def test_visibility_by_role_removes_fields_on_a_copy_and_says_what_it_removed(engine):
    cust = engine.build_logistics_context(principal=P("END_CUSTOMER", customer_id="CUS-009"), shipment_id="SHP-NET-0001")
    oem = engine.build_logistics_context(principal=P("OEM"), shipment_id="SHP-NET-0001")
    assert "remediation_flags" not in cust.shipment and "estimated_cost" not in cust.route_legs[0] and cust.visibility["hidden_fields"] == ["route_legs[*].estimated_cost", "shipment.remediation_flags"]
    assert "remediation_flags" in oem.shipment and oem.visibility == {"role": "OEM", "hidden_fields": []}
    again = engine.build_logistics_context(principal=P("OEM"), shipment_id="SHP-NET-0001")
    assert "remediation_flags" in again.shipment  # the shared reader rows were not touched
    w_cust = engine.build_warranty_context(principal=P("END_CUSTOMER", customer_id="CUS-001"), claim_id="CLM-G001")
    assert "name" not in w_cust.technician and "technician.name" in w_cust.visibility["hidden_fields"]
    assert all("name" not in row["installed_by"] for row in w_cust.traceability["installed_now"] if row["installed_by"])
    stock = engine.build_discovery_context("I need a hydraulic pump for my KFT-600.", principal=P("END_CUSTOMER", customer_id="CUS-001"))
    assert all("warehouses" not in a for a in stock.availability) and stock.recommended_part["availability"] == "AVAILABLE"
    assert all("warehouses" in a for a in engine.build_discovery_context("I need a hydraulic pump for my KFT-600.", principal=P("DEALER", dealer_id="DLR-004")).availability)


def test_a_customers_destination_defaults_to_their_own_country(engine):
    ctx = engine.build_discovery_context("hydraulic pump for my KFT-600", principal=P("END_CUSTOMER", customer_id="CUS-001"))
    assert ctx.extracted["destination_country"] == "NL" and ctx.extracted["destination_region"] == "EUROPE"
    assert ctx.ranking[0]["components"]["regional_score"] == 1.0


# ── the agent adapter ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,intent", [("Which hydraulic pump fits my KFT-600?", "DISCOVERY"), ("Where is my shipment?", "LOGISTICS"), ("Is this covered under warranty?", "WARRANTY"),
                                         ("Where is my pump?", "LOGISTICS"), ("I need a hydraulic pump for my KFT-600.", "DISCOVERY")])
def test_intent_examples(text, intent):
    assert select_intent(text).intent == intent


@pytest.mark.parametrize("text", ["hello", "", "pump", "is my pump under warranty and where is it", "where", "my order", "I need help"])
def test_weak_or_mixed_requests_never_force_a_flow(text):
    assert select_intent(text).intent is None
    r = AgenticCommerceService(CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)).handle(ServiceRequest(text=text))
    assert r.decision.status == c.REQUIRES_CLARIFICATION and r.context is None and r.decision.facts["options"] == ["DISCOVERY", "LOGISTICS", "WARRANTY"]


def test_a_supplied_intent_wins_and_an_invalid_one_is_refused(engine):
    assert select_intent("hello", "WARRANTY").intent == "WARRANTY" and select_intent("hello", "WARRANTY").source == "PROVIDED"
    with pytest.raises(ValueError):
        select_intent("hello", "SELL_ME_SOMETHING")


def test_the_service_calls_the_engine_and_returns_its_decision_unchanged(engine):
    svc = AgenticCommerceService(engine)
    r = svc.handle(ServiceRequest(text="Where is my pump?", principal=P("OEM"), shipment_id="SHP-NET-0001"))
    direct = engine.build_logistics_context(principal=P("OEM"), shipment_id="SHP-NET-0001")
    assert r.intent == "LOGISTICS" and r.context.to_dict() == direct.to_dict() and r.decision == direct.decision
    w = svc.handle(ServiceRequest(text="Is this covered under warranty?", principal=P("OEM"), claim_id="CLM-G003"))
    assert w.intent == "WARRANTY" and w.decision.decision == "NOT_ELIGIBLE"
    d = svc.handle(ServiceRequest(text="Which hydraulic pump fits my KFT-600?"))
    assert d.intent == "DISCOVERY" and d.decision.decision == "RECOMMEND"
    json.dumps(d.to_dict())


# ── architecture ─────────────────────────────────────────────────────────────────────────────────
def test_the_commerce_package_has_no_language_model_network_or_ui_dependency():
    banned = re.compile(r"\b(anthropic|openai|gemini|groq|google\.generativeai|genai|requests|httpx|prompt|app\.llm|app\.agent)\b", re.IGNORECASE)
    for path in (Path(__file__).resolve().parents[1] / "app" / "commerce").glob("*.py"):
        assert not banned.search(path.read_text(encoding="utf-8")), path.name


def test_the_engine_reuses_the_existing_readers_and_builders_rather_than_a_second_graph_layer():
    root = Path(__file__).resolve().parents[1] / "app" / "commerce"
    text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    assert not re.search(r"\.read\(|MATCH \(|GraphDatabase|session\.run", text)  # no Cypher, no driver
    assert "ShipmentContextBuilder" in text and "WarrantyContextBuilder" in text and "Exporter" in text
    assert "from app.lifecycle.rules import APPROVED, VERIFIED" in text  # constants are imported, not re-declared


def test_contexts_are_read_only_and_the_files_are_untouched(engine):
    before = {p: p.stat().st_mtime_ns for p in CANON_DIR.rglob("*") if p.is_file()}
    all_contexts(engine)
    assert before == {p: p.stat().st_mtime_ns for p in CANON_DIR.rglob("*") if p.is_file()}


# ── live graph (read-only) ───────────────────────────────────────────────────────────────────────
def _graph():
    if not get_settings().graph_configured:
        return None
    try:
        import socket
        from urllib.parse import urlparse

        from app.graph.client import GraphClient

        host = urlparse(get_settings().neo4j_uri).hostname
        socket.create_connection((host, 7687), timeout=4).close()  # fail fast when the sandbox cannot reach the database
        g = GraphClient(get_settings())
        g.read("RETURN 1 AS x")
        return g
    except Exception:  # noqa: BLE001 - unreachable graph: the live checks skip
        return None


@pytest.fixture(scope="module")
def graph():
    g = _graph()
    if g is None:
        pytest.skip("Neo4j is not reachable")
    yield g
    g.close()


def test_live_the_graph_engine_gives_the_same_contexts_as_the_file_engine(graph):
    files = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)
    live = CommerceContextEngine.from_graph(graph, as_of=AS_OF)
    strip = lambda d: json.loads(json.dumps(d, default=str))  # noqa: E731
    assert strip(live.build_logistics_context(shipment_id="SHP-NET-0001").decision.facts) == strip(files.build_logistics_context(shipment_id="SHP-NET-0001").decision.facts)
    for claim in GOLDEN_WARRANTY:
        assert live.build_warranty_context(claim_id=claim).decision.decision == GOLDEN_WARRANTY[claim]
    a, b = live.build_discovery_context("I need a hydraulic pump for my KFT-600."), files.build_discovery_context("I need a hydraulic pump for my KFT-600.")
    assert a.decision.decision == b.decision.decision and (a.recommended_part or {}).get("part_id") == (b.recommended_part or {}).get("part_id")
    assert {k: [r["code"] for r in v] for k, v in a.rejection_reasons.items()} == {k: [r["code"] for r in v] for k, v in b.rejection_reasons.items()}
