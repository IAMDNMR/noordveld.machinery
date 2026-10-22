"""Canonical models and the ingestion engine, on an isolated in-memory world: no Neo4j, deterministic.

The MemoryStore has the same contract as the Neo4j store, so planning (create / update / unchanged / verify), idempotency, dry-run and the protection
policy are proven here exactly as they behave against the real graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.canonical import models as m
from app.canonical.engine import Engine, guard
from app.canonical.integrity import dataset_checksum, graph_fingerprint
from app.canonical.io import dump_rows
from app.canonical.registry import BY_NAME, SPECS, order
from app.canonical.store import MemoryStore

SYN = {"data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO"}
CLOCK = iter(f"2026-10-07T10:{n // 60:02d}:{n % 60:02d}Z" for n in range(100000))


def clock() -> str:
    return next(CLOCK)


def seeded() -> MemoryStore:
    s = MemoryStore()
    s.seed_node(
        "Machine",
        "machine_id",
        {
            "machine_id": "MCH-1",
            "model_code": "X-1",
            "machine_type": "Loader",
            "name": "X-1 Loader",
            "data_status": "SOURCE_DERIVED",
            "source_id": "SRC-001",
        },
    )
    s.seed_node(
        "MachineVariant",
        "variant_id",
        {"variant_id": "VAR-1", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"},
    )
    s.seed_node(
        "Customer",
        "customer_id",
        {
            "customer_id": "CUS-1",
            "name": "Customer One (demo)",
            "data_status": "SYNTHETIC_DEMO",
            "source_id": "SRC-003",
        },
    )
    s.seed_node(
        "ShipTo",
        "shipto_id",
        {"shipto_id": "SHT-1", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005"},
    )
    s.seed_node(
        "Dealer",
        "dealer_id",
        {
            "dealer_id": "DLR-1",
            "name": "Dealer One (demo)",
            "data_status": "SYNTHETIC_DEMO",
            "source_id": "SRC-005",
        },
    )
    s.seed_node(
        "Part",
        "part_id",
        {
            "part_id": "PRT-1",
            "part_number": "P-1",
            "name": "Hose",
            "brand": "Noordveld",
            "data_status": "SOURCE_DERIVED",
            "source_id": "SRC-001",
        },
    )
    s.seed_node(
        "PartCatalogProfile",
        "profile_id",
        {
            "profile_id": "PCP-PRT-1",
            "part_status": "VERIFIED",
            "data_status": "SYNTHETIC_DEMO",
            "source_id": "SRC-003",
        },
    )
    s.seed_node(
        "Category",
        "category_id",
        {
            "category_id": "CAT-1",
            "name": "Hydraulics",
            "data_status": "SOURCE_DERIVED",
            "source_id": "SRC-001",
        },
    )
    return s


TECH = {
    "technician_id": "TEC-1",
    "dealer_id": "DLR-1",
    "name": "Jan (demo)",
    "certification": "L2",
    "specialization": "Hydraulics",
    "status": "ACTIVE",
    **SYN,
}
INSTANCE = {
    "machine_instance_id": "MI-1",
    "machine_id": "MCH-1",
    "variant_id": "VAR-1",
    "serial_number": "X-1-00001",
    "model_year": 2024,
    "owner_id": "CUS-1",
    "location_id": "SHT-1",
    "status": "IN_SERVICE",
    **SYN,
}
WO = {
    "work_order_id": "WO-1",
    "machine_instance_id": "MI-1",
    "dealer_id": "DLR-1",
    "technician_id": "TEC-1",
    "service_date": "2025-02-01",
    "service_type": "INSTALLATION",
    "status": "COMPLETED",
    "reason": None,
    **SYN,
}
INSTALL = {
    "installation_id": "INS-1",
    "machine_instance_id": "MI-1",
    "part_id": "PRT-1",
    "part_serial_number": "SN-1",
    "dealer_id": "DLR-1",
    "technician_id": "TEC-1",
    "work_order_id": "WO-1",
    "installation_date": "2025-02-01",
    "removal_date": None,
    "status": "CURRENT",
    **SYN,
}
POLICY = {
    "warranty_policy_id": "WP-PRT-1",
    "part_id": "PRT-1",
    "coverage_type": "STANDARD",
    "coverage_period_days": 365,
    "coverage_conditions": ["APPROVED_PART"],
    "start_rule": "INSTALLATION_DATE",
    "region": None,
    "status": "ACTIVE",
    **SYN,
}


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
    p = m.Part.model_validate(
        {
            "part_id": "P",
            "part_number": "N",
            "name": "n",
            "description": "",
            "category_id": "C",
            "subcategory_id": "",
            "manufacturer": "Noordveld",
            "oem_status": "OEM",
            "status": "VERIFIED",
            "aliases": "a|b|",
            "common_names": "",
            "technical_terms": "Bore 63",
            "symptoms": "",
            **SYN,
        }
    )
    assert (
        p.aliases == ["a", "b"]
        and p.description is None
        and p.subcategory_id is None
        and p.common_names == []
    )


def test_enums_are_enforced_and_a_legacy_fitment_value_is_not_silently_accepted():
    base = {
        "fitment_id": "f",
        "machine_id": "m",
        "variant_id": None,
        "part_id": "p",
        "fitment_status": "APPROVED",
        "approval_status": "APPROVED",
        "fitment_rule": None,
        **SYN,
    }
    assert m.Fitment.model_validate(base).fitment_status == "APPROVED"
    with pytest.raises(ValidationError):
        m.Fitment.model_validate(
            {**base, "fitment_status": "CONFIRMED"}
        )  # the export maps CONFIRMED -> APPROVED explicitly; the model never guesses
    with pytest.raises(ValidationError):
        m.Part.model_validate({**base, "part_id": "P"})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({**TECH, "data_status": "MADE_UP"})
    with pytest.raises(ValidationError):
        m.Route.model_validate(
            {
                "route_id": "r",
                "origin_location_id": "a",
                "destination_location_id": "b",
                "transport_mode": "TELEPORT",
                "planned_transit_days": 1,
                "estimated_cost": 1,
                "currency": "EUR",
                "service_level": "x",
                "status": "x",
                **SYN,
            }
        )


def test_required_fields_must_be_present_and_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        m.Technician.model_validate({k: v for k, v in TECH.items() if k != "dealer_id"})
    with pytest.raises(ValidationError):
        m.Technician.model_validate({**TECH, "unexpected": 1})
    with pytest.raises(ValidationError):
        m.Technician.model_validate(
            {k: v for k, v in TECH.items() if k != "source_type"}
        )  # provenance is required


def test_dates_ranges_and_installation_rules():
    with pytest.raises(ValidationError):
        m.WorkOrder.model_validate({**WO, "service_date": "01/02/2025"})
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate(
            {**INSTALL, "status": "REMOVED", "removal_date": "2025-01-01"}
        )  # removed before it was installed
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate(
            {**INSTALL, "status": "CURRENT", "removal_date": "2025-03-01"}
        )
    with pytest.raises(ValidationError):
        m.InstallationEvent.model_validate({**INSTALL, "status": "REMOVED", "removal_date": None})
    with pytest.raises(ValidationError):
        m.Technician.model_validate(
            {**TECH, "effective_from": "2026-01-01", "effective_to": "2025-01-01"}
        )
    with pytest.raises(ValidationError):
        m.OrderLine.model_validate(
            {
                "order_line_id": "l",
                "order_id": "o",
                "part_id": "p",
                "quantity": 0,
                "unit_price": 1.0,
                **SYN,
            }
        )


def test_synthetic_evidence_never_carries_a_url():
    ev = {
        "evidence_id": "e",
        "evidence_type": "WORK_ORDER",
        "entity_type": "WORK_ORDER",
        "entity_id": "WO-1",
        "reference": "Synthetic demonstration record",
        **SYN,
    }
    assert m.Evidence.model_validate(ev)
    with pytest.raises(ValidationError):
        m.Evidence.model_validate({**ev, "reference": "https://example.com/report.pdf"})
    assert m.Evidence.model_validate(
        {
            **ev,
            "data_status": "REAL",
            "source_type": "SERVICE",
            "reference": "https://example.com/report.pdf",
        }
    )


def test_the_data_status_vocabulary_extends_the_existing_one():
    for status in (
        "REAL",
        "SYNTHETIC_DEMO",
        "REFERENCE",
        "TEST",
        "SOURCE_DERIVED",
        "DERIVED",
        "USER_PROVIDED",
    ):
        assert m.Technician.model_validate({**TECH, "data_status": status})


def test_every_registry_dataset_has_a_model_a_file_path_and_resolvable_dependencies():
    names = {s.name for s in SPECS}
    assert len(names) == len(SPECS) == 43
    for s in SPECS:
        assert s.depends and set(s.depends) <= names or not s.depends
        assert s.targets or s.rel
    assert next(s.name for s in order()) in {
        "plants",
        "categories",
        "suppliers",
        "dealers",
        "customers",
    }
    seen: set[str] = set()
    for s in order():
        assert set(s.depends) <= seen, f"{s.name} ordered before a dependency"
        seen.add(s.name)


# ── loading ──────────────────────────────────────────────────────────────────────────────────────


# ── ingestion ────────────────────────────────────────────────────────────────────────────────────


def test_a_second_run_is_idempotent_no_writes_no_duplicates_same_fingerprint(tmp_path):
    engine, store, root = world(tmp_path)
    engine.run(NEW, dry_run=False)
    nodes, rels, fingerprint = len(store.nodes), len(store.rels), graph_fingerprint(store)
    writes = store.writes
    second = Engine(store, root, clock).run(NEW, dry_run=False)
    assert second["totals"]["records_created"] == 0 and second["totals"]["records_updated"] == 0
    assert (
        second["totals"]["nodes_to_create"] == 0
        and second["totals"]["nodes_to_update"] == 0
        and second["totals"]["relationships_to_create"] == 0
    )
    assert (len(store.nodes), len(store.rels), store.writes) == (nodes, rels, writes)
    assert graph_fingerprint(store) == fingerprint
    third = Engine(store, root, clock).run(NEW, dry_run=False)
    assert graph_fingerprint(store) == fingerprint and third["totals"]["records_unchanged"] == 5


# ── the write policy ─────────────────────────────────────────────────────────────────────────────
def test_protected_and_app_written_records_are_never_modified():
    assert (
        guard({"data_status": "SOURCE_DERIVED"}) == "protected"
        and guard({"data_status": "DERIVED"}) == "protected"
        and guard({"data_status": "REAL"}) == "protected"
    )
    assert guard({"data_status": "USER_PROVIDED", "source_id": "SRC-BRIEF"}) == "protected"
    assert (
        guard({"data_status": "USER_PROVIDED", "source_id": "APP-SESSION"}) == "app-written"
        and guard({"data_status": "SYNTHETIC_DEMO", "source_id": "APP-SESSION"}) == "app-written"
    )
    assert (
        guard({"data_status": "SYNTHETIC_DEMO", "source_id": "SRC-003"}) is None
        and guard({"data_status": "TEST"}) is None
    )


def part_row(**kw):
    base = {
        "part_id": "PRT-1",
        "part_number": "P-1",
        "name": "Hose",
        "description": "A synthetic description",
        "category_id": "CAT-1",
        "subcategory_id": None,
        "manufacturer": "Noordveld",
        "oem_status": "OEM",
        "status": "VERIFIED",
        "aliases": ["h-1"],
        "common_names": ["pipe"],
        "technical_terms": ["Bore 63"],
        "symptoms": ["oil leak"],
        **SYN,
    }
    return {**base, **kw}


# ── checksums ────────────────────────────────────────────────────────────────────────────────────
def test_dataset_checksum_is_deterministic_independent_of_order_and_sensitive_to_values():
    a, b = (
        m.Technician.model_validate(TECH),
        m.Technician.model_validate({**TECH, "technician_id": "TEC-2"}),
    )
    assert dataset_checksum([a, b]) == dataset_checksum([b, a]) == dataset_checksum([a, b])
    assert dataset_checksum([a]) != dataset_checksum([a.model_copy(update={"certification": "L9"})])
    assert dataset_checksum([a]) == dataset_checksum(
        [a.model_copy(update={"ingestion_timestamp": "2030-01-01"})]
    )  # the run's timestamp is not part of the data


def test_the_graph_fingerprint_changes_when_an_ingested_value_is_tampered_with(tmp_path):
    engine, store, _ = world(tmp_path)
    engine.run(NEW, dry_run=False)
    good = graph_fingerprint(store)
    store.nodes[("Technician", "TEC-1")]["certification"] = "tampered"
    assert graph_fingerprint(store) != good
    store.nodes[("Technician", "TEC-1")]["certification"] = "L2"
    assert graph_fingerprint(store) == good


def test_a_node_the_canonical_ingestion_created_follows_the_records_source_record_id_and_a_foreign_node_does_not(
    tmp_path,
):
    engine, store, _ = world(tmp_path)
    engine.run(NEW, dry_run=False)
    key = ("Technician", "TEC-1")
    assert store.nodes[key]["source_id"] == "SRC-CANON"
    put(tmp_path, "technicians", [{**TECH, "source_record_id": "synthetic:TEC-1"}])
    assert (
        Engine(store, tmp_path, clock).run(["technicians"], dry_run=True)["totals"][
            "nodes_to_update"
        ]
        == 1
    )
    Engine(store, tmp_path, clock).run(["technicians"], dry_run=False)
    assert (
        store.nodes[key]["source_record_id"] == "synthetic:TEC-1"
        and store.nodes[key]["name"] == TECH["name"]
    )
    assert (
        Engine(store, tmp_path, clock).run(["technicians"], dry_run=True)["totals"][
            "nodes_to_update"
        ]
        == 0
    )  # idempotent
    store.nodes[key]["source_id"], store.nodes[key]["source_record_id"] = "SRC-OTHER", "theirs"
    Engine(store, tmp_path, clock).run(["technicians"], dry_run=False)
    assert (
        store.nodes[key]["source_record_id"] == "theirs"
    )  # a record another source created keeps its own provenance
