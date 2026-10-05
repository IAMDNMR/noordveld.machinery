"""European operational data foundation: generator determinism/idempotency, and the live-graph validation + scenarios (skipped without Neo4j)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.config import get_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eu_foundation"))

needs_graph = pytest.mark.skipif(not get_settings().graph_configured, reason="Neo4j is not configured")


@needs_graph
def test_generator_is_deterministic_and_regenerates_the_seeded_model_exactly():
    from build import build, summary
    a, b = summary(*build()), summary(*build())
    assert a == b  # same counts both runs; also equals what is already in the graph because batch-owned entities are excluded from "existing"
    assert a["nodes_total"] > 0 and a["relationships_total"] > 0


@needs_graph
def test_seed_plan_matches_the_graph_so_a_rerun_creates_nothing():
    from build import build
    from common import BATCH, read
    model, _ = build()
    for label in ("Dealer", "Supplier", "ShipTo", "Warehouse", "TransportRoute", "TransportLeg", "FreightRate", "TransportTerminal"):
        in_graph = read(f"MATCH (n:`{label}`) WHERE n.enrichment_batch = $b RETURN count(n) AS n", b=BATCH)[0]["n"]
        assert in_graph == len(model.nodes[label]), label


@needs_graph
def test_live_graph_passes_every_validation_check():
    import validate
    validate.CHECKS.clear()
    assert validate.main() == 0, [c for c in validate.CHECKS if not c["pass"]]


@needs_graph
def test_end_to_end_scenarios_all_pass():
    import scenarios
    assert scenarios.main() == 0


def test_no_us_or_uk_country_in_the_geography():
    from geo import COUNTRIES, EU27
    assert len(EU27) == 27 and "GB" not in COUNTRIES and "US" not in COUNTRIES and set(COUNTRIES) == set(EU27)
