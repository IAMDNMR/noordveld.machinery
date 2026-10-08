"""Live-graph validation of the Commerce Context Engine (read-only). Every test here compares the engine on the live Neo4j graph with the engine on the canonical files.

When Neo4j cannot be reached these tests are SKIPPED with a reason; a skip is not a pass. The harness itself (the scenario list, the comparison and the golden expectations) is
exercised on every run by the dry-run test, with the files standing in for the graph. The full report, including the before/after graph snapshot, is produced by
scripts/commerce_live_validate.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import commerce_live_validate as v  # noqa: E402

from app.canonical.io import CANON_DIR  # noqa: E402
from app.commerce.engine import CommerceContextEngine  # noqa: E402


@pytest.fixture(scope="module")
def files() -> CommerceContextEngine:
    return CommerceContextEngine.from_files(CANON_DIR, as_of=v.AS_OF)


@pytest.fixture(scope="module")
def graph():
    ok, why = v.reachable()
    if not ok:
        pytest.skip(f"live Neo4j validation not run: {why}")
    from app.graph.client import GraphClient
    from app.core.config import get_settings

    g = GraphClient(get_settings())
    yield g
    g.close()


# ── always runs: the harness, with the files standing in for the graph ──────────────────────────
def test_dry_run_the_harness_passes_when_both_sides_are_the_files(files):
    twin = CommerceContextEngine.from_files(CANON_DIR, as_of=v.AS_OF)
    report = v.compare_engines(files, twin)
    assert report["scenarios"] >= 35 and report["identical"] == report["scenarios"] and report["different"] == {}
    assert all(r["ok"] for r in v.authorization_checks(files, twin))
    assert all(r["ok"] for r in v.golden_checks(twin))


def test_the_difference_report_names_the_path_of_every_difference():
    assert v.diffs({"a": {"b": [1, 2]}}, {"a": {"b": [1, 3]}}) == ["a.b[1]: files=2 graph=3"]
    assert v.diffs({"a": 1}, {"b": 1}) == ["a: files=1 graph=\"<absent>\"", "b: files=\"<absent>\" graph=1"]
    assert v.diffs({"a": [1]}, {"a": [1, 2]}) == ["a: files has 1 items, graph has 2"] and v.diffs({"a": 1}, {"a": 1}) == []


# ── live ─────────────────────────────────────────────────────────────────────────────────────────
def test_live_every_context_equals_the_file_context(files, graph):
    live = CommerceContextEngine.from_graph(graph, as_of=v.AS_OF)
    report = v.compare_engines(files, live)
    assert report["different"] == {}, report["different"]


def test_live_authorization_matrix_on_real_ownership_data(files, graph):
    rows = v.authorization_checks(files, CommerceContextEngine.from_graph(graph, as_of=v.AS_OF))
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_live_golden_outcomes_evidence_paths_and_provenance(graph):
    rows = v.golden_checks(CommerceContextEngine.from_graph(graph, as_of=v.AS_OF))
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_live_api_routes(graph):
    rows = v.api_checks(graph)
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_live_the_graph_is_unchanged_by_everything_above(graph):
    before = v.snapshot(graph)
    live = CommerceContextEngine.from_graph(graph, as_of=v.AS_OF)
    for name, kind, kw in v.scenarios(CommerceContextEngine.from_files(CANON_DIR, as_of=v.AS_OF)):
        v.run(live, kind, kw)
    v.api_checks(graph)
    assert v.snapshot(graph) == before
