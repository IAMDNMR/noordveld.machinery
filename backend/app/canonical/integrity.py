"""Integrity coverage for canonical data.

The existing SOURCE/DERIVED DATA INTEGRITY CHECKSUM (scripts/eu_foundation/audit_before.py) protects the supplied catalogue; it is reused unchanged and is
checked before and after every ingestion. New canonical domains are SYNTHETIC_DEMO, so they sit outside that checksum by design. They get two checksums of
their own:

  dataset_checksum   SHA-256 over the validated canonical records of a dataset (every field except ingestion_timestamp), independent of file order.
                     The same canonical input always gives the same value.
  graph_fingerprint  SHA-256 over every node and relationship the ingestion created (source_id = SRC-CANON), excluding timestamps. After ingesting the
                     same dataset again the fingerprint is identical: the logical graph did not change.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.canonical.models import Canon
from app.canonical.store import VOLATILE, Store


def _line(rec: Canon) -> str:
    body = rec.model_dump(exclude={"ingestion_timestamp"})
    return f"{rec.id}\t{json.dumps(body, sort_keys=True, default=str, ensure_ascii=False)}"


def dataset_checksum(records: list[Canon]) -> str:
    h = hashlib.sha256()
    for line in sorted(_line(r) for r in records):
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def graph_fingerprint(store: Store) -> str:
    nodes, rels = store.fingerprint_rows()
    h = hashlib.sha256()
    for r in nodes:
        h.update(json.dumps({"l": r["l"], "p": {k: v for k, v in r["p"].items() if k not in VOLATILE}}, sort_keys=True, default=str).encode())
    for r in rels:
        h.update(json.dumps({"t": r["t"], "p": {k: v for k, v in r["p"].items() if k not in VOLATILE}}, sort_keys=True, default=str).encode())
    return h.hexdigest()


def summary(records: list[Canon]) -> dict[str, Any]:
    return {"records": len(records), "checksum": dataset_checksum(records)}
