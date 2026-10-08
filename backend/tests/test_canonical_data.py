"""The committed canonical datasets: they validate, hang together, carry the right provenance and match their recorded checksums.

Part 1 is offline (files only). Part 2 reads the live graph (read-only). Part 3 writes TEST records to the graph and is opt-in (RUN_GRAPH_WRITE_TESTS=1).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from app.canonical import models as m
from app.canonical.engine import Engine
from app.canonical.integrity import dataset_checksum, graph_fingerprint
from app.canonical.io import CANON_DIR, dump_rows, load_rows, read_manifest
from app.canonical.registry import BY_NAME, SPECS
from app.core.config import get_settings

LIFECYCLE = ["machine_instances", "technicians", "work_orders", "installations", "replacements", "warranty_policies", "warranty_claims", "evidence"]
live = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


def rows(name: str) -> list[dict]:
    return load_rows(BY_NAME[name], CANON_DIR)[0]


def records(name: str) -> list[m.Canon]:
    spec = BY_NAME[name]
    return [spec.model.model_validate(r) for r in rows(name)]


# ── part 1: files only ───────────────────────────────────────────────────────────────────────────
def test_every_dataset_file_exists_and_every_record_is_valid():
    report = Engine(None, CANON_DIR).run(dry_run=True)
    assert report["offline"] and len(report["datasets"]) == len(SPECS)
    for d in report["datasets"]:
        assert d["records_read"] > 0, d["dataset"]
        assert d["records_invalid"] == 0, (d["dataset"], d["invalid_examples"])


def test_the_manifest_lists_every_dataset_with_its_current_checksum():
    manifest = read_manifest(CANON_DIR)
    assert manifest["canonical_schema_version"] == "1.0" and set(manifest["datasets"]) == {s.name for s in SPECS}
    for name, entry in manifest["datasets"].items():
        recs = records(name)
        assert entry["records"] == len(recs) and entry["dataset_version"] == "v1", name
        assert entry["checksum"] == dataset_checksum(recs), f"{name}: the file changed without the manifest being refreshed (python backend/scripts/canonical.py validate)"


def test_json_datasets_carry_their_schema_and_dataset_version():
    for spec in SPECS:
        if spec.fmt == "json":
            body = json.loads((CANON_DIR / spec.path).read_text(encoding="utf-8"))
            assert body["canonical_schema_version"] == "1.0" and body["dataset_version"] == "v1" and body["dataset"] == spec.name and body["generated_at"]


def test_dataset_files_follow_the_requested_directory_layout():
    assert {s.path.split("/")[0] for s in SPECS} == {"master", "relationships", "commerce", "logistics", "lifecycle", "scenarios"}
    assert (CANON_DIR / "reference" / "discovery_vocabulary.json").exists()


def test_all_newly_generated_lifecycle_data_is_marked_synthetic():
    for name in LIFECYCLE + ["scenarios_discovery", "scenarios_logistics", "scenarios_warranty", "fitment", "approved_sources"]:
        for r in records(name):
            assert r.data_status == "SYNTHETIC_DEMO" and r.source_type == "SYNTHETIC_DEMO", (name, r.id)


def test_evidence_never_carries_a_fabricated_url_or_document_id():
    for r in records("evidence"):
        assert r.reference and "http" not in r.reference.lower() and "synthetic" in r.reference.lower()


def test_lifecycle_records_reference_each_other_consistently():
    inst = {r["machine_instance_id"]: r for r in rows("machine_instances")}
    wo = {r["work_order_id"]: r for r in rows("work_orders")}
    ins = {r["installation_id"]: r for r in rows("installations")}
    tech = {r["technician_id"]: r for r in rows("technicians")}
    for r in rows("work_orders"):
        assert r["machine_instance_id"] in inst and (not r["technician_id"] or (r["technician_id"] in tech and tech[r["technician_id"]]["dealer_id"] == r["dealer_id"]))
    for r in rows("installations"):  # a work order may record several installations, and an incomplete installation may have no work order or technician at all
        assert r["machine_instance_id"] in inst
        if r["work_order_id"]:
            w = wo[r["work_order_id"]]
            assert w["machine_instance_id"] == r["machine_instance_id"] and w["dealer_id"] == r["dealer_id"] and w["service_date"] == r["installation_date"]
        else:
            assert r["validation_status"] == "INCOMPLETE" and "work_order_missing" in r["validation_issues"]
    for r in rows("replacements"):
        old, new = ins[r["removed_installation_id"]], ins[r["new_installation_id"]]
        assert old["status"] == "REMOVED" and old["removal_date"] == r["replacement_date"] and new["installation_date"] == r["replacement_date"]
        assert new["status"] == ("REMOVED" if any(x["removed_installation_id"] == new["installation_id"] for x in rows("replacements")) else "CURRENT")  # a replacement can itself be replaced
        assert old["machine_instance_id"] == new["machine_instance_id"] == r["machine_instance_id"] and old["part_id"] == r["removed_part_id"] and new["part_id"] == r["installed_part_id"]
    for r in rows("warranty_claims"):
        i = ins[r["installation_id"]]
        assert i["machine_instance_id"] == r["machine_instance_id"] and i["part_id"] == r["part_id"] and r["claim_date"] >= r["failure_date"]
        assert (not r["decision"]) == (r["status"] == "UNDER_REVIEW") or r["status"] in ("SUBMITTED", "CLOSED")
    for r in rows("evidence"):
        pool = {"WORK_ORDER": wo, "INSTALLATION": ins, "WARRANTY_CLAIM": {c["claim_id"]: c for c in rows("warranty_claims")}, "TECHNICIAN": tech,
                "DEALER": {d["dealer_id"]: d for d in rows("dealers")}, "PART": {p["part_id"]: p for p in rows("parts")}}[r["entity_type"]]
        assert r["entity_id"] in pool


def test_history_is_kept_a_replaced_part_stays_on_record_beside_its_replacement():
    by_instance = defaultdict(list)
    for r in rows("installations"):
        by_instance[r["machine_instance_id"]].append(r)
    replaced = {r["machine_instance_id"] for r in rows("replacements")}
    assert replaced
    for mid in replaced:
        statuses = Counter(i["status"] for i in by_instance[mid])
        assert statuses["REMOVED"] >= 1 and statuses["CURRENT"] >= 1  # the removed installation is still there beside its replacement
        removed_parts = {i["part_id"] for i in by_instance[mid] if i["status"] == "REMOVED"}
        assert removed_parts <= {i["part_id"] for i in by_instance[mid] if i["status"] == "CURRENT"}
    for mid, items in by_instance.items():  # at most one CURRENT installation per part per machine
        current = [i["part_id"] for i in items if i["status"] == "CURRENT"]
        assert len(current) == len(set(current))


def test_machine_serial_numbers_are_unique_and_belong_to_the_model():
    serials = [r["serial_number"] for r in rows("machine_instances")]
    assert len(serials) == len(set(serials))
    models = {r["machine_id"]: r["model"] for r in rows("machines")}
    for r in rows("machine_instances"):
        assert r["serial_number"].startswith(models[r["machine_id"]] + "-")


def test_fitment_statuses_use_the_target_vocabulary_and_ids_are_unique():
    fit = rows("fitment")
    assert {r["fitment_status"] for r in fit} <= {"APPROVED", "CONDITIONAL", "DEPRECATED", "NOT_APPROVED"}
    assert len({r["fitment_id"] for r in fit}) == len(fit) == 219
    assert Counter(r["fitment_status"] for r in fit) == Counter({"APPROVED": 216, "CONDITIONAL": 3})  # CONFIRMED -> APPROVED, nothing else reinterpreted


def test_parts_carry_discovery_data_and_their_existing_aliases_are_preserved():
    parts = rows("parts")
    assert len(parts) == 100 and all(p["description"] and p["symptoms"] and p["technical_terms"] is not None for p in parts)
    assert all(p["aliases"] for p in parts) and sum(bool(p["common_names"]) for p in parts) >= 30
    assert len({p["part_number"] for p in parts}) == 100  # synonyms never became separate parts


def test_specification_names_are_normalised_and_original_text_is_kept():
    names = {r["name"] for r in rows("specifications")}
    assert {"bore", "stroke", "ratio"}.isdisjoint(names) and {"Bore", "Stroke", "Ratio"} <= names
    assert sum(1 for r in rows("specifications") if r["name"] in ("Note segment", "Spec Note")) == 208  # free text preserved, not parsed into invented values


def test_shipments_without_a_determinable_route_are_flagged_not_invented():
    for r in rows("shipments"):
        if not r["route_id"]:
            assert "ROUTE_NOT_DETERMINABLE" in r["remediation_flags"].split("|")
        else:
            assert "ROUTE_NOT_DETERMINABLE" not in r["remediation_flags"].split("|")


def test_app_written_records_are_not_in_the_canonical_files():
    assert not any(r["order_id"].startswith("HCME-ORD") for r in rows("orders"))
    assert not any(re.match(r"^HCME-ORD", r["order_id"]) for r in rows("order_lines"))


def test_the_film_constants_and_city_coordinates_became_canonical_records():
    film = next(r for r in rows("scenarios_discovery") if r["scenario_type"] == "FILM")
    assert film["customer_id"] == "CUS-008" and film["part_id"] and film["machine_id"]
    cities = [r for r in rows("locations") if r["location_kind"] == "CITY" and r["latitude"]]
    assert cities and all(r["geo_basis"] == "REFERENCE_CITY_CENTRE" for r in cities)


def test_route_modes_are_values_of_the_existing_network_never_a_rule():
    modes = {r["transport_mode"] for r in rows("routes")}
    assert modes <= set(m.TransportMode.__args__) and {"ROAD", "AIR", "RAIL"} <= modes
    assert len({(r["transport_mode"], r["planned_transit_days"]) for r in rows("routes")}) > 3  # values are per route


# ── part 2: the live graph, read-only ────────────────────────────────────────────────────────────
@live
def test_live_graph_has_nothing_left_to_create_or_update_for_the_ingested_domains():
    from app.canonical.store import Neo4jStore

    store = Neo4jStore(get_settings())
    try:
        names = ["plants", "categories", "machines", "fitment", "approved_sources", "warranty_policies", "machine_instances", "technicians", "scenarios_warranty"]
        t = Engine(store, CANON_DIR).run(names, dry_run=True)["totals"]
    finally:
        store.close()
    assert t["records_invalid"] == 0 and t["records_drift"] == 0
    assert (t["nodes_to_create"], t["nodes_to_update"], t["relationships_to_create"], t["relationships_to_update"]) == (0, 0, 0, 0), t


@live
def test_live_existing_integrity_checksum_still_matches_its_baseline_and_the_canonical_baseline_matches_the_graph():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eu_foundation"))
    from audit_before import source_checksum

    from app.canonical.store import Neo4jStore

    baseline = json.loads((Path(__file__).resolve().parents[1] / "data" / "eu_foundation" / "audit_before.json").read_text(encoding="utf-8"))["source_checksum"]
    assert source_checksum() == baseline  # the SOURCE/DERIVED DATA INTEGRITY CHECKSUM is untouched by the canonical layer
    store = Neo4jStore(get_settings())
    try:
        recorded = json.loads((CANON_DIR / "integrity.json").read_text(encoding="utf-8"))
        assert graph_fingerprint(store) == recorded["graph_fingerprint"]
    finally:
        store.close()


# ── part 3: opt-in, writes TEST records and removes them ─────────────────────────────────────────
@pytest.mark.skipif(not (get_settings().graph_configured and os.environ.get("RUN_GRAPH_WRITE_TESTS") == "1"), reason="writes to the database: set RUN_GRAPH_WRITE_TESTS=1 to run")
def test_live_merge_creates_each_record_once_however_often_it_is_ingested(tmp_path):
    from app.canonical.store import Neo4jStore

    store = Neo4jStore(get_settings())
    dealer = store._read("MATCH (d:Dealer) RETURN d.dealer_id AS id ORDER BY id LIMIT 1")[0]["id"]
    tech = {"technician_id": "TEC-TEST-CANON-1", "dealer_id": dealer, "name": "Canonical test technician", "certification": "TEST", "specialization": None, "status": "ACTIVE",
            "data_status": "TEST", "source_type": "SYNTHETIC_DEMO"}
    dump_rows(BY_NAME["technicians"], [tech], tmp_path, "2026-10-07T00:00:00Z")
    try:
        runs = [Engine(store, tmp_path).run(["technicians"], dry_run=False) for _ in range(3)]
        assert runs[0]["totals"]["records_created"] == 1 and runs[1]["totals"]["records_created"] == 0 and runs[2]["totals"]["records_updated"] == 0
        count = store._read("MATCH (t:Technician {technician_id: 'TEC-TEST-CANON-1'}) RETURN count(t) AS n")[0]["n"]
        rels = store._read("MATCH (:Technician {technician_id: 'TEC-TEST-CANON-1'})-[r:EMPLOYED_BY]->(:Dealer) RETURN count(r) AS n")[0]["n"]
        node = store._read("MATCH (t:Technician {technician_id: 'TEC-TEST-CANON-1'}) RETURN properties(t) AS p")[0]["p"]
        assert (count, rels) == (1, 1) and node["data_status"] == "TEST" and node["source_id"] == "SRC-CANON"
    finally:
        store._write("MATCH (t:Technician {technician_id: 'TEC-TEST-CANON-1'}) DETACH DELETE t")
        store.close()
