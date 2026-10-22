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






def test_missing_technician_work_order_or_evidence_is_insufficient_data_never_a_guess():
    for override in ({"technician": None}, {"work_order": None}, {"evidence": []},
                     {"installation": {**facts().installation, "technician_id": None}}, {"installation": {**facts().installation, "work_order_id": None}}):
        d = evaluate(facts(**override))
        assert d.outcome == INSUFFICIENT_DATA and d.factor("INSTALLATION_EVIDENCED").status == rules.UNKNOWN, override
    no_install = evaluate(facts(installation=None))
    assert no_install.outcome == INSUFFICIENT_DATA and no_install.factor("PART_INSTALLED").status == rules.UNKNOWN




















# installation validation, replacement chronology, current component
def _install(**kw):
    return {**facts().installation, **kw}
















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








































# ── Part 3: the live graph (read-only) ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def graph():
    from app.graph.client import GraphClient

    g = GraphClient(get_settings())
    yield g
    g.close()


LIFECYCLE = ["machine_instances", "technicians", "work_orders", "installations", "replacements", "warranty_policies", "warranty_claims", "evidence", "scenarios_warranty"]












