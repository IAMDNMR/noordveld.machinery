"""Final data reconciliation: shipments with several order lines, the carrier name, technician provenance.
Offline tests read the canonical files; live ones (read-only) skip when Neo4j is unreachable."""
from __future__ import annotations

import dataclasses
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commerce_validation_lib as L  # noqa: E402

from app.canonical.io import CANON_DIR, load_rows  # noqa: E402
from app.canonical.registry import BY_NAME  # noqa: E402
from app.commerce.access import CommerceRole, Principal  # noqa: E402
from app.commerce.engine import CommerceContextEngine  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402
from app.logistics.readers import FileReader  # noqa: E402

live = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")
OEM = Principal(CommerceRole("OEM"), user_id="test")


def rows(name: str) -> list[dict]:
    return load_rows(BY_NAME[name], CANON_DIR)[0]


def ro_graph() -> L.ReadOnlyGraph:
    return L.ReadOnlyGraph(GraphClient(dataclasses.replace(get_settings(), neo4j_query_timeout=120.0)))


@pytest.fixture(scope="module")
def engine() -> CommerceContextEngine:
    return CommerceContextEngine.from_files(as_of=date(2026, 10, 7))


def part_of_line() -> dict[str, str]:
    return {r["order_line_id"]: r["part_id"] for r in rows("order_lines") + rows("network_order_lines")}


# ── the model: one shipment, one or more lines ───────────────────────────────────────────────────
def test_the_shipment_no_longer_holds_a_single_order_line_and_every_line_is_a_shipment_line_record():
    assert "order_line_id" not in BY_NAME["shipments"].model.model_fields
    lines = rows("shipment_lines") + rows("network_shipment_lines")
    assert all(r["shipment_line_id"] == f"{r['shipment_id']}>{r['order_line_id']}" for r in lines)
    ids = [r["shipment_line_id"] for r in lines]
    assert len(ids) == len(set(ids)) == 14 + 4
    by: dict[str, list[str]] = {}
    for r in lines:
        by.setdefault(r["shipment_id"], []).append(r["order_line_id"])
    assert len(by["SHP-0010"]) == 2 and len(by["SHP-0011"]) == 3 and all(len(v) == 1 for k, v in by.items() if k not in ("SHP-0010", "SHP-0011"))
    assert set(by) == {r["shipment_id"] for r in rows("shipments") + rows("network_shipments")}  # every shipment ships at least one line


# ── the context ──────────────────────────────────────────────────────────────────────────────────
def test_a_shipment_with_two_lines_returns_both_lines_and_both_parts_and_no_single_part(engine):
    ctx = engine.build_logistics_context(principal=OEM, shipment_id="SHP-0010")
    want = ["OI-0021", "OI-0022"]
    assert ctx.shipment_kind == "MULTI_LINE" and sorted(ln["order_line_id"] for ln in ctx.shipment_lines) == want
    assert ctx.part is None, "no part is forced onto a multi-line shipment"
    assert sorted(p["part_id"] for p in ctx.parts) == sorted({part_of_line()[i] for i in want})
    assert ctx.decision.facts["shipment_line_count"] == 2 and ctx.decision.facts["shipment_kind"] == "MULTI_LINE"


def test_a_shipment_with_three_lines_returns_all_three(engine):
    ctx = engine.build_logistics_context(principal=OEM, shipment_id="SHP-0011")
    want = ["OI-0023", "OI-0024", "OI-0025"]
    assert ctx.shipment_kind == "MULTI_LINE" and sorted(ln["order_line_id"] for ln in ctx.shipment_lines) == want and ctx.part is None
    assert {p["part_id"] for p in ctx.parts} == {part_of_line()[i] for i in want} and len(ctx.parts) == len({part_of_line()[i] for i in want})
    assert [s["entity"] for s in ctx.evidence_path].count("OrderLine") == 3
    assert any("carries 3 order line(s)" in str(e) for e in ctx.evidence)


def test_a_single_line_shipment_works_as_before(engine):
    ctx = engine.build_logistics_context(principal=OEM, shipment_id="SHP-NET-0001")
    assert ctx.shipment_kind == "SINGLE_LINE" and len(ctx.shipment_lines) == 1 and ctx.part["part_number"] == "NVM-1010-HY" and [p["part_number"] for p in ctx.parts] == ["NVM-1010-HY"]
    assert ctx.decision.status == "SUCCESS" and ctx.route["route_id"] == "RTE-NET-JPNL-SEA-ECO"
    old = engine.build_logistics_context(principal=OEM, shipment_id="SHP-0001")
    assert old.shipment_kind == "SINGLE_LINE" and old.part is not None and old.part["part_id"] == part_of_line()["OI-0001"]


def test_multiple_lines_in_one_shipment_and_multiple_shipments_of_one_order_are_different_things(engine):
    multi_line = engine.build_logistics_context(principal=OEM, shipment_id="SHP-0010")
    assert multi_line.shipment_kind == "MULTI_LINE" and multi_line.order_split is False and multi_line.order_shipments == ["SHP-0010"]
    split = engine.build_logistics_context(principal=OEM, shipment_id="SHP-NET-0001")
    assert split.shipment_kind == "SINGLE_LINE" and split.order_split is True and split.order_shipments == ["SHP-NET-0001", "SHP-NET-0002"]
    assert split.decision.facts["other_shipments_of_order"] == ["SHP-NET-0002"] and split.decision.facts["order_split"] is True


def test_an_order_split_over_several_shipments_still_requires_clarification_and_each_option_names_its_parts(engine):
    ctx = engine.build_logistics_context(principal=OEM, order_id="ORD-NET-0001")
    assert ctx.decision.status == "REQUIRES_CLARIFICATION"
    opts = {o["shipment_id"]: o for o in ctx.clarification["options"]}
    assert set(opts) == {"SHP-NET-0001", "SHP-NET-0002"} and all(o["line_count"] == 1 and o["part_number"] == "NVM-1010-HY" for o in opts.values())


def test_the_clarification_options_of_a_multi_line_shipment_list_every_part_and_pick_none(engine):
    order = next(r["order_id"] for r in rows("shipments") if r["shipment_id"] == "SHP-0010")
    options = engine._options([s for s in FileReader().shipments_of_order(order) if s["shipment_id"] == "SHP-0010"])
    assert options[0]["line_count"] == 2 and options[0]["part_number"] is None and len(options[0]["parts"]) == 2


# ── the carrier ──────────────────────────────────────────────────────────────────────────────────
def test_every_shipment_names_its_carrier_and_the_names_agree_with_the_carrier_id():
    names: dict[str, set[str]] = {}
    for s in rows("shipments") + rows("network_shipments"):
        assert s["carrier_id"] and s["carrier"], s["shipment_id"]
        names.setdefault(s["carrier_id"], set()).add(s["carrier"])
    assert all(len(v) == 1 for v in names.values()), "one name per carrier id (no free-text variants)"
    assert names["CAR-demo-freight-fictional"] == {"Demo Freight (fictional)"}


@live
def test_live_carrier_id_and_name_agree_between_files_and_graph_and_no_carrier_is_orphaned():
    g = ro_graph()
    graph = {r["id"]: r["name"] for r in g.read("MATCH (c:Carrier) RETURN c.carrier_id AS id, c.name AS name")}
    for s in rows("shipments") + rows("network_shipments"):
        assert graph.get(s["carrier_id"]) == s["carrier"], s["shipment_id"]
    linked = {r["id"] for r in g.read("MATCH (:Shipment)-[:CARRIED_BY]->(c:Carrier) RETURN DISTINCT c.carrier_id AS id")}
    assert {s["carrier_id"] for s in rows("shipments") + rows("network_shipments")} <= linked


# ── technicians ──────────────────────────────────────────────────────────────────────────────────
def test_the_technician_source_record_id_states_what_it_is():
    techs = rows("technicians")
    assert len(techs) == 22 and all(t["data_status"] == "SYNTHETIC_DEMO" for t in techs)
    generated = [t for t in techs if t["source_record_id"].startswith("synthetic:")]
    assert len(generated) == 20 and all(t["source_record_id"] == f"synthetic:{t['technician_id']}" for t in generated)


@live
def test_live_every_technicians_graph_provenance_equals_the_canonical_record():
    g = ro_graph()
    graph = {r["id"]: r for r in g.read("MATCH (t:Technician) RETURN t.technician_id AS id, t.source_record_id AS srid, t.data_status AS ds, t.certification AS cert, "
                                        "t.specialization AS spec, t.name AS name")}
    for t in rows("technicians"):
        got = graph[t["technician_id"]]
        assert (got["srid"], got["ds"], got["cert"], got["spec"], got["name"]) == (t["source_record_id"], t["data_status"], t["certification"], t["specialization"], t["name"]), t["technician_id"]


# ── the graph ────────────────────────────────────────────────────────────────────────────────────
@live
def test_live_the_graphs_shipment_lines_are_exactly_the_canonical_ones():
    src = L.CypherSource(ro_graph())
    graph = {f"{f}>{t}" for f, t in src.rel_endpoints("SHIPS_LINE", ("Shipment", "shipment_id"), ("OrderLine", "order_line_id"))}
    assert graph == {r["shipment_line_id"] for r in rows("shipment_lines") + rows("network_shipment_lines")}
