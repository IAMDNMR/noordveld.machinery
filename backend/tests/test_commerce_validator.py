"""Tests of the live-validation harness itself (scripts/commerce_live_validate.py and scripts/commerce_validation_lib.py). They run against an in-memory twin of the canonical files,
a recording fake graph and monkeypatched connectivity, so they need no database. Nothing here validates Neo4j; tests/test_commerce_live.py does that and skips when it is unreachable."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commerce_live_validate as V  # noqa: E402
import commerce_validation_lib as L  # noqa: E402

from app.canonical.io import CANON_DIR  # noqa: E402
from app.commerce.engine import CommerceContextEngine  # noqa: E402
from app.core.exceptions import GraphUnavailableError  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def twin() -> L.MemorySource:
    return L.MemorySource.from_files(CANON_DIR)


def failing(r: L.DatasetResult) -> list[dict]:
    """The differences that are not an approved normalisation."""
    return [d for d in r.differences if d["difference_type"] in L.FAILING]


def one(results: list[L.DatasetResult], name: str) -> L.DatasetResult:
    return next(r for r in results if r.dataset == name)


@pytest.fixture(scope="module")
def offline_report() -> dict:
    return V.build_report(argparse.Namespace(offline=True, full_detail=False, out=None))


# ── entity counts ────────────────────────────────────────────────────────────────────────────────
REQUIRED_ENTITIES = ["Part", "Machine", "MachineInstance", "Category", "PartSpecification", "Fitment (FITS relationship)", "FitmentContext", "ApprovedSource (APPROVED_SOURCE relationship)", "Supplier", "Dealer",
                     "Plant", "Location", "Customer", "Order", "OrderLine", "Inventory (AVAILABLE_AT relationship)", "Pricing (Price)", "Route (TransportRoute)", "RouteLeg (TransportLeg)", "Shipment",
                     "TrackingEvent", "Technician", "WorkOrder", "InstallationEvent", "ReplacementEvent", "WarrantyPolicy", "WarrantyClaim", "Evidence", "FeaturedScenario"]


def test_entity_counts_cover_every_required_entity_with_canonical_graph_difference_and_status():
    rows = L.entity_counts(twin())
    assert [r["entity"] for r in rows] == REQUIRED_ENTITIES
    for r in rows:
        assert set(r) >= {"entity", "canonical_count", "graph_count", "difference", "status"} and r["canonical_count"] > 0
        assert r["difference"] == r["graph_count"] - r["canonical_count"] and r["status"] == "PASS", r
    by = {r["entity"]: r for r in rows}
    assert by["Part"]["canonical_count"] == 100 and by["Machine"]["canonical_count"] == 15


def test_a_missing_or_extra_graph_record_fails_its_entity_and_names_the_ids():
    m = twin()
    del m.n[("Part", "part_id")]["PRT-007"]
    m.n[("Machine", "machine_id")]["MCH-999"] = {"machine_id": "MCH-999", "data_status": "SYNTHETIC_DEMO"}
    by = {r["entity"]: r for r in L.entity_counts(m)}
    assert by["Part"]["status"] == "FAIL" and by["Part"]["missing_in_graph"] == ["PRT-007"] and by["Part"]["difference"] == -1
    assert by["Machine"]["status"] == "FAIL" and by["Machine"]["missing_in_canonical"] == ["MCH-999"]


def test_equal_counts_cannot_hide_a_swapped_record():
    m = twin()
    m.n[("Part", "part_id")]["PRT-XXX"] = m.n[("Part", "part_id")].pop("PRT-007")
    r = {e["entity"]: e for e in L.entity_counts(m)}["Part"]
    assert r["canonical_count"] == r["graph_count"] == 100 and r["status"] == "FAIL" and r["missing_in_graph"] == ["PRT-007"] and r["missing_in_canonical"] == ["PRT-XXX"]


def test_operational_records_written_by_the_app_are_counted_apart_and_never_hide_a_mismatch():
    m = twin()
    m.app_nodes["Order"] = 7
    by = {e["entity"]: e for e in L.entity_counts(m)}
    assert by["Order"]["graph_app_written"] == 7 and by["Order"]["status"] == "PASS" and "APP-SESSION" in by["Order"]["note"]


def test_a_dealer_or_supplier_node_counts_as_a_location_only_when_used_as_a_place():
    m = twin()
    m.n[("Supplier", "supplier_id")]["SUP-PLAIN"] = {"supplier_id": "SUP-PLAIN", "data_status": "SYNTHETIC_DEMO"}  # a supplier that is not a place
    assert {e["entity"]: e for e in L.entity_counts(m)}["Location"]["status"] == "PASS"


# ── field-level comparison ───────────────────────────────────────────────────────────────────────
def test_a_perfect_twin_has_zero_differences_in_every_dataset():
    results = L.compare_datasets(twin()) + L.compare_supplied_relationships(twin())
    assert all(r.status() == "PASS" for r in results) and sum(r.records for r in results) > 15000
    assert {r.dataset for r in results} >= {"parts", "machines", "shipments", "network_shipments", "warranty_claims", "evidence", "protected:FITS_relationship", "protected:part_search_aliases"}


def test_canonical_value_not_equal_graph_value_reports_the_exact_dataset_record_field_and_both_values():
    m = twin()
    m.n[("Shipment", "shipment_id")]["SHP-NET-0001"]["shipment_status"] = "DELIVERED"
    r = one(L.compare_datasets(m, names=["network_shipments"]), "network_shipments")
    assert r.status() == "FAIL" and r.field_mismatches == 1
    assert failing(r) == [{"dataset": "network_shipments", "record_id": "SHP-NET-0001", "field": "Shipment.shipment_status", "canonical_value": "IN_TRANSIT", "graph_value": "DELIVERED",
                              "difference_type": "VALUE_MISMATCH"}]


def test_a_value_the_graph_lacks_is_missing_in_graph_and_a_value_only_the_graph_has_is_missing_in_canonical():
    m = twin()
    m.n[("Shipment", "shipment_id")]["SHP-NET-0001"].pop("route_id")
    m.n[("Part", "part_id")]["PRT-007"]["part_number"], m.n[("Part", "part_id")]["PRT-007"]["name"] = None, "Piston pump, variable displacement"
    ship = one(L.compare_datasets(m, names=["network_shipments"]), "network_shipments")
    assert failing(ship) == [{"dataset": "network_shipments", "record_id": "SHP-NET-0001", "field": "Shipment.route_id", "canonical_value": "RTE-NET-JPNL-SEA-ECO", "graph_value": None,
                                 "difference_type": "MISSING_IN_GRAPH"}]
    c = L.classify(None, "x")
    assert c == (L.MISSING_IN_CANONICAL, None)


def test_a_record_missing_from_the_graph_and_a_graph_record_no_canonical_row_names():
    m = twin()
    del m.n[("Shipment", "shipment_id")]["SHP-NET-0002"]
    m.n[("Shipment", "shipment_id")]["SHP-NET-9999"] = {"shipment_id": "SHP-NET-9999", "canonical_dataset": "network_shipments", "data_status": "SYNTHETIC_DEMO"}
    r = one(L.compare_datasets(m, names=["network_shipments"]), "network_shipments")
    kinds = {(d["record_id"], d["field"], d["difference_type"]) for d in failing(r)}
    assert ("SHP-NET-0002", "<record>", "MISSING_IN_GRAPH") in kinds and ("SHP-NET-9999", "<record>", "MISSING_IN_CANONICAL") in kinds
    assert r.missing_in_graph >= 1 and r.missing_in_canonical == 1 and r.status() == "FAIL"


def test_a_missing_relationship_edge_is_reported_for_the_record_that_needs_it():
    m = twin()
    del m.r[("USES_ROUTE", "Shipment", "TransportRoute")][("SHP-NET-0001", "RTE-NET-JPNL-SEA-ECO")]
    r = one(L.compare_datasets(m, names=["network_shipments"]), "network_shipments")
    assert [(d["record_id"], d["field"], d["difference_type"]) for d in failing(r)] == [("SHP-NET-0001", "edge:USES_ROUTE", "MISSING_IN_GRAPH")]


def test_provenance_is_compared_not_ignored():
    m = twin()
    m.n[("WarrantyClaim", "claim_id")]["CLM-G001"]["data_status"] = "REAL"
    r = one(L.compare_datasets(m, names=["warranty_claims"]), "warranty_claims")
    assert [(d["record_id"], d["field"], d["canonical_value"], d["graph_value"]) for d in failing(r)] == [("CLM-G001", "WarrantyClaim.data_status", "SYNTHETIC_DEMO", "REAL")]


def test_a_relationship_dataset_property_difference_is_found():
    m = twin()
    key = next(iter(m.r[("AVAILABLE_AT", "Part", "Warehouse")]))
    m.r[("AVAILABLE_AT", "Part", "Warehouse")][key]["available"] = 9999
    r = one(L.compare_datasets(m, names=["inventory"]), "inventory")
    assert r.field_mismatches == 1 and failing(r)[0]["field"] == "AVAILABLE_AT.available" and failing(r)[0]["graph_value"] == 9999


# ── normalization ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("canonical,graph,expected,rule", [
    ("a", "a", L.MATCH, None), (None, None, L.MATCH, None), ([], None, L.NORMALIZATION_ONLY, "EMPTY_EQUIVALENT"), ("", None, L.NORMALIZATION_ONLY, "EMPTY_EQUIVALENT"),
    (["b", "a"], ["a", "b"], L.NORMALIZATION_ONLY, "LIST_ORDER"), (["a"], ["a", "b"], L.VALUE_MISMATCH, None), (5, 5.0, L.NORMALIZATION_ONLY, "NUMERIC_TYPE"),
    (0.1 + 0.2, 0.3, L.NORMALIZATION_ONLY, "NUMERIC_TOLERANCE"), (5, 6, L.VALUE_MISMATCH, None), ("5", 5, L.TYPE_MISMATCH, None), (True, "true", L.TYPE_MISMATCH, None),
    ("2026-10-01", "2026-10-01T00:00:00", L.NORMALIZATION_ONLY, "DATE_REPRESENTATION"), ("2026-10-01", "2026-10-02T00:00:00", L.VALUE_MISMATCH, None),
    ("2026-10-01T10:00:00Z", "2026-10-01 10:00:00+00:00", L.NORMALIZATION_ONLY, "TIMESTAMP_FORMAT"), ("2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z", L.VALUE_MISMATCH, None),
    ("NL", "nl", L.VALUE_MISMATCH, None), ("x", None, L.MISSING_IN_GRAPH, None), (None, "x", L.MISSING_IN_CANONICAL, None), ("Alpha", "Beta", L.VALUE_MISMATCH, None),
])
def test_value_classification(canonical, graph, expected, rule):
    assert L.classify(canonical, graph) == (expected, rule)


def test_country_code_case_and_specification_name_casefold_are_named_rules_only_where_approved():
    assert L.classify("NL", "nl", "country_code") == (L.NORMALIZATION_ONLY, "COUNTRY_CODE_CASE")
    assert L.classify("Bore  63", "bore 63", "name", casefold=True) == (L.NORMALIZATION_ONLY, "SPEC_NAME_CASEFOLD")
    assert L.classify("Bore 63", "bore 63", "name") == (L.VALUE_MISMATCH, None)  # no casefold rule for a field that does not have one


def test_protected_data_allows_only_order_and_numeric_type_rules():
    for rule_input in (([], None), ("2026-10-01", "2026-10-01T00:00:00"), ("2026-10-01T10:00:00Z", "2026-10-01 10:00:00+00:00")):
        assert L.classify(*rule_input, protected=True)[0] == L.VALUE_MISMATCH or L.classify(*rule_input, protected=True)[0] == L.MISSING_IN_GRAPH
    assert L.classify("NL", "nl", "country_code", protected=True)[0] == L.VALUE_MISMATCH
    assert L.classify(["b", "a"], ["a", "b"], protected=True) == (L.NORMALIZATION_ONLY, "LIST_ORDER")
    assert L.classify(5, 5.0, protected=True) == (L.NORMALIZATION_ONLY, "NUMERIC_TYPE")
    assert set(L.PROTECTED_ALLOWED_RULES) <= set(L.RULES)


def test_every_applied_rule_is_reported_with_its_count_and_there_is_no_catch_all():
    results = L.compare_datasets(twin()) + L.compare_supplied_relationships(twin())
    rep = L.normalization_report(results)
    assert rep["ignored_difference_count"] == sum(a["count"] for a in rep["normalization_rules_applied"]) > 0
    assert {a["rule"] for a in rep["normalization_rules_applied"]} <= set(L.RULES) and all(a["description"] and a["datasets"] for a in rep["normalization_rules_applied"])
    assert "ignored" not in {a["rule"].lower() for a in rep["normalization_rules_applied"]} and "catch-all" in rep["not_ignored"] or "no catch-all" in rep["not_ignored"].lower()
    assert all(r.unexplained == 0 for r in results)  # a normalisation is never counted as a mismatch, and a mismatch never as a normalisation


def test_an_unapproved_difference_in_a_normalisation_field_is_still_a_mismatch():
    m = twin()
    m.n[("Part", "part_id")]["PRT-007"]["name"] = "piston pump, variable displacement"  # case-only difference on a protected Part: no rule allows it
    r = one(L.compare_datasets(m, names=["parts"]), "parts")
    assert r.status() == "FAIL" and failing(r)[0]["difference_type"] == "VALUE_MISMATCH"


# ── protected comparison ─────────────────────────────────────────────────────────────────────────
def test_protected_catalogue_drift_is_reported_in_the_protected_section():
    m = twin()
    m.n[("Machine", "machine_id")]["MCH-009"]["model_code"] = "KFT-601"
    m.fits_[0]["props"]["fitment_status"] = "CONDITIONAL"
    m.categories["PRT-097"] = ("CAT-01", m.categories["PRT-097"][1])
    m.aliases["PRT-097"] = ["something else"]
    res = L.compare_datasets(m, names=["machines"]) + L.compare_supplied_relationships(m)
    by = {r.dataset: r for r in res}
    assert by["machines"].status() == "FAIL" and by["machines"].protected and failing(by["machines"])[0]["graph_value"] == "KFT-601"
    assert by["protected:FITS_relationship"].status() == "FAIL" and by["protected:part_category_links"].status() == "FAIL" and by["protected:part_search_aliases"].status() == "FAIL"
    assert failing(by["protected:part_category_links"])[0]["record_id"] == "PRT-097"


def test_the_report_has_a_protected_comparison_for_the_supplied_catalogue(offline_report):
    names = {d["dataset"] for d in offline_report["protected_comparison"]}
    assert names >= {"machines", "parts", "categories", "specifications", "plants", "legacy_part_mappings", "protected:FITS_relationship", "protected:part_search_aliases"} and all(d["protected"] for d in offline_report["protected_comparison"])


# ── snapshot, mutation and read-only ─────────────────────────────────────────────────────────────
def test_the_twin_snapshot_has_every_required_measure_and_is_stable():
    a, b = twin().snapshot(), twin().snapshot()
    assert a == b and {"node_count", "relationship_count", "protected_node_count", "protected_relationship_count", "integrity_checksum", "src_canon_graph_fingerprint", "label_counts",
                       "relationship_type_counts"} <= set(a)
    assert a["label_counts"]["Part"] == 100 and a["node_count"] == sum(a["label_counts"].values())


def test_a_changed_graph_changes_the_snapshot_and_fails_the_unchanged_criteria():
    m = twin()
    s0 = m.snapshot()
    m.n[("Part", "part_id")]["PRT-001"]["name"] = "tampered"
    s1 = m.snapshot()
    m.n[("Customer", "customer_id")]["CUS-NEW"] = {"customer_id": "CUS-NEW", "data_status": "SYNTHETIC_DEMO"}
    s2 = m.snapshot()
    assert s0["integrity_checksum"] != s1["integrity_checksum"] and s1["node_count"] != s2["node_count"] and s0["src_canon_graph_fingerprint"] != s1["src_canon_graph_fingerprint"]
    det = V.determinism({}, {}, s0, s1, s2)
    assert det["snapshot_identical"] is False and {"integrity_checksum", "node_count"} <= set(det["snapshot_changes"])
    conn = {"dns_resolved": True, "tcp_reachable": True, "authentication": "ok", "database_reachable": True, "host": "h"}
    crit = {c["criterion"]: c["status"] for c in V.acceptance("ONLINE", conn, {k: [] for k in ("entity_counts", "dataset_comparison", "protected_comparison", "discovery", "logistics", "warranty", "authorization", "apis", "golden", "evidence", "provenance")} | {"engine_files_vs_graph": {"different": {}}}, det, [s0, s1, s2], None)}
    assert crit["snapshot unchanged (before == after pass 1 == after pass 2)"] == "FAIL" and crit["integrity checksum unchanged"] == "FAIL" and crit["fingerprint unchanged"] == "FAIL"


class RecordingGraph:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def read(self, query: str, **params):
        self.sent.append(query)
        return [{"n": 0, "l": "Label", "t": "TYPE"}] if "count(" in query else []

    def close(self) -> None:
        pass


def test_the_guard_refuses_every_kind_of_write_before_it_is_sent():
    g = RecordingGraph()
    ro = L.ReadOnlyGraph(g)
    for q in ("CREATE (n:X)", "MATCH (n) SET n.a = 1", "MATCH (n) DETACH DELETE n", "MERGE (n:X {id: 1})", "MATCH (n) REMOVE n.a", "CALL db.clearQueryCaches()", "LOAD CSV FROM 'x' AS r RETURN r",
              "MATCH (n) FOREACH (x IN [1] | CREATE (:Y))", "match (n) set n.a = 1", "DROP INDEX i"):
        with pytest.raises(L.WriteAttempt):
            ro.read(q)
    assert g.sent == [] and len(ro.blocked) == 10 and not hasattr(ro, "write") and not hasattr(ro, "transaction")
    assert ro.read("MATCH (n:Part {name: 'SET it'}) RETURN count(n) AS n")[0]["n"] == 0  # a write word inside a string literal is data


def test_everything_the_validator_asks_of_the_graph_is_a_read_query():
    """Every Cypher statement the validator, the engine's graph readers and the exporter can send, captured with a recording graph, passes the read-only guard."""
    g = RecordingGraph()
    ro = L.ReadOnlyGraph(g)
    src = L.CypherSource(ro)
    from audit_before import source_checksum  # noqa: F401  (the checksum helper is imported by the snapshot; its queries are the constants below)

    src.snapshot()
    src.nodes("Part", "part_id", ["PRT-001"]), src.rels("FITS", ("Part", "part_id"), ("Machine", "machine_id"), [("a", "b")]), src.resolve("location", ["WH-001"])
    src.node_ids("Dealer", "dealer_id", dataset="locations", exclude_app=True, require_property="logistics_type"), src.app_written("Order"), src.rel_ids("FITS", "fitment")
    src.part_aliases(), src.part_categories(), src.fits(), src.supplied_by()
    engine = CommerceContextEngine.from_graph(ro)
    for ds in ("machines", "parts", "categories", "fitment", "approved_sources", "inventory", "pricing", "locations", "customers"):
        engine.discovery._rows(ds)
    engine.build_logistics_context(shipment_id="SHP-X")
    engine.build_warranty_context(claim_id="CLM-X")
    engine.build_warranty_context(machine_instance_id="MI-X", part_id="PRT-X")
    from audit_before import NODE_QUERY, REL_QUERY
    L.assert_read_only(NODE_QUERY), L.assert_read_only(REL_QUERY)
    assert len(g.sent) > 40 and ro.blocked == [] and ro.queries == len(g.sent)


def test_the_validator_sources_contain_no_write_operation():
    for name in ("commerce_live_validate.py", "commerce_validation_lib.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', "", text)
        assert not re.search(r"\.write\(|execute_write|WRITE_ACCESS|\.transaction\(|Neo4jStore|upsert_|ensure_constraint|\.run\(", code), name
        for q in re.findall(r'f?"((?:MATCH|UNWIND|RETURN)[^"]*)"', code):
            L.assert_read_only(q)


# ── connectivity: unreachable, blocked, authentication ───────────────────────────────────────────
class Settings:
    graph_configured = True
    neo4j_uri = "neo4j+s://does-not-exist.invalid"


def test_unreachable_neo4j_stops_at_dns_and_the_later_steps_are_not_tested(monkeypatch):
    c = L.connectivity(Settings())
    assert c["host"] == "does-not-exist.invalid" and c["dns_resolved"] is False and c["tcp_reachable"] is False and c["authentication"] == "not_tested" and c["database_reachable"] is False
    assert "password" not in json.dumps(c).lower()


def test_unconfigured_neo4j_is_reported_as_such():
    class Off:
        graph_configured = False
        neo4j_uri = ""

    assert L.connectivity(Off())["error_class"] == "NotConfigured"


def _patch_network(monkeypatch, auth_error: str | None):
    monkeypatch.setattr(L.socket, "gethostbyname", lambda h: "10.0.0.1")
    monkeypatch.setattr(L.socket, "create_connection", lambda *a, **k: type("S", (), {"close": lambda self: None})())

    class G:
        def read(self, q, **p):
            if auth_error:
                raise GraphUnavailableError(auth_error)
            return [{"ok": 1}]

        def close(self):
            pass

    return lambda: G()


def test_authentication_failure_is_distinguished_from_an_unreachable_host(monkeypatch):
    c = L.connectivity(Settings(), _patch_network(monkeypatch, "AuthError"))
    assert (c["dns_resolved"], c["tcp_reachable"], c["authentication"], c["database_reachable"], c["error_class"]) == (True, True, "failed", False, "AuthError")
    c2 = L.connectivity(Settings(), _patch_network(monkeypatch, "ServiceUnavailable"))
    assert c2["authentication"] == "not_tested" and c2["database_reachable"] is False
    ok = L.connectivity(Settings(), _patch_network(monkeypatch, None))
    assert (ok["authentication"], ok["database_reachable"]) == ("ok", True)


@pytest.mark.parametrize("conn,reason", [({"configured": True, "dns_resolved": False, "tcp_reachable": False, "authentication": "not_tested", "database_reachable": False}, "DNS does not resolve"),
                                         ({"configured": True, "dns_resolved": True, "tcp_reachable": False, "authentication": "not_tested", "database_reachable": False}, "TCP connection failed"),
                                         ({"configured": True, "dns_resolved": True, "tcp_reachable": True, "authentication": "failed", "database_reachable": False}, "authentication failed")])
def test_a_run_that_cannot_reach_neo4j_is_blocked_with_the_reason_and_never_a_pass(monkeypatch, tmp_path, conn, reason):
    monkeypatch.setattr(V.L, "connectivity", lambda s: {"host": "h", "port": 7687, "scheme": "neo4j+s", **conn})
    out = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(out)])
    assert V.main() == 2
    r = json.loads(out.read_text())
    assert r["mode"] == "ONLINE" and r["live_graph_verified"] is False and r["final_classification"] == "PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE"
    assert r["final_classification_detail"]["reason"] == reason and all(a["status"] in ("PASS", "BLOCKED") for a in r["acceptance"])
    assert [a["status"] for a in r["acceptance"] if a["criterion"] in ("DNS resolves", "database reachable")] != ["PASS", "PASS"]
    assert r["entity_counts"] == [] and r["dataset_comparison"] == []  # nothing was invented


def test_a_live_failure_is_a_fail_not_an_environment_problem():
    conn = {"dns_resolved": True, "tcp_reachable": True, "authentication": "ok", "database_reachable": True, "host": "h"}
    p = {k: [] for k in ("entity_counts", "dataset_comparison", "protected_comparison", "discovery", "logistics", "warranty", "authorization", "apis", "golden", "evidence", "provenance")}
    p["engine_files_vs_graph"] = {"different": {}}
    p["dataset_comparison"] = [{"status": "FAIL"}]
    snap = {"integrity_checksum": "a", "src_canon_graph_fingerprint": "b", "node_count": 1}
    det = {"business_results_identical": True, "snapshot_identical": True}
    crit = V.acceptance("ONLINE", conn, p, det, [snap, snap, snap], L.ReadOnlyGraph(RecordingGraph()))
    res = V.classify_run("ONLINE", conn, crit)
    assert res["result"] == "FAIL" and res["phase_4h"] == "PHASE 4H FAILED — LIVE VALIDATION FOUND PRODUCT/DATA ISSUES" and "field comparison has zero unexplained mismatches" in res["reason"]
    p["dataset_comparison"] = []
    assert V.classify_run("ONLINE", conn, V.acceptance("ONLINE", conn, p, det, [snap, snap, snap], L.ReadOnlyGraph(RecordingGraph())))["phase_4h"] == "PHASE 4H COMPLETE"
    blocked = V.acceptance("ONLINE", conn, p, det, [snap, snap, snap], L.ReadOnlyGraph(RecordingGraph()))
    assert all(c["status"] == "PASS" for c in blocked)


# ── the report: schema, offline mode, determinism ────────────────────────────────────────────────
REPORT_KEYS = ["connectivity", "snapshot_before", "entity_counts", "dataset_comparison", "discovery", "logistics", "warranty", "authorization", "apis", "evidence", "provenance", "snapshot_after_pass1",
               "snapshot_after_pass2", "determinism", "final_classification"]


def test_the_report_has_the_full_schema_and_is_plain_json(offline_report):
    for k in REPORT_KEYS:
        assert k in offline_report, k
    json.loads(json.dumps(L.json_safe(offline_report)))
    assert offline_report["schema_version"] == 2 and {"before", "after", "graph_unchanged", "files_vs_graph", "api"} <= set(offline_report)  # earlier consumers keep their keys


def test_offline_mode_is_labelled_never_live_verified_and_always_blocked(offline_report):
    r = offline_report
    assert r["mode"] == "OFFLINE" and r["live_graph_verified"] is False and r["connectivity"]["mode"] == "OFFLINE"
    assert r["final_classification"] == "PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE" and r["final_classification_detail"]["result"] == "BLOCKED"
    assert all(a["status"] == "BLOCKED" for a in r["acceptance"]) and "PASS" not in {a["status"] for a in r["acceptance"]}
    assert r["offline_checks"]["harness_and_engine_logic"] == "PASS" and "not Neo4j" in r["offline_checks"]["note"]
    assert r["snapshot_before"]["source"] == "MEMORY_TWIN"


def test_two_passes_are_identical_and_the_snapshots_do_not_move(offline_report):
    d = offline_report["determinism"]
    assert d["business_results_identical"] is True and d["snapshot_identical"] is True and d["mismatches"] == [] and d["pass1_status"] == d["pass2_status"] == "PASS"
    assert offline_report["snapshot_before"] == offline_report["snapshot_after_pass1"] == offline_report["snapshot_after_pass2"]
    assert "validation_timestamp" in d["excluded_as_time_dependent"]


def test_determinism_reports_exactly_what_changed_between_passes():
    p1 = {"discovery": [{"scenario": "D001", "status": "PASS", "actual": "SUCCESS/RECOMMEND"}], "timing": {"duration_seconds": 1}}
    p2 = copy.deepcopy(p1)
    p2["discovery"][0]["actual"] = "NOT_FOUND/NO_VALID_RECOMMENDATION"
    p2["timing"]["duration_seconds"] = 9
    d = V.determinism(p1, p2, {}, {}, {})
    assert d["business_results_identical"] is False and d["mismatches"] == ["discovery[0].actual: files=\"SUCCESS/RECOMMEND\" graph=\"NOT_FOUND/NO_VALID_RECOMMENDATION\""]
    same = V.determinism(p1, {**p1, "timing": {"duration_seconds": 99}}, {}, {}, {})
    assert same["business_results_identical"] is True  # durations are the only thing excluded


def test_main_writes_the_json_report_and_exits_with_the_classification_code(monkeypatch, tmp_path, capsys):
    out = tmp_path / "report_offline.json"
    monkeypatch.setattr(sys, "argv", ["x", "--offline", "--out", str(out)])
    assert V.main() == 2
    data = json.loads(out.read_text())
    assert data["mode"] == "OFFLINE" and set(REPORT_KEYS) <= set(data) and "mode=OFFLINE  live_graph_verified=False" in capsys.readouterr().out


def test_the_dataset_table_has_the_review_columns_and_every_dataset(offline_report):
    t = offline_report["dataset_summary_table"]
    assert set(t[0]) == {"Dataset", "Records checked", "Valid", "Invalid", "Missing in graph", "Missing in canonical", "Field mismatches", "Normalization-only differences", "Status"}
    names = {r["Dataset"] for r in t}
    from app.canonical.registry import SPECS
    assert {s.name for s in SPECS} <= names and all(r["Status"] == "PASS" for r in t)


def test_scenario_sections_show_the_requested_columns(offline_report):
    d = offline_report["discovery"][0]
    assert {"scenario", "request", "expected", "actual", "status", "evidence_status"} <= set(d)
    ids = [r["scenario"] for r in offline_report["discovery"]]
    assert ids[:3] == ["D001", "D002", "D003"]
    l = offline_report["logistics"][0]
    assert {"shipment", "expected_status", "actual_status", "expected_route", "actual_route", "planned_eta", "alternatives", "status"} <= set(l)
    w = offline_report["warranty"][0]
    assert {"scenario", "expected_decision", "actual_decision", "matching_factors", "mismatching_factors", "status"} <= set(w) and w["mismatching_factors"] == []
    a = offline_report["authorization"][0]
    assert {"test", "role", "resource", "expected", "actual", "status"} <= set(a)
    ep = offline_report["api_endpoints"]
    assert [e["endpoint"] for e in ep] == ["POST discovery/context", "POST logistics/context", "POST warranty/context", "POST request"]
    assert all({"authentication", "authorization", "status_code", "decision", "evidence", "provenance", "status"} <= set(e) for e in ep)


def test_the_authorization_section_exposes_no_private_customer_information(offline_report):
    blob = json.dumps(offline_report["authorization"] + offline_report["apis"])
    assert not re.search(r"@|Harmsen|Hamburg|Zwolle|password|NEO4J|nv_session", blob)


def test_a_graph_engine_that_differs_from_the_files_is_reported_by_path():
    from app.logistics.readers import FileReader

    class Drifted(FileReader):
        def shipment(self, shipment_id):
            row = super().shipment(shipment_id)
            return {**row, "status": "DELIVERED"} if row and shipment_id == "SHP-NET-0001" else row

    files = CommerceContextEngine.from_files(CANON_DIR, as_of=V.AS_OF)
    live = CommerceContextEngine.from_files(CANON_DIR, as_of=V.AS_OF)
    live.logistics = Drifted(CANON_DIR)
    rep = V.compare_engines(files, live)
    assert "logistics: SHP-NET-0001" in rep["different"] and any("shipment.status" in d and "DELIVERED" in d for d in rep["different"]["logistics: SHP-NET-0001"])
    assert rep["identical"] == rep["scenarios"] - 1


def test_the_live_tests_do_not_count_as_passes_when_skipped():
    """The live module skips (with a reason) when Neo4j is unreachable; the dry-run tests it contains are the only ones that can pass without the graph."""
    text = (Path(__file__).parent / "test_commerce_live.py").read_text(encoding="utf-8")
    assert "pytest.skip(" in text and "a skip is not a pass" in text
