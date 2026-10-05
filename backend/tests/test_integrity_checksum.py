"""The SOURCE/DERIVED DATA INTEGRITY CHECKSUM (scripts/eu_foundation/audit_before.py): what it protects and what it deliberately ignores.
Read-only: it reads the live graph and perturbs copies in memory."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from app.core.config import get_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eu_foundation"))

needs_graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


def _tweak(rows, pred, key, value):
    out = copy.deepcopy(rows)
    for r in out:
        if pred(r):
            r["p"][key] = value
            return out
    raise AssertionError("no row matched")


@needs_graph
def test_the_checksum_covers_supplied_data_including_user_provided_seed_records_and_never_app_written_ones():
    import audit_before as ab

    nodes, rels = ab.protected_rows()
    classes = {(r["p"]["data_status"], r["p"]["source_id"]) for r in nodes + rels}
    assert {("SOURCE_DERIVED", "SRC-001"), ("DERIVED", "SRC-002"), ("USER_PROVIDED", "SRC-BRIEF")} <= classes
    assert not [r for r in nodes + rels if r["p"].get("source_id") == ab.APP_WRITTEN_SOURCE_ID]  # nothing the app writes is guarded
    seed = {(r["l"]) for r in nodes if r["p"]["data_status"] == "USER_PROVIDED"}
    assert seed == {"Plant", "DataSource", "OrderStatus"}  # the supplied plants, data-source entry and original statuses are protected


@needs_graph
def test_any_change_to_supplied_data_changes_the_checksum_and_the_live_graph_matches_the_baseline():
    import json

    import audit_before as ab
    from common import DATA_DIR

    nodes, rels = ab.protected_rows()
    base = ab.fingerprint(nodes, rels)
    assert base == json.load(open(DATA_DIR / "audit_before.json", encoding="utf-8"))["source_checksum"]  # the graph is as baselined
    for label, key in (("Plant", "name"), ("DataSource", "name"), ("Part", "name"), ("Machine", "model_code")):
        assert ab.fingerprint(_tweak(nodes, lambda r, label=label: r["l"] == label, key, "X"), rels) != base, label
    assert ab.fingerprint(_tweak(nodes, lambda r: r["l"] == "OrderStatus" and r["p"].get("order_status_code") == "NEW", "label", "X"), rels) != base
    assert ab.fingerprint(nodes, _tweak(rels, lambda r: r["p"]["data_status"] == "DERIVED", "x", "y")) != base


def test_fingerprint_is_order_sensitive_and_deterministic():
    import audit_before as ab

    a = [{"l": "A", "p": {"x": 1}}, {"l": "B", "p": {"x": 2}}]
    assert ab.fingerprint(a, []) == ab.fingerprint(copy.deepcopy(a), [])
    assert ab.fingerprint(a, []) != ab.fingerprint(list(reversed(a)), [])
