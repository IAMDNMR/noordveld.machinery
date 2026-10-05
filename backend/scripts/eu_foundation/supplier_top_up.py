"""Second source for common verified parts that have only one supplier. Additive, deterministic, idempotent. No new suppliers.

Rules (only facts already in the graph are used):
  * eligible  = PartCatalogProfile VERIFIED and orderable, currently with exactly one SUPPLIED_BY supplier
  * single-source by design = machine-specific assemblies (final drive gearbox, planetary gear carrier, central lubrication pump):
    they keep one supplier. No attribute in the graph marks a part "proprietary", so this list is a stated judgement (SINGLE_SOURCE_BY_DESIGN).
  * candidate supplier = an existing supplier whose SUPPLIES_CATEGORY covers the part's category and who does not already supply it;
    the least-loaded candidate wins (deterministic tie-break). A second source is a supply relationship only: it does not say the
    suppliers' parts are interchangeable, and no unit cost is stated (none is known).
  * lead time = that supplier's own average lead time on its existing part links.

  python supplier_top_up.py plan | apply
"""
from __future__ import annotations

import json
import sys

from common import SOURCE_FILE, SOURCE_ID, SOURCE_NAME, TODAY, dump, read, stable_int, write

BATCH2 = "SUPPLY-2026-10-05"
SINGLE_SOURCE_BY_DESIGN = {"PRT-018": "Final drive gearbox assembly", "PRT-027": "Planetary gear carrier", "PRT-097": "Central lubrication pump"}


def plan() -> list[dict]:
    parts = read("""MATCH (c:PartCatalogProfile {part_status:'VERIFIED', orderable:true})-[:PROFILES_PART]->(p:Part)
                    WITH p, [(p)-[:SUPPLIED_BY]->(s:Supplier) | s.supplier_id] AS have WHERE size(have) = 1 AND NOT p.part_id IN $single
                    RETURN p.part_id AS id, p.part_number AS no, p.category AS cat, have ORDER BY id""", single=list(SINGLE_SOURCE_BY_DESIGN))
    load = {r["s"]: r["n"] for r in read("MATCH (s:Supplier) OPTIONAL MATCH (s)<-[r:SUPPLIED_BY]-() RETURN s.supplier_id AS s, count(r) AS n")}
    lead = {r["s"]: r["avg"] for r in read("MATCH (s:Supplier)<-[r:SUPPLIED_BY]-() WHERE r.lead_time_days IS NOT NULL RETURN s.supplier_id AS s, avg(r.lead_time_days) AS avg")}
    covers = {}
    for r in read("MATCH (s:Supplier)-[:SUPPLIES_CATEGORY]->(c:Category) RETURN s.supplier_id AS s, collect(c.name) AS cats"):
        covers[r["s"]] = set(r["cats"])
    out = []
    for p in parts:
        cands = [s for s, cats in covers.items() if p["cat"] in cats and s not in p["have"]]
        if not cands:
            continue
        pick = min(cands, key=lambda s: (load[s], stable_int("second", p["id"], s)))
        load[pick] += 1
        out.append({"part_id": p["id"], "part_number": p["no"], "category": p["cat"], "existing": p["have"], "added": pick, "lead_time_days": round(lead.get(pick, 14))})
    return out


def apply(rows: list[dict]) -> dict:
    prov = {"data_status": "SYNTHETIC_DEMO", "provenance_type": "SYNTHETIC_DEMO", "source_id": SOURCE_ID, "source_name": SOURCE_NAME, "source_file": SOURCE_FILE,
            "source_sheet": "supplier_top_up", "confidence": "NOT_STATED", "authoritative_flag": False, "last_updated": TODAY, "enrichment_batch": BATCH2,
            "demo_marker": "SYNTHETIC_DEMO_DATA"}
    items = [{"p": r["part_id"], "s": r["added"], "rel_id": f"SUPPLIED_BY:{r['part_id']}>{r['added']}:2ND",
              "props": {**prov, "is_primary": False, "lead_time_days": r["lead_time_days"], "min_order_qty": 1 + stable_int("moq2", r["part_id"], r["added"], mod=10),
                        "supplier_part_number": f"{r['added'][4:]}-{r['part_number']}", "relationship_status": "ACTIVE_DEMO",
                        "basis": "SECOND_SOURCE_SAME_CATEGORY_NO_INTERCHANGEABILITY_IMPLIED"}} for r in rows]
    return write("""UNWIND $rows AS row MATCH (p:Part {part_id: row.p}) MATCH (s:Supplier {supplier_id: row.s})
                    WHERE NOT (p)-[:SUPPLIED_BY]->(s)
                    MERGE (p)-[r:SUPPLIED_BY {rel_id: row.rel_id}]->(s) ON CREATE SET r += row.props""", rows=items)


if __name__ == "__main__":
    rows = plan()
    print(json.dumps(rows, indent=1))
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        result = apply(rows)
        dump(f"supplier_top_up_result.json", {"batch": BATCH2, "planned": rows, "created": result})
        print(result)
