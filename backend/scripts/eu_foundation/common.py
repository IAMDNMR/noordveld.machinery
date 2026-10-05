"""Shared helpers for the European operational data foundation (deterministic, additive, idempotent).

Conventions follow the earlier enrichment batch (scripts/enrich_graph_demo_data.py): every new node and relationship carries the
project's provenance fields, data_status = provenance_type = SYNTHETIC_DEMO (the project's spelling of "SYNTHETIC_DEMO_DATA"),
and every relationship has a unique rel_id (the graph enforces uniqueness on it).
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
logging.disable(logging.CRITICAL)

from neo4j import READ_ACCESS, WRITE_ACCESS  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402

BATCH = "EUFOUND-2026-10-04"
SOURCE_ID = "SRC-005"
SOURCE_NAME = "eu_foundation generator (deterministic, no random module)"
SOURCE_FILE = "backend/scripts/eu_foundation"
TODAY = "2026-10-04"
DATA_DIR = BACKEND / "data" / "eu_foundation"
DOCS_DIR = ROOT / "docs" / "data-foundation"

_client: GraphClient | None = None


def client() -> GraphClient:
    global _client
    if _client is None:
        _client = GraphClient(get_settings())
    return _client


def read(query: str, **params: Any) -> list[dict[str, Any]]:
    with client().driver.session(database=get_settings().neo4j_database, default_access_mode=READ_ACCESS) as s:
        return s.execute_read(lambda tx: tx.run(query, params).data())


def write(query: str, **params: Any) -> dict[str, int]:
    """One write transaction; returns what it created (nothing is ever deleted by this package)."""
    with client().driver.session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as s:
        def work(tx):
            c = tx.run(query, params).consume().counters
            return {"nodes": c.nodes_created, "rels": c.relationships_created, "props": c.properties_set, "deleted": c.nodes_deleted + c.relationships_deleted}
        return s.execute_write(work)


def prov(sheet: str, record_id: str, status: str = "SYNTHETIC_DEMO", confidence: str = "NOT_STATED") -> dict[str, Any]:
    return {
        "data_status": status, "provenance_type": status, "source_id": SOURCE_ID, "source_name": SOURCE_NAME, "source_file": SOURCE_FILE,
        "source_sheet": sheet, "source_record_id": record_id, "confidence": confidence, "authoritative_flag": False,
        "last_updated": TODAY, "enrichment_batch": BATCH,
    }


def stable_int(*parts: Any, mod: int = 1_000_000) -> int:
    """A deterministic integer from the inputs: replaces random numbers everywhere in the generator."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:12], 16) % mod


def pick(options: list[Any] | tuple[Any, ...], *key: Any) -> Any:
    return options[stable_int(*key, mod=len(options))]


def unit(*key: Any) -> float:
    """Deterministic float in [0, 1)."""
    return stable_int(*key, mod=10_000_000) / 10_000_000


def dump(name: str, obj: Any) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / name
    p.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str), encoding="utf-8")
    return p
