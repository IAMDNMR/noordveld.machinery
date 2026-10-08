"""Phase 4H remediation: the validator compares overlay entities against their own provenance, and every graph reader returns every field of the canonical record.
No database: an in-memory twin and a stub graph."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commerce_validation_lib as L
import reader_mapping_audit as A

from app.canonical.graph_rows import graph_row
from app.canonical.io import CANON_DIR
from app.canonical.registry import BY_NAME
from app.logistics.readers import GraphReader as LogisticsGraphReader


def twin() -> L.MemorySource:
    return L.MemorySource.from_files(CANON_DIR)


def parts_result(m: L.MemorySource) -> L.DatasetResult:
    return next(r for r in L.compare_datasets(m, names=["parts"]) if r.dataset == "parts")


def bad(r: L.DatasetResult) -> list[tuple[str, str, str]]:
    return [(d["record_id"], d["field"], d["difference_type"]) for d in r.differences if d["difference_type"] in L.FAILING]


# ── Part and PartCatalogProfile are validated independently ──────────────────────────────────────
def test_a_synchronised_part_and_its_profile_each_match_their_own_provenance():
    m = twin()
    assert m.n[("Part", "part_id")]["PRT-007"]["data_status"] == "SOURCE_DERIVED"
    assert m.n[("PartCatalogProfile", "profile_id")]["PCP-PRT-007"]["data_status"] == "SYNTHETIC_DEMO"  # a different status on a different node: that is correct
    r = parts_result(m)
    assert r.status() == "PASS" and bad(r) == []


def test_the_profile_is_not_checked_against_the_parts_provenance():
    m = twin()
    m.n[("PartCatalogProfile", "profile_id")]["PCP-PRT-007"]["data_status"] = "SOURCE_DERIVED"  # a profile claiming the part's status is wrong, whatever the part says
    assert bad(parts_result(m)) == [("PRT-007", "PartCatalogProfile.data_status", "VALUE_MISMATCH")]


def test_the_part_is_not_checked_against_the_profiles_provenance():
    m = twin()
    m.n[("Part", "part_id")]["PRT-007"]["data_status"] = "SYNTHETIC_DEMO"  # drift in the supplied part is reported on the Part, not the profile
    r = parts_result(m)
    assert bad(r) == [("PRT-007", "Part.data_status", "VALUE_MISMATCH")]


def test_both_can_drift_together_and_are_reported_as_two_findings():
    m = twin()
    m.n[("Part", "part_id")]["PRT-007"]["data_status"] = "REAL"
    m.n[("PartCatalogProfile", "profile_id")]["PCP-PRT-007"]["data_status"] = "REAL"
    assert sorted(bad(parts_result(m))) == [("PRT-007", "Part.data_status", "VALUE_MISMATCH"), ("PRT-007", "PartCatalogProfile.data_status", "VALUE_MISMATCH")]


def test_a_profile_hung_on_no_part_is_reported():
    m = twin()
    del m.r[("PROFILES_PART", "PartCatalogProfile", "Part")][("PCP-PRT-007", "PRT-007")]
    assert bad(parts_result(m)) == [("PRT-007", "edge:PROFILES_PART", "MISSING_IN_GRAPH")]


def test_the_protected_comparison_does_not_fail_on_the_overlay():
    m = twin()
    protected = [r for r in L.compare_datasets(m) if r.protected]
    assert protected and all(r.status() == "PASS" for r in protected)


# ── every reader returns every field ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dataset", [n for n in A.READER_DATASETS if BY_NAME[n].targets or n.endswith("route_legs")])
def test_graph_row_has_exactly_the_fields_of_the_canonical_model(dataset):
    row = graph_row(dataset, {"data_status": "SYNTHETIC_DEMO"})
    assert set(row) == set(BY_NAME[dataset].model.model_fields) - {"ingestion_timestamp"}


def test_graph_row_reads_mapped_properties_provenance_effective_dates_and_makes_empty_lists():
    row = graph_row("orders", {"order_status": "SHIPPED", "currency": "EUR", "order_total_incl_vat": 10.5, "effective_from": "2026-01-01", "data_status": "SOURCE_DERIVED", "source_record_id": "ORD-1"},
                    order_id="ORD-1", customer_id="CUS-1", dealer_id=None)
    assert row["status"] == "SHIPPED" and row["currency"] == "EUR" and row["total_value"] == 10.5 and row["effective_from"] == "2026-01-01" and row["effective_to"] is None
    assert row["priority"] is None and row["customer_id"] == "CUS-1"
    assert (row["data_status"], row["source_type"], row["source_record_id"]) == ("SOURCE_DERIVED", "OEM_MASTER", "ORD-1")
    loc = graph_row("locations", {"modes": "SEA|AIR"}, location_id="L", graph_label="Location", location_kind="PORT")
    assert loc["modes"] == ["SEA", "AIR"] and graph_row("locations", {}, location_id="L")["modes"] == []


def test_a_graph_value_that_the_registry_does_not_map_is_still_read_by_its_own_name():
    assert graph_row("tracking_events", {"effective_to": "2027-01-01"})["effective_to"] == "2027-01-01"


class StubGraph:
    def __init__(self, shipment_row: dict[str, Any]) -> None:
        self.row = shipment_row

    def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        assert "MERGE" not in query and "SET " not in query
        return [self.row]


def ship_row(lines: list[str]) -> dict[str, Any]:
    return {"p": {"shipment_id": "S1", "shipment_status": "SHIPPED", "data_status": "SYNTHETIC_DEMO"}, "order_id": "O1", "order_line_ids": lines, "route_rel": None, "origin": "W1",
            "destination": None, "carrier": "Demo Freight (fictional)", "carrier_id": "CAR-1"}


def test_the_shipment_carrier_id_is_read_from_the_carrier_relationship():
    s = LogisticsGraphReader(StubGraph(ship_row(["OL-1"]))).shipment("S1")
    assert s["carrier_id"] == "CAR-1" and s["carrier"] == "Demo Freight (fictional)" and s["order_line_id"] == "OL-1"
    assert set(s) == set(BY_NAME["shipments"].model.model_fields) - {"ingestion_timestamp"}


def test_a_shipment_that_ships_several_lines_does_not_get_one_of_them_chosen_for_it():
    assert LogisticsGraphReader(StubGraph(ship_row(["OL-1", "OL-2"]))).shipment("S1")["order_line_id"] is None
    assert LogisticsGraphReader(StubGraph(ship_row([]))).shipment("S1")["order_line_id"] is None


# ── the mapping audit leaves nothing out ─────────────────────────────────────────────────────────
def test_the_mapping_audit_has_a_row_for_every_canonical_field_and_no_unmapped_business_field():
    rows = A.audit()
    for dataset in A.READER_DATASETS:
        fields = {r["canonical_field"] for r in rows if r["dataset"] == dataset}
        assert fields == set(BY_NAME[dataset].model.model_fields) - {"ingestion_timestamp"}, dataset
    assert {r["classification"] for r in rows} <= {"BUSINESS_FIELD", "PROVENANCE_FIELD", "RELATIONSHIP_FIELD", "NOT_APPLICABLE"}
    assert [r for r in rows if r["status"] == "MISSING"] == []


def test_route_legs_join_the_relationship_record_to_the_leg_node():
    row = {"p": {"leg_id": "LEG-1", "from_id": "A", "to_id": "B", "mode": "SEA", "leg_status": "PLANNED", "distance_km": 10.0},
           "hp": {"rel_id": "HAS_LEG:R1>LEG-1", "sequence": 1, "data_status": "SYNTHETIC_DEMO", "source_record_id": "x", "effective_from": "2026-01-01"}, "sequence": 1}
    legs = LogisticsGraphReader(StubGraph(row)).legs("R1")
    assert legs[0]["route_leg_id"] == "R1>LEG-1" and legs[0]["leg_id"] == "LEG-1" and legs[0]["origin_location_id"] == "A" and legs[0]["transport_mode"] == "SEA"
    assert legs[0]["effective_from"] == "2026-01-01" and legs[0]["source_record_id"] == "x" and legs[0]["sequence"] == 1


def test_a_network_leg_relationship_id_is_read_as_the_canonical_route_leg_id():
    assert LogisticsGraphReader._leg_id({"rel_id": "HAS_LEG:R1:LEG-1"}, "R1", "LEG-1") == "R1>LEG-1"
    assert LogisticsGraphReader._leg_id({"rel_id": "HAS_LEG:SEED-LEG-7"}, "R1", "LEG-7") == "SEED-LEG-7"


def test_the_report_lists_every_failing_difference_even_when_normalisation_ones_exceed_the_cap():
    import commerce_live_validate as V

    r = L.DatasetResult("x")
    for i in range(V.NORMALISATION_LIST_CAP + 50):
        r.add(f"R{i}", "f", [], None, L.NORMALIZATION_ONLY, "EMPTY_EQUIVALENT", False)
    r.add("R-bad", "g", "a", "b", L.VALUE_MISMATCH, None, False)
    listed = V.listed_differences(r)
    assert listed[0]["record_id"] == "R-bad" and len(listed) == V.NORMALISATION_LIST_CAP + 1
