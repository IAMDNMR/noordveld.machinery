"""In-memory model of everything the foundation adds, plus a loader for the parts of the existing graph it attaches to.

Nothing here talks to Neo4j except `load_existing` (read-only). `Model` collects nodes and relationships; seed.py writes them.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from common import BATCH, prov, read

# primary label -> property that holds its unique id
KEYS = {
    "Dealer": "dealer_id", "Supplier": "supplier_id", "Customer": "customer_id", "Warehouse": "warehouse_id", "ShipTo": "shipto_id", "Carrier": "carrier_id",
    "TransportOption": "transport_option_id", "FreightRate": "freight_rate_id", "Address": "address_id", "Location": "location_id", "Region": "region_id",
    "DealerContact": "contact_id", "SupplierContact": "contact_id", "CustomerContact": "contact_id", "ServiceCentre": "service_centre_id", "Capability": "capability_id",
    "Industry": "industry_id", "PostalArea": "postal_area_id", "TransportTerminal": "terminal_id", "TransportRoute": "route_id", "TransportLeg": "leg_id",
    "DataSource": "source_id",
    # existing labels that new relationships point at
    "Part": "part_id", "Machine": "machine_id", "MachineFamily": "family_id", "Category": "category_id", "ShippingRate": "rate_id", "ServicePlan": "service_plan_id",
}


@dataclass
class Model:
    nodes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=lambda: defaultdict(dict))   # label -> id -> props
    extra_labels: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    rels: dict[str, dict[str, dict[str, Any]]] = field(default_factory=lambda: defaultdict(dict))     # type -> rel_id -> row

    def node(self, label: str, id_: str, props: dict[str, Any], extra: tuple[str, ...] = ()) -> str:
        if id_ in self.nodes[label]:
            raise ValueError(f"duplicate node {label} {id_}")
        self.nodes[label][id_] = {KEYS[label]: id_, **props}
        if extra:
            self.extra_labels[(label, id_)] = extra
        return id_

    def rel(self, type_: str, a: tuple[str, str], b: tuple[str, str], sheet: str, props: dict[str, Any] | None = None, suffix: str = "", status: str = "SYNTHETIC_DEMO") -> None:
        rel_id = f"{type_}:{a[1]}>{b[1]}{suffix}"
        if rel_id in self.rels[type_]:
            raise ValueError(f"duplicate relationship {rel_id}")
        self.rels[type_][rel_id] = {"type": type_, "a_label": a[0], "a_id": a[1], "b_label": b[0], "b_id": b[1], "rel_id": rel_id,
                                    "props": {**prov(sheet, rel_id, status), "demo_marker": "SYNTHETIC_DEMO_DATA" if status == "SYNTHETIC_DEMO" else status, **(props or {})}}

    def has(self, label: str, id_: str) -> bool:
        return id_ in self.nodes[label]

    def counts(self) -> tuple[dict[str, int], dict[str, int]]:
        return ({k: len(v) for k, v in self.nodes.items() if v}, {k: len(v) for k, v in self.rels.items() if v})


def node_props(sheet: str, id_: str, props: dict[str, Any], status: str = "SYNTHETIC_DEMO") -> dict[str, Any]:
    marker = {"demo_marker": "SYNTHETIC_DEMO_DATA"} if status == "SYNTHETIC_DEMO" else {}
    return {**prov(sheet, id_, status), **marker, **props}


@dataclass
class Existing:
    parts: list[dict[str, Any]]
    machines: list[dict[str, Any]]
    families: list[dict[str, Any]]
    dealers: list[dict[str, Any]]
    suppliers: list[dict[str, Any]]
    customers: list[dict[str, Any]]
    warehouses: list[dict[str, Any]]
    regions: list[dict[str, Any]]
    locations: list[dict[str, Any]]
    option_ids: set[str]
    carrier_ids: set[str]
    shipto_ids: set[str]
    all_ids: dict[str, set[str]]
    service_plan_parts: dict[str, list[str]]  # machine_id -> part ids required by its service plans
    existing_dealer_families: dict[str, list[str]]
    existing_dealer_capability: dict[str, list[str]]
    existing_part_dealers: set[tuple[str, str]]
    existing_part_suppliers: set[tuple[str, str]]
    existing_stock_total: dict[str, int]


def load_existing() -> Existing:
    parts = read("""MATCH (p:Part) OPTIONAL MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p) OPTIONAL MATCH (pr:Price)-[:PRICES_PART]->(p)
                    RETURN p.part_id AS id, p.part_number AS number, p.name AS name, p.category AS category, p.subcategory AS subcategory,
                           c.part_status AS status, c.orderable AS orderable, c.availability_state AS availability, pr.list_price_ex_vat AS price,
                           [(p)-[:FITS]->(m:Machine) | m.machine_id] AS machines ORDER BY id""")
    machines = read("""MATCH (m:Machine) OPTIONAL MATCH (m)-[:MEMBER_OF_FAMILY]->(f:MachineFamily) OPTIONAL MATCH (m)-[:MANUFACTURED_AT]->(pl:Plant)
                       RETURN m.machine_id AS id, m.model_code AS code, m.machine_type AS type, f.family_id AS family, pl.name AS plant ORDER BY id""")
    families = read("MATCH (f:MachineFamily) RETURN f.family_id AS id, f.name AS name ORDER BY id")
    dealers = read("MATCH (d:Dealer) WHERE coalesce(d.enrichment_batch,'') <> $b AND NOT coalesce(d.canonical_dataset, '') STARTS WITH 'network_' RETURN d.dealer_id AS id, d.name AS name, d.city AS city, d.country_code AS cc ORDER BY id", b=BATCH)
    suppliers = read("MATCH (s:Supplier) WHERE coalesce(s.enrichment_batch,'') <> $b AND NOT coalesce(s.canonical_dataset, '') STARTS WITH 'network_' RETURN s.supplier_id AS id, s.name AS name, s.city AS city, s.country_code AS cc ORDER BY id", b=BATCH)
    customers = read("MATCH (c:Customer) WHERE coalesce(c.enrichment_batch,'') <> $b RETURN c.customer_id AS id, c.name AS name, c.city AS city, c.country_code AS cc ORDER BY id", b=BATCH)
    warehouses = read("MATCH (w:Warehouse) WHERE coalesce(w.enrichment_batch,'') <> $b RETURN w.warehouse_id AS id, w.name AS name, w.city AS city, w.country_code AS cc, w.latitude AS lat, w.longitude AS lon ORDER BY id", b=BATCH)
    regions = read("MATCH (r:Region) WHERE coalesce(r.enrichment_batch,'') <> $b RETURN r.region_id AS id, r.name AS name, r.country_code AS cc ORDER BY id", b=BATCH)
    locations = read("MATCH (l:Location) WHERE coalesce(l.enrichment_batch,'') <> $b RETURN l.location_id AS id, l.name AS name, l.location_type AS type, l.country_code AS cc ORDER BY id", b=BATCH)
    ids: dict[str, set[str]] = {}
    for label, key in [("Dealer", "dealer_id"), ("Supplier", "supplier_id"), ("Customer", "customer_id"), ("Warehouse", "warehouse_id"), ("ShipTo", "shipto_id"),
                       ("Carrier", "carrier_id"), ("TransportOption", "transport_option_id"), ("FreightRate", "freight_rate_id"), ("Address", "address_id"),
                       ("Location", "location_id"), ("Region", "region_id"), ("DealerContact", "contact_id"), ("SupplierContact", "contact_id"),
                       ("CustomerContact", "contact_id"), ("DataSource", "source_id")]:
        ids[label] = {r["i"] for r in read(f"MATCH (n:`{label}`) WHERE coalesce(n.enrichment_batch, '') <> $b RETURN n.{key} AS i", b=BATCH)}
    sp: dict[str, list[str]] = defaultdict(list)
    for r in read("MATCH (s:ServicePlan)-[:FOR_MACHINE]->(m:Machine) MATCH (s)-[:REQUIRES_PART]->(p:Part) RETURN m.machine_id AS m, collect(DISTINCT p.part_id) AS parts"):
        sp[r["m"]] = r["parts"]
    fam = defaultdict(list)
    for r in read("MATCH (d:Dealer)-[r:SERVES_FAMILY]->(f:MachineFamily) WHERE coalesce(r.enrichment_batch,'') <> $b RETURN d.dealer_id AS d, f.family_id AS f ORDER BY d, f", b=BATCH):
        fam[r["d"]].append(r["f"])
    cap = {r["id"]: r["c"] or [] for r in read("MATCH (d:Dealer) WHERE coalesce(d.enrichment_batch,'') <> $b AND NOT coalesce(d.canonical_dataset, '') STARTS WITH 'network_' RETURN d.dealer_id AS id, d.service_capability AS c", b=BATCH)}
    pd = {(r["p"], r["d"]) for r in read("MATCH (p:Part)-[r:STOCKED_BY]->(d:Dealer) WHERE coalesce(r.enrichment_batch,'') <> $b RETURN p.part_id AS p, d.dealer_id AS d", b=BATCH)}
    ps = {(r["p"], r["s"]) for r in read("MATCH (p:Part)-[r:SUPPLIED_BY]->(s:Supplier) WHERE coalesce(r.enrichment_batch,'') <> $b RETURN p.part_id AS p, s.supplier_id AS s", b=BATCH)}
    stock = {r["p"]: r["n"] for r in read("MATCH (p:Part)-[a:AVAILABLE_AT]->(:Warehouse) WHERE coalesce(a.enrichment_batch,'') <> $b RETURN p.part_id AS p, sum(coalesce(a.available,0)) AS n", b=BATCH)}
    return Existing(parts, machines, families, dealers, suppliers, customers, warehouses, regions, locations, ids["TransportOption"], ids["Carrier"], ids["ShipTo"], ids,
                    dict(sp), dict(fam), cap, pd, ps, stock)
