"""Remove the synthetic EU customer master created by batch EUFOUND-2026-10-04: Customer, CustomerContact, their customer-only Address nodes,
all relationships on them, and any batch Location/Region/Industry that only they kept alive. ShipTos, routes, legs, rates, distances,
dealers, suppliers, depots and inventory are NOT touched.

  python cleanup_customers.py plan     counts only, writes nothing
  python cleanup_customers.py apply    backs up everything it will delete to data/eu_foundation/cleanup_backup_*.json, deletes, verifies

Idempotent: a second run finds nothing and deletes nothing. Reversible: the backup holds every node's labels and properties and every
relationship's endpoints, type and properties (see `restore()`).
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

from audit_before import source_checksum
from common import BATCH, DATA_DIR, client, get_settings, read
from neo4j import WRITE_ACCESS

ORDER_DEPENDENCY = "EXISTS { (c)<-[:ORDERED_BY|ACTS_FOR|OPENED_BY|DELIVERS_TO_CUSTOMER|TO_CUSTOMER]-() }"


def write(q: str, **p: Any) -> dict[str, int]:
    with client().driver.session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as s:
        def work(tx):
            c = tx.run(q, p).consume().counters
            return {"nodes": c.nodes_deleted, "rels": c.relationships_deleted, "created": c.nodes_created + c.relationships_created}
        return s.execute_write(work)


def targets() -> dict[str, Any]:
    b = {"b": BATCH}
    cust = read("MATCH (c:Customer {enrichment_batch: $b}) RETURN c.customer_id AS id", **b)
    contacts = read("MATCH (c:CustomerContact {enrichment_batch: $b}) RETURN c.contact_id AS id", **b)
    # an address is deletable only if the batch created it as a customer address and nothing but deleted customers point at it
    addresses = read("""MATCH (a:Address {enrichment_batch: $b, owner_type: 'CUSTOMER'})
                        WHERE NOT EXISTS { MATCH (x)-[]->(a) WHERE NOT (x:Customer AND x.enrichment_batch = $b) } RETURN a.address_id AS id""", **b)
    blocked = read(f"MATCH (c:Customer {{enrichment_batch: $b}}) WHERE {ORDER_DEPENDENCY} RETURN c.customer_id AS id", **b)
    return {"customers": [r["id"] for r in cust], "contacts": [r["id"] for r in contacts], "addresses": [r["id"] for r in addresses], "blocked": [r["id"] for r in blocked]}


def orphans() -> dict[str, list[str]]:
    """Batch geography/taxonomy nodes with nothing pointing at them (Location city/Region/Industry) and no use."""
    q = """MATCH (n) WHERE n.enrichment_batch = $b AND any(l IN labels(n) WHERE l IN ['Industry','Region','Location','PostalArea'])
           AND NOT EXISTS { MATCH ()-[]->(n) } RETURN labels(n)[0] AS l, coalesce(n.industry_id, n.region_id, n.location_id, n.postal_area_id) AS id"""
    out: dict[str, list[str]] = {}
    for r in read(q, b=BATCH):
        out.setdefault(r["l"], []).append(r["id"])
    return out


KEYS = {"Industry": "industry_id", "Region": "region_id", "Location": "location_id", "PostalArea": "postal_area_id"}


def snapshot(label_filter: str, ids: list[str], key: str) -> dict[str, Any]:
    nodes = read(f"MATCH (n:{label_filter}) WHERE n.{key} IN $ids RETURN labels(n) AS labels, properties(n) AS props", ids=ids)
    rels = read(f"""MATCH (n:{label_filter})-[r]-(m) WHERE n.{key} IN $ids
                    RETURN type(r) AS type, startNode(r) = n AS out, labels(n)[0] AS nl, n.{key} AS nid, labels(m)[0] AS ml,
                           coalesce(m.customer_id, m.contact_id, m.address_id, m.shipto_id, m.machine_id, m.industry_id, m.location_id, m.region_id, m.part_id) AS mid, properties(r) AS props""", ids=ids)
    return {"nodes": nodes, "relationships": rels}


def main(mode: str) -> int:
    t = targets()
    o = orphans()
    print(f"customers {len(t['customers'])}  contacts {len(t['contacts'])}  customer-only addresses {len(t['addresses'])}  blocked-by-dependency {len(t['blocked'])}")
    print("orphans already present before cleanup:", {k: len(v) for k, v in o.items()})
    if t["blocked"]:
        print("STOP: customers referenced by orders/users/carts/shipments:", t["blocked"][:10])
        return 2
    if mode == "plan" or not (t["customers"] or t["contacts"] or t["addresses"]):
        return 0
    before = source_checksum()
    backup = {"batch": BATCH, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "customers": snapshot("Customer", t["customers"], "customer_id"),
              "contacts": snapshot("CustomerContact", t["contacts"], "contact_id"), "addresses": snapshot("Address", t["addresses"], "address_id")}
    path = DATA_DIR / f"cleanup_backup_{int(time.time())}.json"
    # relationships are listed once per endpoint inside the backup; restore() de-duplicates on rel_id
    path.write_text(json.dumps(backup, default=str), encoding="utf-8")
    print("backup:", path.name, {k: (len(v["nodes"]), len(v["relationships"])) for k, v in backup.items() if isinstance(v, dict)})

    deleted = {"nodes": 0, "rels": 0}
    for label, key, ids in (("Customer", "customer_id", t["customers"]), ("CustomerContact", "contact_id", t["contacts"]), ("Address", "address_id", t["addresses"])):
        for i in range(0, len(ids), 60):
            c = write(f"MATCH (n:{label}) WHERE n.enrichment_batch = $b AND n.{key} IN $ids DETACH DELETE n", b=BATCH, ids=ids[i:i + 60])
            deleted["nodes"] += c["nodes"]
            deleted["rels"] += c["rels"]
    # orphans created by this cleanup (not those that existed before): repeat until stable
    before_orphans = {(k, i) for k, v in o.items() for i in v}
    swept: list[tuple[str, str]] = []
    while True:
        new = [(k, i) for k, v in orphans().items() for i in v if (k, i) not in before_orphans]
        if not new:
            break
        extra = {"nodes": [], "relationships": []}
        for k, i in new:
            s = snapshot(k, [i], KEYS[k])
            extra["nodes"] += s["nodes"]
            extra["relationships"] += s["relationships"]
            c = write(f"MATCH (n:{k}) WHERE n.enrichment_batch = $b AND n.{KEYS[k]} = $id DETACH DELETE n", b=BATCH, id=i)
            deleted["nodes"] += c["nodes"]
            deleted["rels"] += c["rels"]
            swept.append((k, i))
        backup.setdefault("swept_orphans", []).append(extra)
    backup["swept"] = swept
    path.write_text(json.dumps(backup, default=str), encoding="utf-8")
    after = source_checksum()
    result = {"deleted_nodes": deleted["nodes"], "deleted_relationships": deleted["rels"], "swept_orphans": [f"{k}:{i}" for k, i in swept],
              "source_checksum_unchanged": before == after, "backup": path.name}
    print(json.dumps(result, indent=1))
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "plan"))
