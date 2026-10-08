"""Location coordinate review: export completeness, protected separation, the geography resolver, and that the review writes nothing.
Offline tests use a stub graph; the live ones (read-only) skip when Neo4j is unreachable."""
from __future__ import annotations

import copy
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commerce_validation_lib as L  # noqa: E402
import location_reconciliation as R  # noqa: E402

from app.canonical import geography as G  # noqa: E402
from app.canonical.export import Exporter  # noqa: E402
from app.canonical.io import CANON_DIR  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.logistics.readers import FileReader  # noqa: E402

live = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


# ── export completeness ──────────────────────────────────────────────────────────────────────────
class StubGraph:
    def __init__(self, locations: list[dict[str, Any]]) -> None:
        self.locations = locations

    def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        assert "MERGE" not in query and "DELETE" not in query and "SET " not in query
        return [{"p": p} for p in self.locations] if "MATCH (l:Location)" in query else []


def export_locations(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["location_id"]: r for r in Exporter(graph=StubGraph(nodes)).locations()}


def city(i: str, name: str, **kw: Any) -> dict[str, Any]:
    return {"location_id": i, "name": name, "location_type": "CITY", "country_code": "AT", "data_status": "SYNTHETIC_DEMO", "source_id": "SRC-005", **kw}


def test_a_coordinate_the_graph_holds_is_exported_with_its_own_geo_basis():
    out = export_locations([city("LOC-AT-GRAZ", "Graz", latitude=47.07, longitude=15.44, geo_basis="APPROX_CITY_CENTRE")])["LOC-AT-GRAZ"]
    assert (out["latitude"], out["longitude"], out["geo_basis"]) == (47.07, 15.44, "APPROX_CITY_CENTRE")


def test_the_graphs_own_coordinate_wins_over_the_reference_city_centre():
    assert "Assen" in G.reference()["city_coordinates"]
    out = export_locations([city("LOC-X", "Assen", latitude=1.5, longitude=2.5, geo_basis="APPROX_CITY_CENTRE")])["LOC-X"]
    assert (out["latitude"], out["longitude"], out["geo_basis"]) == (1.5, 2.5, "APPROX_CITY_CENTRE")


def test_a_city_the_graph_has_no_coordinates_for_still_takes_the_reference_city_centre_and_is_labelled_so():
    out = export_locations([city("LOC-ASSEN", "Assen", data_status="SOURCE_DERIVED")])["LOC-ASSEN"]
    assert out["geo_basis"] == "REFERENCE_CITY_CENTRE" and out["latitude"] == G.reference()["city_coordinates"]["Assen"][0]


def test_no_coordinate_is_invented_for_a_city_without_graph_or_reference_coordinates():
    out = export_locations([city("LOC-NOWHERE", "Nowhereville")])["LOC-NOWHERE"]
    assert (out["latitude"], out["longitude"], out["geo_basis"]) == (None, None, None)


@live
def test_every_graph_coordinate_that_should_be_exported_appears_in_the_canonical_files():
    report = R.run()
    assert report["counts"].get("EXPORTER_OMISSION", 0) == 0 and report["counts"].get("GRAPH_ONLY", 0) == 0 and report["counts"].get("CONFLICT", 0) == 0
    # what remains is canonical-only and protected: exactly the three supplied cities and the three plants, never anything else
    assert {r["location_id"] for r in report["records"]} == {"LOC-ASSEN", "LOC-COEVORDEN", "LOC-LINGEN", "PLT-001", "PLT-002", "PLT-003"}
    assert all(r["classification"] == "CANONICAL_ONLY" and r["protected"] for r in report["records"])


# ── reconciliation classification ────────────────────────────────────────────────────────────────
def test_classification_covers_every_case():
    cities = {"Assen"}
    canon = {"latitude": 1.0, "longitude": 2.0, "geo_basis": "X", "country": None, "region": None, "timezone": None, "location_type": None}
    graph_same = {"latitude": 1.0, "longitude": 2.0, "geo_basis": "X"}
    assert R.classify(canon, graph_same, "Location", cities)[0] == "MATCH"
    assert R.classify(canon, {}, "Location", cities)[0] == "CANONICAL_ONLY"
    assert R.classify({**canon, "latitude": None, "longitude": None, "geo_basis": None}, graph_same, "Location", cities)[0] == "GRAPH_ONLY"
    assert R.classify({**canon, "latitude": None, "longitude": None, "geo_basis": None}, {**graph_same, "location_type": "CITY", "name": "Graz"}, "Location", cities)[0] == "EXPORTER_OMISSION"
    assert R.classify(canon, {**graph_same, "latitude": 9.0}, "Location", cities) == ("CONFLICT", ["latitude"])


# ── protected separation and overlay resolution ──────────────────────────────────────────────────
def test_the_protected_records_own_fields_are_never_filled_in_by_the_overlay():
    class Reader:
        def location(self, i: str) -> dict[str, Any]:
            return {"location_id": i, "name": "Assen", "graph_label": "Location", "country_code": "NL", "latitude": None, "longitude": None, "geo_basis": None, "country": None,
                    "region": None, "timezone": None, "location_type": None, "data_status": "SOURCE_DERIVED", "source_type": "OEM_MASTER", "source_record_id": "LOC-ASSEN"}

    out = G.resolve_location_context("LOC-ASSEN", reader=Reader())
    assert out["protected"] is True
    assert out["location"] == {f: None for f in G.FIELDS}  # the record is exactly what the reader returned
    assert out["resolved"]["latitude"] == G.reference()["city_coordinates"]["Assen"][0] and out["resolved"]["timezone"] == "Europe/Amsterdam" and out["resolved"]["country"] == "Netherlands"
    assert out["field_sources"]["latitude"] == "GEOGRAPHY_REFERENCE" and out["field_sources"]["country"] == "GEOGRAPHY_REFERENCE"
    assert out["coordinate_class"] == "REFERENCE" and out["provenance"]["geography_profile"]["data_status"] == "REFERENCE"
    assert out["provenance"]["location"]["data_status"] == "SOURCE_DERIVED"


def test_the_overlay_fills_only_what_the_record_leaves_empty():
    class Reader:
        def location(self, i: str) -> dict[str, Any]:
            return {"location_id": i, "name": "Assen", "graph_label": "Location", "country_code": "NL", "latitude": 52.99, "longitude": 6.56, "geo_basis": "APPROX_CITY_CENTRE",
                    "country": "The Netherlands (record)", "region": None, "timezone": None, "location_type": "CITY", "data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO"}

    out = G.resolve_location_context("X", reader=Reader())
    assert (out["resolved"]["latitude"], out["field_sources"]["latitude"]) == (52.99, "LOCATION")  # the record's own coordinate is kept, not the reference one
    assert (out["resolved"]["country"], out["field_sources"]["country"]) == ("The Netherlands (record)", "LOCATION")
    assert (out["resolved"]["region"], out["field_sources"]["region"]) == ("EUROPE", "GEOGRAPHY_REFERENCE")
    assert out["coordinate_class"] == "SYNTHETIC_DEMO"


def test_a_plant_gets_its_logistics_type_from_its_label_and_a_dealer_none_it_does_not_have():
    out = G.resolve_location_context("PLT-001", reader=FileReader(CANON_DIR))
    assert out["resolved"]["logistics_type"] == "PLANT" and out["resolved"]["country"] == "Netherlands" and out["resolved"]["timezone"] == "Europe/Amsterdam"
    assert G.resolve_location_context("NO-SUCH-PLACE", reader=FileReader(CANON_DIR)) == {"location_id": "NO-SUCH-PLACE", "found": False}


def test_nothing_is_guessed_for_an_unknown_country():
    assert G.country_profile("ZZ") == {"country": None, "region": None, "timezone": None}
    assert G.country_profile("US", "Houston")["timezone"] == "America/Chicago"


def test_coordinate_quality_is_stated_never_called_verified():
    assert G.coordinate_class("SOURCE_DERIVED", "APPROX_CITY_CENTRE") == "SOURCE_DERIVED" and G.coordinate_class("SYNTHETIC_DEMO", "APPROX_CITY_CENTRE") == "SYNTHETIC_DEMO"
    assert G.coordinate_class("SOURCE_DERIVED", "REFERENCE_CITY_CENTRE") == "REFERENCE" and G.coordinate_class("USER_PROVIDED", "X") == "USER_PROVIDED" and G.coordinate_class("REAL", None) is None
    assert "VERIFIED" not in json.dumps([G.coordinate_class(s, "X") for s in ("REAL", "DERIVED", "SYNTHETIC_DEMO", "USER_PROVIDED")])


def test_the_resolver_is_the_one_place_geography_reference_is_read():
    app = Path(__file__).resolve().parents[1] / "app"
    readers = [p.relative_to(app).as_posix() for p in app.rglob("*.py") if "geography.json" in p.read_text(encoding="utf-8")]
    assert sorted(readers) == ["canonical/geography.py", "canonical/network.py", "core/geography.py"]  # network.py: author-time expansion; core/geography.py: a docstring


# ── no mutation ──────────────────────────────────────────────────────────────────────────────────
@live
def test_the_location_review_changes_nothing_in_the_graph():
    g = R.GraphClient(dataclasses.replace(get_settings(), neo4j_query_timeout=120.0))
    try:
        src = L.CypherSource(L.ReadOnlyGraph(g))
        before = src.snapshot()
        R.run()
        after = src.snapshot()
    finally:
        g.close()
    keep = ("node_count", "relationship_count", "protected_node_count", "protected_relationship_count", "integrity_checksum", "src_canon_graph_fingerprint", "label_counts", "relationship_type_counts")
    assert {k: before[k] for k in keep} == {k: after[k] for k in keep}


def test_the_reconciliation_and_resolver_sources_contain_no_write_operation():
    for name in ("scripts/location_reconciliation.py", "app/canonical/geography.py"):
        text = (Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8")
        assert not any(w in text.upper() for w in ("MERGE ", "DETACH DELETE", " SET N.", "CREATE (", "CREATE CONSTRAINT"))


def test_the_exporter_change_touches_only_coordinate_fields():
    base = copy.deepcopy(export_locations([city("LOC-A", "Graz", latitude=1.0, longitude=2.0, geo_basis="B")])["LOC-A"])
    without = export_locations([city("LOC-A", "Graz")])["LOC-A"]
    assert {k for k in base if base[k] != without[k]} == {"latitude", "longitude", "geo_basis"}
