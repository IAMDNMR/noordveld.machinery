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
def test_a_valid_record_is_accepted_and_csv_text_is_coerced():
    p = m.Part.model_validate({"part_id": "P", "part_number": "N", "name": "n", "description": "", "category_id": "C", "subcategory_id": "", "manufacturer": "Noordveld", "oem_status": "OEM",
                               "status": "VERIFIED", "aliases": "a|b|", "common_names": "", "technical_terms": "Bore 63", "symptoms": "", **SYN})
    assert p.aliases == ["a", "b"] and p.description is None and p.subcategory_id is None and p.common_names == []


def test_enums_are_enforced_and_a_legacy_fitment_value_is_not_silently_accepted():
    base = {"fitment_id": "f", "machine_id": "m", "variant_id": None, "part_id": "p", "fitment_status": "APPROVED", "approval_status": "APPROVED", "fitment_rule": None, **SYN}
    assert m.Fitment.model_validate(base).fitment_status == "APPROVED"
    with pytest.raises(ValidationError):
        m.Fitment.model_validate({**base, "fitment_status": "CONFIRMED"})  # the export maps CONFIRMED -> APPROVED explicitly; the model never guesses
    with pytest.raises(ValidationError):
        m.Part.model_validate({**base, "part_id": "P"})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({**TECH, "data_status": "MADE_UP"})
    with pytest.raises(ValidationError):
        m.Route.model_validate({"route_id": "r", "origin_location_id": "a", "destination_location_id": "b", "transport_mode": "TELEPORT", "planned_transit_days": 1, "estimated_cost": 1,
                                "currency": "EUR", "service_level": "x", "status": "x", **SYN})


def test_required_fields_must_be_present_and_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        m.Technician.model_validate({k: v for k, v in TECH.items() if k != "dealer_id"})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({**TECH, "unexpected": 1})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({k: v for k, v in TECH.items() if k != "source_type"})  # provenance is required


def test_dates_ranges_and_installation_rules():
    with pytest.raises(ValidationError):
        m.WorkOrder.model_validate({**WO, "service_date": "01/02/2025"})
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate({**INSTALL, "status": "REMOVED", "removal_date": "2025-01-01"})  # removed before it was installed
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate({**INSTALL, "status": "CURRENT", "removal_date": "2025-03-01"})
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate({**INSTALL, "status": "REMOVED", "removal_date": None})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({**TECH, "effective_from": "2026-01-01", "effective_to": "2025-01-01"})
    with pytest.raises(ValidationError):
        m.OrderLine.model_validate({"order_line_id": "l", "order_id": "o", "part_id": "p", "quantity": 0, "unit_price": 1.0, **SYN})


def test_synthetic_evidence_never_carries_a_url():
    ev = {"evidence_id": "e", "evidence_type": "WORK_ORDER", "entity_type": "WORK_ORDER", "entity_id": "WO-1", "reference": "Synthetic demonstration record", **SYN}
    assert m.Evidence.model_validate(ev)
    with pytest.raises(ValidationError):
        m.Evidence.model_validate({**ev, "reference": "https://example.com/report.pdf"})
    assert m.Evidence.model_validate({**ev, "data_status": "REAL", "source_type": "SERVICE", "reference": "https://example.com/report.pdf"})


def test_the_data_status_vocabulary_extends_the_existing_one():
    for status in ("REAL", "SYNTHETIC_DEMO", "REFERENCE", "TEST", "SOURCE_DERIVED", "DERIVED", "USER_PROVIDED"):
        assert m.Technician.model_validate({**TECH, "data_status": status})


def test_every_registry_dataset_has_a_model_a_file_path_and_resolvable_dependencies():
    names = {s.name for s in SPECS}
    assert len(names) == len(SPECS) == 41
    for s in SPECS:
        assert s.depends and set(s.depends) <= names or not s.depends
        assert s.targets or s.rel
    assert next(s.name for s in order()) in {"plants", "categories", "suppliers", "dealers", "customers"}
    seen: set[str] = set()
    for s in order():
        assert set(s.depends) <= seen, f"{s.name} ordered before a dependency"
        seen.add(s.name)


# ── loading ──────────────────────────────────────────────────────────────────────────────────────
def test_json_and_csv_files_round_trip(tmp_path):
    put(tmp_path, "warranty_policies", [POLICY])  # JSON
    put(tmp_path, "technicians", [TECH])  # CSV
    assert load_rows(BY_NAME["warranty_policies"], tmp_path)[0][0]["warranty_policy_id"] == "WP-PRT-1"
    rows, meta = load_rows(BY_NAME["technicians"], tmp_path)
    assert rows[0]["technician_id"] == "TEC-1" and "technician_id" in meta["columns"]
    assert json.loads((tmp_path / "lifecycle" / "warranty_policies.json").read_text())["canonical_schema_version"] == "1.0"


def test_a_csv_with_missing_or_unknown_columns_is_refused_whole(tmp_path):
    (tmp_path / "lifecycle").mkdir()
    (tmp_path / "lifecycle" / "technicians.csv").write_text("technician_id,name\nT1,x\n", encoding="utf-8")
    with pytest.raises(DatasetFileError):
        load_rows(BY_NAME["technicians"], tmp_path)
    report = Engine(seeded(), tmp_path, clock).run(["technicians"], dry_run=True)
    assert report["datasets"][0]["records_invalid"] == 1 and report["datasets"][0]["records_valid"] == 0


# ── ingestion ────────────────────────────────────────────────────────────────────────────────────
def test_dry_run_reports_the_plan_and_writes_nothing(tmp_path):
    engine, store, _ = world(tmp_path)
    nodes_before, rels_before = len(store.nodes), len(store.rels)
    report = engine.run(NEW, dry_run=True)
    t = report["totals"]
    assert t["records_read"] == 5 and t["records_valid"] == 5 and t["records_invalid"] == 0
    assert t["nodes_to_create"] == 5 and t["relationships_to_create"] > 0 and t["records_created"] == 0 and t["relationships_created"] == 0
    assert (len(store.nodes), len(store.rels), store.writes) == (nodes_before, rels_before, 0)


def test_ingestion_creates_nodes_and_relationships_with_provenance(tmp_path):
    engine, store, _ = world(tmp_path)
    report = engine.run(NEW, dry_run=False)
    assert report["totals"]["records_created"] == 5 and report["totals"]["records_failed"] == 0
    n = store.nodes[("InstallationEvent", "INS-1")]
    assert n["source_id"] == "SRC-CANON" and n["data_status"] == "SYNTHETIC_DEMO" and n["provenance_type"] == "SYNTHETIC_DEMO" and n["source_type"] == "SYNTHETIC_DEMO"
    assert n["ingestion_timestamp"].startswith("2026-10-07") and n["canonical_schema_version"] == "1.0" and n["canonical_dataset"] == "installations"
    assert n["authoritative_flag"] is False and n["confidence"] == "NOT_STATED" and n["installation_date"] == "2025-02-01"
    assert ("HAS_INSTALLATION", "MachineInstance", "MI-1", "InstallationEvent", "INS-1") in store.rels  # reverse relationship: instance -> installation
    assert ("INSTALLED_PART", "InstallationEvent", "INS-1", "Part", "PRT-1") in store.rels
    rel = store.rels[("INSTALLED_PART", "InstallationEvent", "INS-1", "Part", "PRT-1")]
    assert rel["rel_id"] == "INSTALLED_PART:INS-1:PRT-1" and rel["source_id"] == "SRC-CANON"  # deterministic relationship id
    assert ("DataSource", "SRC-CANON") in store.nodes


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


def test_no_duplicate_nodes_or_relationships_even_when_the_same_record_is_ingested_in_separate_runs(tmp_path):
    _, store, root = world(tmp_path)
    for _ in range(3):
        Engine(store, root, clock).run(NEW, dry_run=False)
    keys = list(store.nodes)
    assert len(keys) == len(set(keys))
    pairs = [(k[0], k[1], k[2], k[3], k[4]) for k in store.rels]
    assert len(pairs) == len(set(pairs))
    assert sum(1 for k in store.rels if k[0] == "INSTALLED_PART") == 1


def test_the_same_canonical_input_gives_the_same_logical_graph_whatever_the_record_order(tmp_path):
    a_root, b_root = tmp_path / "a", tmp_path / "b"
    second_tech = {**TECH, "technician_id": "TEC-2", "name": "Sanne (demo)"}
    put(a_root, "technicians", [TECH, second_tech])
    put(b_root, "technicians", [second_tech, TECH])
    stores = []
    for root in (a_root, b_root):
        store = seeded()
        Engine(store, root, clock).run(["technicians"], dry_run=False)
        stores.append(store)
    assert graph_fingerprint(stores[0]) == graph_fingerprint(stores[1])


def test_a_changed_value_updates_only_that_property_and_restoring_it_updates_again(tmp_path):
    engine, store, root = world(tmp_path)
    engine.run(NEW, dry_run=False)
    put(root, "technicians", [{**TECH, "certification": "L3"}])
    r = Engine(store, root, clock).run(["technicians"], dry_run=False)
    assert r["totals"]["records_updated"] == 1 and store.nodes[("Technician", "TEC-1")]["certification"] == "L3"
    put(root, "technicians", [TECH])
    Engine(store, root, clock).run(["technicians"], dry_run=False)
    assert store.nodes[("Technician", "TEC-1")]["certification"] == "L2"


def test_an_invalid_relationship_is_rejected_reported_and_never_written(tmp_path):
    engine, store, root = world(tmp_path)
    put(root, "installations", [INSTALL, {**INSTALL, "installation_id": "INS-X", "machine_instance_id": "MI-GHOST"}])  # no such machine instance
    report = engine.run(NEW, dry_run=False)
    d = next(x for x in report["datasets"] if x["dataset"] == "installations")
    assert d["records_invalid"] == 1 and d["records_valid"] == 1 and "MI-GHOST" in d["invalid_examples"][0]["errors"]
    assert ("InstallationEvent", "INS-X") not in store.nodes and ("InstallationEvent", "INS-1") in store.nodes


def test_a_missing_foreign_key_is_rejected_for_every_kind_of_reference(tmp_path):
    engine, store, root = world(tmp_path)
    put(root, "technicians", [TECH, {**TECH, "technician_id": "TEC-9", "dealer_id": "DLR-GHOST"}])
    put(root, "warranty_policies", [POLICY, {**POLICY, "warranty_policy_id": "WP-9", "part_id": "PRT-GHOST"}])
    put(root, "machine_instances", [INSTANCE, {**INSTANCE, "machine_instance_id": "MI-9", "owner_id": "CUS-GHOST"}, {**INSTANCE, "machine_instance_id": "MI-8", "variant_id": "VAR-GHOST"}])
    report = engine.run(NEW, dry_run=False)
    bad = {d["dataset"]: d["records_invalid"] for d in report["datasets"]}
    assert bad["technicians"] == 1 and bad["warranty_policies"] == 1 and bad["machine_instances"] == 2
    assert not any(k[1] in ("TEC-9", "WP-9", "MI-9", "MI-8") for k in store.nodes)


def test_a_dependent_record_of_an_invalid_record_is_rejected_too(tmp_path):
    engine, store, root = world(tmp_path)
    put(root, "machine_instances", [{**INSTANCE, "owner_id": "CUS-GHOST"}])
    report = engine.run(NEW, dry_run=False)
    inv = next(d for d in report["datasets"] if d["dataset"] == "installations")
    assert inv["records_invalid"] == 1 and ("InstallationEvent", "INS-1") not in store.nodes and ("MachineInstance", "MI-1") not in store.nodes


def test_duplicate_ids_in_one_file_are_rejected(tmp_path):
    engine, _, root = world(tmp_path)
    put(root, "technicians", [TECH, {**TECH, "name": "Same id again"}])
    d = engine.run(["technicians"], dry_run=True)["datasets"][0]
    assert d["records_invalid"] == 1 and "duplicate" in d["invalid_examples"][0]["errors"]


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


def test_parts_extend_the_synthetic_profile_and_never_touch_the_protected_part(tmp_path):
    store = seeded()
    part_before = dict(store.nodes[("Part", "PRT-1")])
    put(tmp_path, "parts", [part_row()])
    put(tmp_path, "categories", [{"category_id": "CAT-1", "name": "Hydraulics", "parent_category_id": None, "status": None, "data_status": "SOURCE_DERIVED", "source_type": "OEM_MASTER"}])
    report = Engine(store, tmp_path, clock).run(["categories", "parts"], dry_run=False)
    assert store.nodes[("Part", "PRT-1")] == part_before  # SOURCE_DERIVED: byte-identical
    profile = store.nodes[("PartCatalogProfile", "PCP-PRT-1")]
    assert profile["description"] == "A synthetic description" and profile["common_names"] == ["pipe"] and profile["symptoms"] == ["oil leak"] and profile["oem_status"] == "OEM"
    assert profile["part_status"] == "VERIFIED" and profile["source_id"] == "SRC-003"  # existing provenance kept
    assert next(d for d in report["datasets"] if d["dataset"] == "parts")["records_protected_skipped"] == 1


def test_a_canonical_value_that_conflicts_with_a_protected_record_is_reported_as_drift_not_written(tmp_path):
    store = seeded()
    put(tmp_path, "categories", [{"category_id": "CAT-1", "name": "Hydraulic parts", "parent_category_id": None, "status": None, "data_status": "SOURCE_DERIVED", "source_type": "OEM_MASTER"}])
    report = Engine(store, tmp_path, clock).run(["categories"], dry_run=False)
    d = report["datasets"][0]
    assert d["records_drift"] == 1 and d["drift_examples"][0]["properties"] == ["name"]
    assert store.nodes[("Category", "CAT-1")]["name"] == "Hydraulics"


def test_a_specification_name_that_only_differs_in_case_is_normalisation_not_drift(tmp_path):
    store = seeded()
    store.seed_node("PartSpecification", "specification_id", {"specification_id": "SPC-1", "name": "bore", "value": "63", "data_status": "SOURCE_DERIVED", "source_id": "SRC-001"})
    put(tmp_path, "parts", [part_row()])
    put(tmp_path, "specifications", [{"specification_id": "SPC-1", "part_id": "PRT-1", "name": "bore", "value": "63", "unit": None, "source_text": None, "group": None, **SYN}])
    d = Engine(store, tmp_path, clock).run(["parts", "specifications"], dry_run=True)["datasets"][1]
    assert d["records_drift"] == 0 and d["records_extension_pending"] == 1  # canonical 'Bore', graph 'bore': normalised in the canonical file only
    assert store.nodes[("PartSpecification", "SPC-1")]["name"] == "bore"
    rows = load_rows(BY_NAME["specifications"], tmp_path)[0]
    assert rows[0]["name"] == "bore"  # the file is the input; normalisation happens on validation


def test_app_written_records_are_compared_not_changed(tmp_path):
    store = seeded()
    store.seed_node("Order", "order_id", {"order_id": "HCME-ORD-000001", "order_status": "ALLOCATED", "data_status": "USER_PROVIDED", "source_id": "APP-SESSION"})
    put(tmp_path, "orders", [{"order_id": "HCME-ORD-000001", "customer_id": None, "dealer_id": None, "order_date": "2026-10-06", "status": "NEW", "priority": None, "currency": "EUR",
                              "total_value": None, "channel": "DIRECT_ORDER", **SYN}])
    d = Engine(store, tmp_path, clock).run(["orders"], dry_run=False)["datasets"][0]
    assert d["records_drift"] == 1 and d["records_protected_skipped"] == 1 and store.nodes[("Order", "HCME-ORD-000001")]["order_status"] == "ALLOCATED"


def test_a_verify_dataset_never_updates_an_unprotected_node_either(tmp_path):
    store = seeded()
    store.seed_node("OrderLine", "order_line_id", {"order_line_id": "OL-1", "quantity": 2, "unit_price_eur": 10.0, "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    store.seed_node("Order", "order_id", {"order_id": "ORD-1", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"})
    put(tmp_path, "parts", [part_row()])
    put(tmp_path, "order_lines", [{"order_line_id": "OL-1", "order_id": "ORD-1", "part_id": "PRT-1", "quantity": 5, "unit_price": 10.0, "requested_date": None, **SYN}])
    d = Engine(store, tmp_path, clock).run(["parts", "order_lines"], dry_run=False)["datasets"][1]
    assert d["records_drift"] == 1 and store.nodes[("OrderLine", "OL-1")]["quantity"] == 2


def test_a_target_that_must_exist_is_not_created(tmp_path):
    store = seeded()
    del store.nodes[("PartCatalogProfile", "PCP-PRT-1")]
    put(tmp_path, "parts", [part_row()])
    d = Engine(store, tmp_path, clock).run(["parts"], dry_run=False)["datasets"][0]
    assert d["records_invalid"] == 1 and ("PartCatalogProfile", "PCP-PRT-1") not in store.nodes


def test_nothing_is_ever_deleted(tmp_path):
    engine, store, root = world(tmp_path)
    engine.run(NEW, dry_run=False)
    before = set(store.nodes), set(store.rels)
    put(root, "technicians", [])  # a file with fewer records never removes what was ingested
    Engine(store, root, clock).run(NEW, dry_run=False)
    assert before[0] <= set(store.nodes) and before[1] <= set(store.rels)


# ── checksums ────────────────────────────────────────────────────────────────────────────────────
def test_dataset_checksum_is_deterministic_independent_of_order_and_sensitive_to_values():
    a, b = m.Technician.model_validate(TECH), m.Technician.model_validate({**TECH, "technician_id": "TEC-2"})
    assert dataset_checksum([a, b]) == dataset_checksum([b, a]) == dataset_checksum([a, b])
    assert dataset_checksum([a]) != dataset_checksum([a.model_copy(update={"certification": "L9"})])
    assert dataset_checksum([a]) == dataset_checksum([a.model_copy(update={"ingestion_timestamp": "2030-01-01"})])  # the run's timestamp is not part of the data


def test_the_graph_fingerprint_changes_when_an_ingested_value_is_tampered_with(tmp_path):
    engine, store, _ = world(tmp_path)
    engine.run(NEW, dry_run=False)
    good = graph_fingerprint(store)
    store.nodes[("Technician", "TEC-1")]["certification"] = "tampered"
    assert graph_fingerprint(store) != good
    store.nodes[("Technician", "TEC-1")]["certification"] = "L2"
    assert graph_fingerprint(store) == good
