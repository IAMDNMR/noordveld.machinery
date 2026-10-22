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
































# ── part 2: the live graph, read-only ────────────────────────────────────────────────────────────




# ── part 3: opt-in, writes TEST records and removes them ─────────────────────────────────────────
