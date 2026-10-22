"""Canonical models and the ingestion engine, on an isolated in-memory world: no Neo4j, deterministic.

The MemoryStore has the same contract as the Neo4j store, so planning (create / update / unchanged / verify), idempotency, dry-run and the protection
policy are proven here exactly as they behave against the real graph.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.canonical import models as m
from app.canonical.engine import Engine, guard
from app.canonical.integrity import dataset_checksum, graph_fingerprint
from app.canonical.io import DatasetFileError, dump_rows, load_rows
from app.canonical.registry import BY_NAME, SPECS, order
from app.canonical.store import MemoryStore

SYN = {"data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO"}
CLOCK = iter(f"2026-10-07T10:{n // 60:02d}:{n % 60:02d}Z" for n in range(100000))


def clock() -> str:
    return next(CLOCK)


def seeded() -> MemoryStore:
    s = MemoryStore()
    s.seed_node("Machine", "machine_id", {"machine_id": "MCH-1", "model_code": "X-1", "machine_type": "Loader", "name": "X-1 Loader", "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"})
    s.seed_node("MachineVariant", "variant_id", {"variant_id": "VAR-1", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    s.seed_node("Customer", "customer_id", {"customer_id": "CUS-1", "name": "Customer One (demo)", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    s.seed_node("ShipTo", "shipto_id", {"shipto_id": "SHT-1", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"})
    s.seed_node("Dealer", "dealer_id", {"dealer_id": "DLR-1", "name": "Dealer One (demo)", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"})
    s.seed_node("Part", "part_id", {"part_id": "PRT-1", "part_number": "P-1", "name": "Hose", "brand": "Noordveld", "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"})
    s.seed_node("PartCatalogProfile", "profile_id", {"profile_id": "PCP-PRT-1", "part_status": "VERIFIED", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    s.seed_node("Category", "category_id", {"category_id": "CAT-1", "name": "Hydraulics", "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"})
    return s


TECH = {"technician_id": "TEC-1", "dealer_id": "DLR-1", "name": "Jan (demo)", "certification": "L2", "specialization": "Hydraulics", "status": "ACTIVE", **SYN}
INSTANCE = {"machine_instance_id": "MI-1", "machine_id": "MCH-1", "variant_id": "VAR-1", "serial_number": "X-1-00001", "model_year": 2024, "owner_id": "CUS-1",
            "location_id": "SHT-1", "status": "IN_SERVICE", **SYN}
WO = {"work_order_id": "WO-1", "machine_instance_id": "MI-1", "dealer_id": "DLR-1", "technician_id": "TEC-1", "service_date": "2025-02-01", "service_type": "INSTALLATION",
      "status": "COMPLETED", "reason": None, **SYN}
INSTALL = {"installation_id": "INS-1", "machine_instance_id": "MI-1", "part_id": "PRT-1", "part_serial_number": "SN-1", "dealer_id": "DLR-1", "technician_id": "TEC-1",
           "work_order_id": "WO-1", "installation_date": "2025-02-01", "removal_date": None, "status": "CURRENT", **SYN}
POLICY = {"warranty_policy_id": "WP-PRT-1", "part_id": "PRT-1", "coverage_type": "STANDARD", "coverage_period_days": 365, "coverage_conditions": ["APPROVED_PART"],
          "start_rule": "INSTALLATION_DATE", "region": None, "status": "ACTIVE", **SYN}


def put(root: Path, name: str, rows: list[dict]) -> None:
    dump_rows(BY_NAME[name], rows, root, "2026-10-07T00:00:00Z")


def world(tmp_path: Path, **extra) -> tuple[Engine, MemoryStore, Path]:
    put(tmp_path, "technicians", [TECH])
    put(tmp_path, "machine_instances", [INSTANCE])
    put(tmp_path, "work_orders", [WO])
    put(tmp_path, "installations", [INSTALL])
    put(tmp_path, "warranty_policies", [POLICY])
    store = seeded()
    return Engine(store, tmp_path, clock), store, tmp_path


NEW = ["technicians", "machine_instances", "work_orders", "installations", "warranty_policies"]


# ── models ───────────────────────────────────────────────────────────────────────────────────────














# ── loading ──────────────────────────────────────────────────────────────────────────────────────




# ── ingestion ────────────────────────────────────────────────────────────────────────────────────




def test_a_second_run_is_idempotent_no_writes_no_duplicates_same_fingerprint(tmp_path):
    engine, store, root = world(tmp_path)
    engine.run(NEW, dry_run=False)
    nodes, rels, fingerprint = len(store.nodes), len(store.rels), graph_fingerprint(store)
    writes = store.writes
    second = Engine(store, root, clock).run(NEW, dry_run=False)
    assert second["totals"]["records_created"] == 0 and second["totals"]["records_updated"] == 0
    assert second["totals"]["nodes_to_create"] == 0 and second["totals"]["nodes_to_update"] == 0 and second["totals"]["relationships_to_create"] == 0
    assert (len(store.nodes), len(store.rels), store.writes) == (nodes, rels, writes)
    assert graph_fingerprint(store) == fingerprint
    third = Engine(store, root, clock).run(NEW, dry_run=False)
    assert graph_fingerprint(store) == fingerprint and third["totals"]["records_unchanged"] == 5
















# ── the write policy ─────────────────────────────────────────────────────────────────────────────
def test_protected_and_app_written_records_are_never_modified():
    assert guard({"data_status": "SOURCE_DERIVED"}) == "protected" and guard({"data_status": "DERIVED"}) == "protected" and guard({"data_status": "REAL"}) == "protected"
    assert guard({"data_status": "USER_PROVIDED", "source_id": "SRC-BRIEF"}) == "protected"
    assert guard({"data_status": "USER_PROVIDED", "source_id": "APP-SESSION"}) == "app-written" and guard({"data_status": "SYNTHETIC_DEMO", "source_id": "APP-SESSION"}) == "app-written"
    assert guard({"data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"}) is None and guard({"data_status": "TEST"}) is None


def part_row(**kw):
    base = {"part_id": "PRT-1", "part_number": "P-1", "name": "Hose", "description": "A synthetic description", "category_id": "CAT-1", "subcategory_id": None, "manufacturer": "Noordveld",
            "oem_status": "OEM", "status": "VERIFIED", "aliases": ["h-1"], "common_names": ["pipe"], "technical_terms": ["Bore 63"], "symptoms": ["oil leak"], **SYN}
    return {**base, **kw}
















# ── checksums ────────────────────────────────────────────────────────────────────────────────────


