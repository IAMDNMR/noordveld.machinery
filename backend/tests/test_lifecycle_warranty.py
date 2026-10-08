"""Phase 3: machine lifecycle, installation and replacement history, warranty evaluation, traceability.

Part 1 is the rules on small in-memory facts (no files, no database). Part 2 reads the canonical files: golden scenarios, history, context, traceability, data quality.
Part 3 reads the live graph (read-only): idempotency, the quality checks, files == graph, and the integrity checksum.
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.canonical import models as m
from app.canonical.engine import Engine
from app.canonical.io import CANON_DIR
from app.core.config import get_settings
from app.lifecycle import audit, rules
from app.lifecycle.context import WarrantyContextBuilder
from app.lifecycle.readers import FileReader
from app.lifecycle.rules import (
    ELIGIBLE,
    INSUFFICIENT_DATA,
    NOT_ELIGIBLE,
    REQUIRES_REVIEW,
    Facts,
    evaluate,
)

live = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
GOLDEN = json.loads((CANON_DIR / "reference" / "lifecycle_scenarios.json").read_text(encoding="utf-8"))
EXPECTED = {s["claim_id"]: s["expected_outcome"] for s in GOLDEN["scenarios"]}
ALL_CONDITIONS = list(rules.CONDITIONS)


# ── Part 1: the rules on in-memory facts ─────────────────────────────────────────────────────────
def facts(**override) -> Facts:
    """A complete, evidenced, eligible case; each test breaks exactly one thing."""
    evidence = [{"evidence_id": f"EV-{n}", "evidence_type": t, "entity_type": et, "entity_id": eid, "created_at": "2026-04-12"}
                for n, (t, et, eid) in enumerate((("INSTALLATION_RECORD", "INSTALLATION", "INS-1"), ("WORK_ORDER", "WORK_ORDER", "WO-1"), ("DEALER_RECORD", "DEALER", "DLR-1"),
                                                  ("TECHNICIAN_RECORD", "TECHNICIAN", "TEC-1"), ("PART_RECORD", "PART", "PRT-1")))]
    base = {
        "instance": {"machine_instance_id": "MI-1", "machine_id": "MCH-1", "model_year": 2025},
        "installation": {"installation_id": "INS-1", "machine_instance_id": "MI-1", "part_id": "PRT-1", "dealer_id": "DLR-1", "technician_id": "TEC-1", "work_order_id": "WO-1",
                      "installation_date": "2026-04-12", "removal_date": None, "status": "CURRENT"},
        "part": {"part_id": "PRT-1", "status": "VERIFIED"}, "dealer": {"dealer_id": "DLR-1", "authorized_status": "AUTHORISED", "region": "EUROPE"},
        "technician": {"technician_id": "TEC-1", "dealer_id": "DLR-1"}, "work_order": {"work_order_id": "WO-1", "machine_instance_id": "MI-1"},
        "fitment": {"fitment_id": "F-1", "approval_status": "APPROVED", "fitment_rule": "CONFIRMED"}, "approved_sources": [{"approved_source_id": "AS-1", "approval_status": "APPROVED"}],
        "policies": [{"warranty_policy_id": "WP-1", "status": "ACTIVE", "region": None, "coverage_period_days": 365, "start_rule": "INSTALLATION_DATE", "coverage_conditions": ALL_CONDITIONS}],
        "claim": {"claim_id": "CLM-1", "machine_instance_id": "MI-1", "part_id": "PRT-1", "claim_date": "2026-09-22", "failure_date": "2026-09-20"},
        "other_claims": [], "replacements": [], "evidence": evidence, "reference_date": date(2026, 9, 20)}
    base.update(override)
    return Facts(**base)


def test_a_complete_approved_authorised_evidenced_installation_inside_the_period_is_eligible():
    d = evaluate(facts())
    assert d.outcome == ELIGIBLE and (d.coverage_start, d.coverage_end) == ("2026-04-12", "2027-04-12")
    assert all(f.status == rules.PASS for f in d.factors) and {f.code for f in d.factors} >= set(ALL_CONDITIONS)


def test_the_same_facts_always_give_the_same_decision():
    f = facts()
    assert evaluate(f) == evaluate(copy.deepcopy(f))


def test_an_expired_period_is_not_eligible_and_the_boundary_days_are_exact():
    assert evaluate(facts(reference_date=date(2027, 4, 12))).outcome == ELIGIBLE  # the last covered day
    d = evaluate(facts(reference_date=date(2027, 4, 13)))
    assert d.outcome == NOT_ELIGIBLE and d.factor("COVERAGE_PERIOD_ACTIVE").status == rules.FAIL
    assert evaluate(facts(reference_date=date(2026, 4, 11))).outcome == NOT_ELIGIBLE  # a failure before the part was fitted cannot be covered


def test_an_unauthorised_installer_is_not_eligible_whatever_else_holds():
    for status in ("SERVICE_PARTNER", "INDEPENDENT", None):
        d = evaluate(facts(dealer={"dealer_id": "DLR-1", "authorized_status": status, "region": "EUROPE"}))
        assert d.outcome == NOT_ELIGIBLE and d.factor("AUTHORISED_DEALER_INSTALL").status == rules.FAIL


def test_a_part_that_is_not_a_verified_approved_part_is_not_eligible():
    assert evaluate(facts(part={"part_id": "PRT-1", "status": "UNVERIFIED"})).outcome == NOT_ELIGIBLE
    assert evaluate(facts(part={"part_id": "PRT-1", "status": "AMBIGUOUS"})).outcome == NOT_ELIGIBLE
    assert evaluate(facts(approved_sources=[])).outcome == NOT_ELIGIBLE
    assert evaluate(facts(approved_sources=[{"approved_source_id": "AS-1", "approval_status": "REVOKED"}])).outcome == NOT_ELIGIBLE


def test_a_part_not_approved_for_the_machine_model_is_not_eligible_even_though_it_was_installed():
    for fit in (None, {"fitment_id": "F-1", "approval_status": "REJECTED"}, {"fitment_id": "F-1", "approval_status": "UNDER_REVIEW"}):
        d = evaluate(facts(fitment=fit))
        assert d.outcome == NOT_ELIGIBLE and d.factor("APPROVED_MACHINE_FITMENT").status == rules.FAIL
        assert d.factor("PART_INSTALLED").status == rules.PASS  # the installation is real; FITS is approval, HAS_INSTALLATION is fact


def test_missing_technician_work_order_or_evidence_is_insufficient_data_never_a_guess():
    for override in ({"technician": None}, {"work_order": None}, {"evidence": []},
                     {"installation": {**facts().installation, "technician_id": None}}, {"installation": {**facts().installation, "work_order_id": None}}):
        d = evaluate(facts(**override))
        assert d.outcome == INSUFFICIENT_DATA and d.factor("INSTALLATION_EVIDENCED").status == rules.UNKNOWN, override
    no_install = evaluate(facts(installation=None))
    assert no_install.outcome == INSUFFICIENT_DATA and no_install.factor("PART_INSTALLED").status == rules.UNKNOWN


def test_a_definite_failure_outranks_missing_data_and_missing_data_outranks_review():
    d = evaluate(facts(technician=None, dealer={"dealer_id": "DLR-1", "authorized_status": "INDEPENDENT"}))
    assert d.outcome == NOT_ELIGIBLE
    prior = [{"claim_id": "CLM-0", "claim_date": "2026-06-01"}]
    assert evaluate(facts(technician=None, other_claims=prior)).outcome == INSUFFICIENT_DATA
    assert evaluate(facts(other_claims=prior)).outcome == REQUIRES_REVIEW


def test_a_previous_claim_sends_the_claim_to_review_but_a_later_one_does_not():
    assert evaluate(facts(other_claims=[{"claim_id": "CLM-0", "claim_date": "2026-06-01"}])).outcome == REQUIRES_REVIEW
    assert evaluate(facts(other_claims=[{"claim_id": "CLM-2", "claim_date": "2026-10-30"}])).outcome == ELIGIBLE


def test_repeated_replacement_is_review_but_the_replacement_that_made_this_installation_is_not():
    own = {"replacement_id": "REP-2", "installed_part_id": "PRT-1", "new_installation_id": "INS-1", "replacement_date": "2026-04-12"}
    earlier = {"replacement_id": "REP-1", "installed_part_id": "PRT-1", "new_installation_id": "INS-0", "replacement_date": "2026-02-01"}
    assert evaluate(facts(replacements=[own])).outcome == ELIGIBLE
    d = evaluate(facts(replacements=[earlier, own]))
    assert d.outcome == REQUIRES_REVIEW and d.factor("NO_PRIOR_REPLACEMENT").records == ["REP-1"]


def test_conditions_are_data_a_policy_without_a_condition_does_not_enforce_it():
    f = facts(dealer={"dealer_id": "DLR-1", "authorized_status": "INDEPENDENT"})
    assert evaluate(f).outcome == NOT_ELIGIBLE
    relaxed = [{**f.policies[0], "coverage_conditions": [c for c in ALL_CONDITIONS if c != "AUTHORISED_DEALER_INSTALL"]}]
    assert evaluate(facts(dealer=f.dealer, policies=relaxed)).outcome == ELIGIBLE
    assert evaluate(facts(policies=[{**f.policies[0], "coverage_conditions": []}], dealer=f.dealer)).outcome == ELIGIBLE  # only the base facts apply


def test_policy_selection_no_policy_inactive_ambiguous_and_regional():
    p = facts().policies[0]
    assert evaluate(facts(policies=[])).outcome == INSUFFICIENT_DATA
    assert evaluate(facts(policies=[{**p, "status": "RETIRED"}])).outcome == INSUFFICIENT_DATA
    assert evaluate(facts(policies=[p, {**p, "warranty_policy_id": "WP-2"}])).outcome == REQUIRES_REVIEW  # two equally specific policies: a person decides
    assert evaluate(facts(policies=[p, {**p, "warranty_policy_id": "WP-2", "region": "EUROPE", "coverage_period_days": 730}])).coverage_end == "2028-04-11"  # the regional policy wins
    assert evaluate(facts(policies=[{**p, "region": "ASIA"}])).outcome == INSUFFICIENT_DATA  # a policy for another region does not apply


def test_start_rules_that_need_a_date_that_is_not_recorded_give_insufficient_data():
    p = facts().policies[0]
    for rule in ("DELIVERY_DATE", "PURCHASE_DATE"):
        d = evaluate(facts(policies=[{**p, "start_rule": rule}]))
        assert d.outcome == INSUFFICIENT_DATA and d.coverage_start is None


def test_a_policy_naming_an_unknown_condition_cannot_be_judged():
    p = facts().policies[0]
    assert evaluate(facts(policies=[{**p, "coverage_conditions": [*ALL_CONDITIONS, "MADE_UP"]}])).outcome == INSUFFICIENT_DATA


def test_a_claim_for_another_part_or_machine_is_not_the_installed_part():
    d = evaluate(facts(claim={"claim_id": "C", "machine_instance_id": "MI-1", "part_id": "PRT-9", "claim_date": "2026-09-22", "failure_date": "2026-09-20"}))
    assert d.outcome == NOT_ELIGIBLE and d.factor("PART_INSTALLED").status == rules.FAIL


def test_claim_status_is_derived_from_the_outcome_and_unresolved_outcomes_stay_with_a_reviewer():
    assert rules.claim_status_for(ELIGIBLE) == ("APPROVED", "APPROVED")
    assert rules.claim_status_for(NOT_ELIGIBLE) == ("REJECTED", "REJECTED")
    assert rules.claim_status_for(REQUIRES_REVIEW) == ("UNDER_REVIEW", None) and rules.claim_status_for(INSUFFICIENT_DATA) == ("UNDER_REVIEW", None)


# installation validation, replacement chronology, current component
def _install(**kw):
    return {**facts().installation, **kw}


def test_a_fully_referenced_installation_is_valid():
    f = facts()
    assert rules.validate_installation(f.installation, f.instance, f.part, f.dealer, f.technician, f.work_order) == ("VALID", [])


def test_missing_references_make_an_installation_incomplete_and_say_why():
    f = facts()
    status, issues = rules.validate_installation(_install(technician_id=None, work_order_id=None), f.instance, f.part, f.dealer, None, None)
    assert status == "INCOMPLETE" and issues == ["technician_missing", "work_order_missing"]
    assert rules.validate_installation(f.installation, f.instance, None, None, f.technician, f.work_order)[1] == ["part_missing", "dealer_missing"]
    assert rules.validate_installation(f.installation, None, f.part, f.dealer, f.technician, f.work_order)[1] == ["machine_instance_missing"]


def test_installation_dates_and_cross_references_are_checked():
    f = facts()
    check = lambda inst, **kw: rules.validate_installation(inst, kw.get("instance", f.instance), f.part, f.dealer, kw.get("tech", f.technician), kw.get("wo", f.work_order),
                                                           kw.get("today"))[1]
    assert "removal_before_installation" in check(_install(removal_date="2026-01-01"))
    assert "installed_before_machine_existed" in check(_install(installation_date="2020-01-01"))
    assert "installation_date_in_future" in check(_install(), today=date(2026, 1, 1))
    assert "installation_date_invalid" in check(_install(installation_date="not-a-date"))
    assert "technician_works_for_another_dealer" in check(_install(), tech={"technician_id": "TEC-1", "dealer_id": "DLR-9"})
    assert "work_order_for_another_machine" in check(_install(), wo={"work_order_id": "WO-1", "machine_instance_id": "MI-9"})


def test_replacement_chronology():
    removed = {"installation_id": "A", "machine_instance_id": "MI-1", "installation_date": "2026-01-01", "removal_date": "2026-03-01"}
    new = {"installation_id": "B", "machine_instance_id": "MI-1", "installation_date": "2026-03-01"}
    rep = {"replacement_date": "2026-03-01"}
    assert rules.replacement_chronology_errors(rep, removed, new) == []
    assert "new_installation_before_replacement" in rules.replacement_chronology_errors({"replacement_date": "2026-03-05"}, removed, new)
    assert "replacement_not_after_removed_installation" in rules.replacement_chronology_errors({"replacement_date": "2026-01-01"}, removed, {**new, "installation_date": "2026-01-01"})
    assert "removed_installation_has_no_removal_date" in rules.replacement_chronology_errors(rep, {**removed, "removal_date": None}, new)
    assert "removal_after_replacement" in rules.replacement_chronology_errors({"replacement_date": "2026-02-01"}, removed, new)
    assert "installations_on_different_machines" in rules.replacement_chronology_errors(rep, removed, {**new, "machine_instance_id": "MI-2"})
    assert rules.replacement_chronology_errors(rep, None, new) == ["installation_missing"]


def test_the_current_component_has_no_removal_date_and_is_active():
    a = {"installation_id": "A", "installation_date": "2026-01-01", "removal_date": "2026-03-01", "status": "REMOVED"}
    b = {"installation_id": "B", "installation_date": "2026-03-01", "removal_date": None, "status": "CURRENT"}
    assert rules.current_installations([a, b]) == [b] and rules.current_installations([a]) == []


def test_models_reject_unknown_conditions_and_bad_installation_state():
    base = {"warranty_policy_id": "WP-X", "part_id": "PRT-1", "coverage_type": "STANDARD", "coverage_period_days": 30, "start_rule": "INSTALLATION_DATE", "region": None, "status": "ACTIVE",
                "data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO", "source_record_id": "x"}
    assert m.WarrantyPolicy.model_validate({**base, "coverage_conditions": ["APPROVED_PART"]})
    with pytest.raises(ValidationError):
        m.WarrantyPolicy.model_validate({**base, "coverage_conditions": ["NOT_A_CONDITION"]})
    with pytest.raises(ValidationError):
        m.WarrantyPolicy.model_validate({**base, "start_rule": "WHENEVER", "coverage_conditions": []})


def test_the_lifecycle_package_has_no_language_model_network_or_ui_dependency():
    banned = re.compile(r"\b(anthropic|openai|google\.generativeai|genai|requests|httpx|fastapi|prompt)\b", re.IGNORECASE)
    for path in (Path(__file__).resolve().parents[1] / "app" / "lifecycle").glob("*.py"):
        assert not banned.search(path.read_text(encoding="utf-8")), path.name


# ── Part 2: the canonical files ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def files() -> FileReader:
    return FileReader(CANON_DIR)


@pytest.fixture(scope="module")
def builder(files) -> WarrantyContextBuilder:
    return WarrantyContextBuilder(files, date(2026, 10, 7))


def test_every_golden_scenario_gets_its_expected_outcome(builder):
    assert len(EXPECTED) >= 8 and set(EXPECTED.values()) == {ELIGIBLE, NOT_ELIGIBLE, REQUIRES_REVIEW, INSUFFICIENT_DATA}
    for claim_id, expected in EXPECTED.items():
        assert builder.for_claim(claim_id).outcome == expected, claim_id


def test_golden_claims_are_submitted_the_evaluator_gives_the_verdict_and_nothing_is_a_fake_approval(files):
    for claim_id in EXPECTED:
        c = files.claim(claim_id)
        if claim_id == "CLM-G004-1":
            continue
        assert c["status"] == "SUBMITTED" and c["decision"] is None and c["decision_reason"] is None, claim_id


def test_decided_claims_carry_exactly_what_the_rules_derive(files, builder):
    decided = [c for c in files._rows("warranty_claims") if c["status"] in ("APPROVED", "REJECTED")]
    assert len(decided) >= 4
    for c in decided:
        ctx = builder.for_claim(c["claim_id"])
        assert rules.claim_status_for(ctx.outcome) == (c["status"], c["decision"]), c["claim_id"]
        assert c["decision_reason"], "a decision states its reason"
    for c in files._rows("warranty_claims"):
        if c["status"] == "UNDER_REVIEW":
            assert c["decision"] is None
            assert builder.for_claim(c["claim_id"]).outcome in (REQUIRES_REVIEW, INSUFFICIENT_DATA)


def test_the_eligible_scenario_explains_itself_with_evidence_for_every_fact(builder):
    ctx = builder.for_claim("CLM-G001")
    d = ctx.to_dict()
    assert set(d) >= {"machine", "current_part", "installation", "dealer", "technician", "work_order", "fitment", "approved_source", "warranty_policy", "coverage_start", "coverage_end",
                      "replacement_history", "prior_claims", "evidence", "decision_factors", "provenance"}
    assert (d["coverage_start"], d["coverage_end"]) == ("2026-04-12", "2027-04-12") and ctx.reference_date == "2026-09-20" and ctx.missing == []
    assert d["dealer"]["authorized_status"] == "AUTHORISED" and d["technician"]["specialization"] == "Hydraulics" and d["current_part"]["part_number"] == "NVM-1060-HY"
    assert {e["evidence_type"] for e in d["evidence"]} >= {"INSTALLATION_RECORD", "WORK_ORDER", "DEALER_RECORD", "TECHNICIAN_RECORD", "PART_RECORD", "SERVICE_REPORT"}
    codes = {f["code"] for f in d["decision_factors"]}
    assert set(ALL_CONDITIONS) <= codes and all(f["status"] == "PASS" for f in d["decision_factors"])
    records = d["provenance"]["records"]  # each record keeps its OWN provenance: the catalogue part is source-derived, the lifecycle records are synthetic
    assert records and all(r["data_status"] for r in records) and {"SYNTHETIC_DEMO"} <= {r["data_status"] for r in records}
    assert d["installation"]["data_status"] == "SYNTHETIC_DEMO" and d["current_part"]["data_status"] != "SYNTHETIC_DEMO"


def test_the_insufficient_scenario_names_what_is_missing_and_invents_nothing(builder):
    ctx = builder.for_claim("CLM-G006")
    assert ctx.outcome == INSUFFICIENT_DATA and ctx.technician is None and ctx.work_order is None and {"technician", "work_order"} <= set(ctx.missing)
    assert ctx.installation["validation_status"] == "INCOMPLETE" and ctx.installation["validation_issues"] == ["technician_missing", "work_order_missing"]
    assert ctx.installation["technician_id"] is None and ctx.installation["work_order_id"] is None


def test_the_review_scenarios_point_at_the_records_that_trigger_review(builder):
    prior = builder.for_claim("CLM-G004-2")
    assert [c["claim_id"] for c in prior.prior_claims] == ["CLM-G004-1"]
    assert next(f for f in prior.decision_factors if f["code"] == "NO_PRIOR_CLAIM")["records"] == ["CLM-G004-1"]
    multi = builder.for_claim("CLM-G005")
    assert [r["replacement_id"] for r in multi.replacement_history] == ["REP-G005-1", "REP-G005-2"]
    assert next(f for f in multi.decision_factors if f["code"] == "NO_PRIOR_REPLACEMENT")["records"] == ["REP-G005-1"]


def test_the_expired_and_unauthorised_scenarios_name_the_failed_condition(builder):
    expired = builder.for_claim("CLM-G003")
    assert next(f for f in expired.decision_factors if f["status"] == "FAIL")["code"] == "COVERAGE_PERIOD_ACTIVE" and expired.coverage_end == "2026-02-10"
    unauthorised = builder.for_claim("CLM-G002")
    assert [f["code"] for f in unauthorised.decision_factors if f["status"] == "FAIL"] == ["AUTHORISED_DEALER_INSTALL"]
    assert unauthorised.dealer["authorized_status"] == "SERVICE_PARTNER"


def test_installation_is_not_fitment_a_part_can_be_installed_without_being_approved(files):
    g8 = files.installation("INS-G008-A")
    assert g8 and files.fitment("MCH-009", g8["part_id"]) is None  # fitted on the machine, never approved for the model
    assert files.fitment("MCH-009", "PRT-007")["approval_status"] == "APPROVED"  # approved, and (G001) also fitted: two separate facts


def test_one_work_order_can_record_several_component_events(files):
    assert files.work_order_events("WO-G001") == ["INS-G001-A", "INS-G001-B"]
    assert files.work_order_events("WO-G005-2") == ["INS-G005-B", "REP-G005-1"]  # an installation and the replacement it completes


def test_authorisation_comes_from_the_dealer_status_and_no_second_field_exists():
    assert "authorized_status" in m.Dealer.model_fields
    assert not [f for fields in (m.Dealer.model_fields, m.Technician.model_fields, m.InstallationEvent.model_fields, m.WorkOrder.model_fields)
                for f in fields if re.search(r"authori[sz]ed_?(dealer|installer|flag)|is_authori", f)]


def test_technician_specialisations_and_certifications(files):
    allowed = {"Hydraulics", "Powertrain", "Electrical", "Transmission"}
    techs = files._rows("technicians")
    assert {t["specialization"] for t in techs} <= allowed and len({t["specialization"] for t in techs}) >= 3
    assert all(t["certification"] and t["dealer_id"] and files.dealer(t["dealer_id"]) for t in techs)


def test_every_installation_validation_is_recomputed_from_the_rules(files):
    incomplete = []
    for i in files._rows("installations"):
        status, issues = rules.validate_installation(i, files.instance(i["machine_instance_id"]), files.part(i["part_id"]), files.dealer(i["dealer_id"]),
                                                     files.technician(i["technician_id"]) if i["technician_id"] else None, files.work_order(i["work_order_id"]) if i["work_order_id"] else None)
        assert (i["validation_status"], i["validation_issues"]) == (status, issues), i["installation_id"]
        if status == "INCOMPLETE":
            incomplete.append(i["installation_id"])
    assert incomplete == ["INS-G006-A"]


def test_replacement_chronology_holds_for_every_replacement_and_history_is_kept(files):
    for mid in files.instance_ids():
        by_id = {i["installation_id"]: i for i in files.installations(mid)}
        for r in files.replacements(mid):
            assert rules.replacement_chronology_errors(r, by_id[r["removed_installation_id"]], by_id[r["new_installation_id"]]) == [], r["replacement_id"]
            assert by_id[r["removed_installation_id"]]["status"] == "REMOVED"  # the replaced part stays on record
    chain = {i["installation_id"]: i["status"] for i in files.installations("MI-G005")}
    assert chain == {"INS-G005-A": "REMOVED", "INS-G005-B": "REMOVED", "INS-G005-C": "CURRENT"}


def test_traceability_answers_what_is_installed_who_fitted_it_what_came_before_and_the_linked_claim(builder):
    t = builder.traceability("MI-G005", "PRT-007")
    assert [r["installation_id"] for r in t["installed_now"]] == ["INS-G005-C"] and [r["installation_id"] for r in t["installed_before"]] == ["INS-G005-A", "INS-G005-B"]
    now = t["installed_now"][0]
    assert now["installed_by"]["name"] and now["installed_at"]["authorized_status"] == "AUTHORISED" and now["claims"] == ["CLM-G005"] and now["replaces_installation"] == "INS-G005-B"
    before = {r["installation_id"]: r for r in t["installed_before"]}
    assert before["INS-G005-A"]["replaced_on"] == "2026-02-10" and before["INS-G005-A"]["replaced_by_event"] == "REP-G005-1" and before["INS-G005-B"]["replaced_on"] == "2026-05-20"
    assert [c["claim_id"] for c in t["claims"]] == ["CLM-G005"]


def test_traceability_of_an_incomplete_installation_shows_the_gap_not_a_made_up_technician(builder):
    row = builder.traceability("MI-G006")["installed_now"][0]
    assert row["installed_by"] is None and row["work_order_id"] is None and row["validation_status"] == "INCOMPLETE"


def test_part_lifecycle_stages_follow_the_records(builder):
    stages = [s["stage"] for s in builder.part_lifecycle("INS-G001-A")["stages"]]
    assert stages == ["INSTALLED", "SERVICED", "INSPECTED"] and builder.part_lifecycle("INS-G001-A")["state"] == "CURRENT"
    old = builder.part_lifecycle("INS-G005-A")
    assert [s["stage"] for s in old["stages"]] == ["INSTALLED", "REMOVED", "REPLACED"] and old["state"] == "HISTORICAL"
    assert builder.part_lifecycle("INS-NOPE")["stages"] == []


def test_files_have_no_duplicate_ids_orphans_or_duplicate_relationships(files):
    for name, key in (("machine_instances", "machine_instance_id"), ("technicians", "technician_id"), ("work_orders", "work_order_id"), ("installations", "installation_id"),
                      ("replacements", "replacement_id"), ("warranty_claims", "claim_id"), ("evidence", "evidence_id"), ("warranty_policies", "warranty_policy_id")):
        ids = [r[key] for r in files._rows(name)]
        assert len(ids) == len(set(ids)), name
    for i in files._rows("installations"):
        assert files.instance(i["machine_instance_id"]) and files.part(i["part_id"]) and files.dealer(i["dealer_id"])
    for e in files._rows("evidence"):
        lookup = {"INSTALLATION": files.installation, "WORK_ORDER": files.work_order, "WARRANTY_CLAIM": files.claim, "TECHNICIAN": files.technician, "DEALER": files.dealer,
                  "PART": files.part}[e["entity_type"]]
        assert lookup(e["entity_id"]), e["evidence_id"]
    rels = Counter((i["machine_instance_id"], i["installation_id"]) for i in files._rows("installations"))
    assert max(rels.values()) == 1


def test_policies_state_their_conditions_as_data_from_the_known_catalogue(files):
    policies = files._rows("warranty_policies")
    assert len(policies) == 100
    for p in policies:
        assert set(p["coverage_conditions"]) == set(ALL_CONDITIONS) and p["start_rule"] == "INSTALLATION_DATE" and p["coverage_period_days"] in (182, 365)


def test_every_lifecycle_record_carries_provenance(files):
    for name in ("machine_instances", "technicians", "work_orders", "installations", "replacements", "warranty_claims", "evidence", "warranty_policies"):
        for r in files._rows(name):
            assert r["data_status"] == "SYNTHETIC_DEMO" and r["source_type"] == "SYNTHETIC_DEMO" and r["source_record_id"], (name, r.get("installation_id"))


def test_scenario_records_exist_for_every_golden_warranty_scenario(files):
    ids = {r["scenario_id"] for r in files._rows("scenarios_warranty")}
    assert {f"SCN-{s['scenario_id']}" for s in GOLDEN["scenarios"]} <= ids


# ── Part 3: the live graph (read-only) ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def graph():
    from app.graph.client import GraphClient

    g = GraphClient(get_settings())
    yield g
    g.close()


LIFECYCLE = ["machine_instances", "technicians", "work_orders", "installations", "replacements", "warranty_policies", "warranty_claims", "evidence", "scenarios_warranty"]


@live
def test_live_a_second_ingestion_would_write_nothing():
    from app.canonical.store import Neo4jStore

    store = Neo4jStore(get_settings())
    try:
        report = Engine(store, CANON_DIR).run(LIFECYCLE, dry_run=True)
    finally:
        store.close()
    t = report["totals"]
    assert t["records_invalid"] == 0 and t["records_drift"] == 0
    assert (t["nodes_to_create"], t["nodes_to_update"], t["relationships_to_create"], t["relationships_to_update"]) == (0, 0, 0, 0), t


@live
def test_live_graph_passes_every_data_quality_check(graph):
    report = audit.quality(graph)
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]


@live
def test_live_golden_scenarios_evaluate_the_same_from_the_graph_as_from_the_files(graph, builder):
    from app.lifecycle.readers import GraphReader

    db = WarrantyContextBuilder(GraphReader(graph), date(2026, 10, 7))

    def essentials(c):
        return (c.outcome, c.coverage_start, c.coverage_end, [(f["code"], f["status"]) for f in c.decision_factors], sorted(e["evidence_id"] for e in c.evidence), sorted(c.missing),
                [r["replacement_id"] for r in c.replacement_history], [p["claim_id"] for p in c.prior_claims])

    for claim_id, expected in EXPECTED.items():
        from_graph = db.for_claim(claim_id)
        assert from_graph.outcome == expected and essentials(from_graph) == essentials(builder.for_claim(claim_id)), claim_id


@live
def test_live_traceability_from_the_graph_equals_the_files(graph, builder):
    from app.lifecycle.readers import GraphReader

    db = WarrantyContextBuilder(GraphReader(graph))
    for mid in ("MI-G001", "MI-G005", "MI-G006", "MI-0001"):
        assert db.traceability(mid) == builder.traceability(mid), mid


@live
def test_live_the_superseded_relationship_names_are_gone_and_the_new_ones_carry_the_history(graph):
    old = graph.read("MATCH ()-[r]->() WHERE type(r) IN ['OF_PART','INSTALLED_BY_DEALER','INSTALLED_BY_TECHNICIAN','UNDER_WORK_ORDER'] RETURN count(r) AS n")[0]["n"]
    assert old == 0
    counts = audit.counts(graph)["relationships"]
    assert counts["HAS_INSTALLATION"] == counts["INSTALLED_PART"] == counts["PERFORMED_AT"] == 35 and counts["PERFORMED_BY"] == 34 and counts["RECORDED_IN"] == 40


@live
def test_live_protected_data_is_untouched():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eu_foundation"))
    from audit_before import source_checksum

    baseline = json.loads((Path(__file__).resolve().parents[1] / "data" / "eu_foundation" / "audit_before.json").read_text(encoding="utf-8"))["source_checksum"]
    assert source_checksum() == baseline
