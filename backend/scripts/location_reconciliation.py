"""Location reconciliation report: every location whose geography differs between the canonical files and the graph. READ-ONLY (MATCH queries only).

    python backend/scripts/location_reconciliation.py [--out reconciliation.json] [--csv reconciliation.csv]

Classification per record:
  MATCH              every geography field equal (not listed)
  GRAPH_ONLY         the graph holds a value the canonical record lacks, and the exporter has no rule that would have dropped it on purpose
  EXPORTER_OMISSION  the graph holds a value the canonical record lacks BECAUSE the exporter did not read it (the export rule takes coordinates from the city reference only)
  CANONICAL_ONLY     the canonical record holds a value the graph lacks
  CONFLICT           both hold a value and they differ
  UNKNOWN            anything else (reported, never guessed)
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import commerce_validation_lib as L

from app.canonical.geography import coordinate_class
from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME, KINDS
from app.core.config import get_settings
from app.graph.client import GraphClient

# canonical field -> graph property
GEO = {"latitude": "latitude", "longitude": "longitude", "geo_basis": "geo_basis", "country": "country", "region": "region", "timezone": "timezone", "logistics_type": "logistics_type"}
CANON_FIELD = {"logistics_type": "location_type"}  # the canonical Location calls it location_type
PROTECTED = ("SOURCE_DERIVED", "DERIVED", "REAL")
FIELDS = ["location_id", "name", "record_status", "protected", "graph_latitude", "graph_longitude", "graph_geo_basis", "canonical_latitude", "canonical_longitude", "canonical_geo_basis",
          "graph_country", "canonical_country", "graph_region", "canonical_region", "graph_timezone", "canonical_timezone", "graph_logistics_type", "canonical_logistics_type", "classification",
          "graph_label", "graph_data_status", "graph_source_id", "coordinate_source_class", "differing_fields"]


def exporter_rule_drops(label: str, props: dict[str, Any], reference_cities: set[str]) -> bool:
    """True when the Phase 1 exporter takes coordinates for this node only from the reference city list, and the node's name is not in it."""
    return label == "Location" and props.get("location_type") == "CITY" and (props.get("name") or "") not in reference_cities


def classify(canon: dict[str, Any], graph: dict[str, Any], label: str, reference_cities: set[str]) -> tuple[str, list[str]]:
    diffs: list[str] = []
    kinds = set()
    for cf, gp in GEO.items():
        c, g = canon.get(CANON_FIELD.get(cf, cf)), graph.get(gp)
        c = None if c in ("", []) else c
        g = None if g in ("", []) else g
        if c == g:
            continue
        diffs.append(cf)
        kinds.add("CANONICAL_ONLY" if g is None else "GRAPH_ONLY" if c is None else "CONFLICT")
    if not diffs:
        return "MATCH", []
    if kinds == {"CONFLICT"} or "CONFLICT" in kinds:
        return "CONFLICT", diffs
    if kinds == {"GRAPH_ONLY"}:
        return ("EXPORTER_OMISSION" if exporter_rule_drops(label, graph, reference_cities) else "GRAPH_ONLY"), diffs
    if kinds == {"CANONICAL_ONLY"}:
        return "CANONICAL_ONLY", diffs
    return "UNKNOWN", diffs


def run(root: Path = CANON_DIR) -> dict[str, Any]:
    reference = json.loads((root / "reference" / "geography.json").read_text(encoding="utf-8"))
    cities = set(reference["city_coordinates"])
    g = GraphClient(dataclasses.replace(get_settings(), neo4j_query_timeout=120.0))
    ro = L.ReadOnlyGraph(g)
    out: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    try:
        for dataset in ("locations", "network_locations"):
            for row in load_rows(BY_NAME[dataset], root)[0]:
                label = row["graph_label"]
                key = dict(KINDS["location"]).get(label) or next(k for lb, k in KINDS["location"] if lb == label)
                res = ro.read(f"MATCH (n:`{label}` {{`{key}`: $id}}) RETURN properties(n) AS p", id=row["location_id"])
                if not res:
                    counts["NOT_IN_GRAPH"] = counts.get("NOT_IN_GRAPH", 0) + 1
                    continue
                p = res[0]["p"]
                cls, diffs = classify(row, p, label, cities)
                counts[cls] = counts.get(cls, 0) + 1
                if cls == "MATCH":
                    continue
                protected = p.get("data_status") in PROTECTED or (p.get("data_status") == "USER_PROVIDED" and p.get("source_id") != "APP-SESSION")
                out.append({"location_id": row["location_id"], "name": row.get("name") or p.get("name"), "record_status": p.get("status") or p.get("dealer_status") or "ACTIVE",
                            "protected": protected, "graph_latitude": p.get("latitude"), "graph_longitude": p.get("longitude"), "graph_geo_basis": p.get("geo_basis"),
                            "canonical_latitude": row.get("latitude"), "canonical_longitude": row.get("longitude"), "canonical_geo_basis": row.get("geo_basis"),
                            "graph_country": p.get("country"), "canonical_country": row.get("country"), "graph_region": p.get("region"), "canonical_region": row.get("region"),
                            "graph_timezone": p.get("timezone"), "canonical_timezone": row.get("timezone"), "graph_logistics_type": p.get("logistics_type"),
                            "canonical_logistics_type": row.get("location_type"), "classification": cls, "graph_label": label, "graph_data_status": p.get("data_status"),
                            "graph_source_id": p.get("source_id"), "differing_fields": ",".join(diffs),
                            "coordinate_source_class": coordinate_class(p.get("data_status"), p.get("geo_basis") or row.get("geo_basis"))})
    finally:
        g.close()
    return {"counts": counts, "records": sorted(out, key=lambda r: (r["classification"], r["location_id"]))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--csv")
    a = ap.parse_args()
    rep = run()
    print(json.dumps(rep["counts"], indent=1), f"\n{len(rep['records'])} records differ")
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows({k: r.get(k) for k in FIELDS} for r in rep["records"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
