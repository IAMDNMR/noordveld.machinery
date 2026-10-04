"""The controlled intent registry. An intent is the only thing that can select a query; unknown intents are rejected.

Each spec documents what it needs, which fixed queries it runs, the relationship path it may return as evidence and how
provenance is carried. `query` names constants in app/graph/queries/intelligence.py (or the Parts Store search for PART_SEARCH).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.models import Intent, Kind


@dataclass(frozen=True)
class IntentSpec:
    intent: Intent
    label: str
    description: str
    required: Kind | None
    optional: tuple[Kind, ...]
    queries: tuple[str, ...]
    result_type: str  # the ResultItem kind(s) produced
    path: str  # relationship path the evidence may use
    provenance: str
    example: str | None = None


_PROV_EDGE = "Edge data_status of each relationship returned."

_SPECS = (
    IntentSpec(Intent.PART_SEARCH, "Part search", "Find parts by name, number, legacy reference, category or machine.", None, (Kind.MACHINE, Kind.CATEGORY),
               ("parts.LIST_PARTS", "parts.PART_SUMMARIES"), "part", "(Part)", "Part node data_status."),
    IntentSpec(Intent.PART_TO_MACHINE, "Part to machine", "Machines a part fits, or whether a part fits one named machine.", Kind.PART, (Kind.MACHINE,),
               ("PART_FITMENT",), "machine", "(Part)-[FITS]->(Machine)", _PROV_EDGE, "Which machines use {part}?"),
    IntentSpec(Intent.MACHINE_TO_PART, "Machine to parts", "Parts that fit a machine, optionally within one category.", Kind.MACHINE, (Kind.CATEGORY,),
               ("MACHINE_CORE", "MACHINE_PARTS"), "part", "(Part)-[FITS]->(Machine)", _PROV_EDGE, "Which parts fit the {machine}?"),
    IntentSpec(Intent.PART_TO_CATEGORY, "Part category", "Category and subcategory of a part.", Kind.PART, (),
               ("PART_CATEGORY",), "category", "(Part)-[IN_CATEGORY|IN_SUBCATEGORY]->(Category)", "Category data_status."),
    IntentSpec(Intent.PART_TO_ASSEMBLY, "Part to assembly", "Assemblies that contain a part.", Kind.PART, (),
               ("PART_ASSEMBLIES",), "assembly", "(Part)-[PART_OF]->(Assembly)", _PROV_EDGE, "What assemblies contain {part}?"),
    IntentSpec(Intent.ASSEMBLY_TO_PART, "Assembly components", "Parts that make up an assembly.", Kind.ASSEMBLY, (),
               ("ASSEMBLY_CORE", "ASSEMBLY_PARTS"), "part", "(Part)-[PART_OF]->(Assembly)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_PART, "Related parts", ("Parts linked to a part by an explicit graph relationship. Also the intent for questions about alternatives, replacements, substitutes, "
                "equivalents or interchangeability of a part or of two parts: the answer shows only the stored links and never states interchangeability."), Kind.PART, (),
               ("PART_RELATED",), "relationship", "(Part)-[RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(Part)", _PROV_EDGE, "Which parts are related to {part}?"),
    IntentSpec(Intent.PART_TO_SUPPLIER, "Part suppliers", "Suppliers explicitly connected to a part.", Kind.PART, (),
               ("PART_SUPPLIERS",), "supplier", "(Part)-[SUPPLIED_BY]->(Supplier)", _PROV_EDGE, "Which suppliers are connected to {part}?"),
    IntentSpec(Intent.PART_TO_DEALER, "Part dealers", "Dealers that stock a part.", Kind.PART, (),
               ("PART_DEALERS",), "dealer", "(Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_LOCATION, "Part locations", "Where a part is available: the warehouses and dealers that hold it, with their stated city and country. Suppliers are a different question (PART_TO_SUPPLIER).", Kind.PART, (),
               ("PART_WAREHOUSES", "PART_DEALERS"), "warehouse", "(Part)-[AVAILABLE_AT|STOCKED_BY]->(Warehouse|Dealer)", _PROV_EDGE, "Where is {part} available?"),
    IntentSpec(Intent.PART_TO_WAREHOUSE, "Part warehouses", "The warehouses that hold a part, with the units recorded at each. Warehouses only: no dealers or suppliers.", Kind.PART, (),
               ("PART_WAREHOUSES",), "warehouse", "(Part)-[AVAILABLE_AT]->(Warehouse)", _PROV_EDGE, "Which warehouses have {part}?"),
    IntentSpec(Intent.WAREHOUSE_STOCK, "Warehouse stock", "The parts recorded as in stock at one named warehouse, with units. Starts from the warehouse; never from geography.", Kind.WAREHOUSE, (),
               ("WAREHOUSE_STOCK",), "part", "(Part)-[AVAILABLE_AT]->(Warehouse)", _PROV_EDGE, "What is in stock at {warehouse}?"),
    IntentSpec(Intent.PART_TO_INVENTORY, "Part inventory", "Stock recorded for a part. Missing stock is unknown, not zero.", Kind.PART, (),
               ("PART_WAREHOUSES", "PART_DEALERS"), "warehouse", "(Part)-[AVAILABLE_AT]->(Warehouse); (Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_COMPLIANCE, "Part compliance", "Compliance requirements connected to a part.", Kind.PART, (),
               ("PART_COMPLIANCE",), "compliance", "(Part)-[HAS_COMPLIANCE]->(ComplianceRequirement)", _PROV_EDGE),
    IntentSpec(Intent.PART_PROVENANCE, "Part provenance", "Where a part's data comes from and how it is classified.", Kind.PART, (),
               ("PART_CORE", "PART_RELATIONSHIPS"), "metric", "(Part)-[*1]-(any)", _PROV_EDGE, "What is the provenance of {part}?"),
    IntentSpec(Intent.PART_GRAPH, "Part relationships", "Counts of everything directly connected to a part.", Kind.PART, (),
               ("PART_RELATIONSHIPS",), "path", "(Part)-[*1]-(any)", _PROV_EDGE, "Show the relationships for {part}."),
    IntentSpec(Intent.MACHINE_GRAPH, "Machine overview", "One named machine (by model code, name or type such as 'the loader'): what it is and what it is connected to.", Kind.MACHINE, (),
               ("MACHINE_CORE",), "path", "(Machine)-[*1]-(any)", "Machine node data_status."),
    IntentSpec(Intent.MACHINE_LIST, "Machines", "The whole machine catalogue, optionally restricted to a plant or city. Only when no specific machine, model or machine type is named; a named machine ('the loader', 'AB-1000') is MACHINE_GRAPH.", None, (),
               ("MACHINE_LIST",), "machine", "(Machine)-[MEMBER_OF_FAMILY|MANUFACTURED_AT]->(...)", "Machine node data_status.", "What machines are available?"),
    IntentSpec(Intent.SHARED_PARTS, "Shared parts", "Parts recorded as fitting more than one machine, optionally including one named machine. Shared fitment is not interchangeability.", None, (Kind.MACHINE,),
               ("SHARED_PARTS",), "part", "(Part)-[FITS]->(Machine) x2+", _PROV_EDGE, "What parts are used across multiple machines?"),
    IntentSpec(Intent.PART_TO_SERVICE_PLAN, "Service plans", "Service plans that require a part, and the machine each plan is for.", Kind.PART, (),
               ("PART_SERVICE_PLANS",), "metric", "(ServicePlan)-[REQUIRES_PART]->(Part); (ServicePlan)-[FOR_MACHINE]->(Machine)", _PROV_EDGE, "Which service plans require {part}?"),
    IntentSpec(Intent.PART_TO_ORDERS, "Orders with a part", "Demo orders that contain a part, with their status and shipments. Read-only; no customer details.", Kind.PART, (),
               ("PART_ORDERS",), "order", "(Order)-[CONTAINS_LINE]->(OrderLine)-[REFERENCES_PART]->(Part)", _PROV_EDGE, "Which orders contain {part}?"),
    IntentSpec(Intent.LOW_STOCK_PARTS, "Low stock", "Parts whose catalogue availability is Limited or Backorder (the same availability the Parts Store shows), with recorded warehouse units.", None, (),
               ("LOW_STOCK_PARTS",), "part", "(PartCatalogProfile)-[PROFILES_PART]->(Part)-[AVAILABLE_AT]->(Warehouse)", "Profile and inventory data_status.", "Which parts are low on stock?"),
    IntentSpec(Intent.SUPPLIER_GRAPH, "Supplier overview", "Parts and categories connected to a supplier.", Kind.SUPPLIER, (),
               ("SUPPLIER_CORE", "SUPPLIER_PARTS"), "part", "(Part)-[SUPPLIED_BY]->(Supplier)", _PROV_EDGE),
    IntentSpec(Intent.DEALER_GRAPH, "Dealer overview", "Parts and machine families connected to a dealer.", Kind.DEALER, (),
               ("DEALER_CORE", "DEALER_PARTS"), "part", "(Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.DATA_QUALITY, "Missing information", "Which relationships are missing, for one part or across the catalogue.", None, (Kind.PART,),
               ("DATA_QUALITY", "PART_COUNTS", "PART_CORE"), "metric", "counts only", "Computed in Neo4j."),
    IntentSpec(Intent.ENTITY_PATH, "Connection path", "How two entities are connected through stored business relationships (shortest path, at most 4 steps).", Kind.PART,
               (Kind.MACHINE, Kind.SUPPLIER, Kind.DEALER, Kind.ASSEMBLY, Kind.CATEGORY), ("PATH_BETWEEN", "PATH_TO_KIND"), "path",
               "(a)-[FITS|PART_OF|SUPPLIED_BY|STOCKED_BY|AVAILABLE_AT|HAS_COMPLIANCE|CO_ORDERED_WITH|RELATED_COMPONENT|SAME_NAME_GROUP_AS|IN_CATEGORY|MEMBER_OF_FAMILY|SERVES_FAMILY*..4]-(b)",
               _PROV_EDGE, "How is {part} connected to {machine}?"),
    IntentSpec(Intent.ORDER_STATUS, "Order status", "Status, parts and shipments of one order. Read-only; customer and address are not shown.", Kind.ORDER, (),
               ("ORDER_STATUS",), "order", "(Order)-[CONTAINS_LINE]->(OrderLine)-[REFERENCES_PART]->(Part); (Order)-[HAS_SHIPMENT]->(Shipment)-[HAS_TRACKING_EVENT]->(TrackingEvent)",
               _PROV_EDGE),
    IntentSpec(Intent.GEO_LOCATION, "Locations", "Dealers, suppliers or warehouses by the city or country stated on their records. No coordinates exist, so no distances.", None, (),
               ("PLACES", "DEALERS_IN", "SUPPLIERS_IN", "WAREHOUSES_IN"), "dealer", "stated city / country_code properties", "Entity data_status."),
    IntentSpec(Intent.UNSUPPORTED, "Not supported", "Outside what the graph can answer.", None, (), (), "none", "", ""),
)

REGISTRY: dict[Intent, IntentSpec] = {s.intent: s for s in _SPECS}


def spec_for(intent: Intent) -> IntentSpec:
    return REGISTRY[intent]


def answerable_intents() -> list[Intent]:
    return [i for i in REGISTRY if i is not Intent.UNSUPPORTED]


# What each intent is allowed to put in the result list (ResultItem.kind). Everything else the query walked through is supporting
# evidence, never a result card. app/intelligence/contract.py enforces this after every handler.
RESULT_KINDS: dict[Intent, tuple[str, ...]] = {
    Intent.PART_SEARCH: ("part",), Intent.PART_TO_MACHINE: ("machine",), Intent.MACHINE_TO_PART: ("part",), Intent.PART_TO_CATEGORY: ("category",),
    Intent.PART_TO_ASSEMBLY: ("assembly",), Intent.ASSEMBLY_TO_PART: ("part",), Intent.PART_TO_PART: ("part",), Intent.PART_TO_SUPPLIER: ("supplier",),
    Intent.PART_TO_DEALER: ("dealer",), Intent.PART_TO_LOCATION: ("warehouse", "dealer"), Intent.PART_TO_WAREHOUSE: ("warehouse",),
    Intent.PART_TO_INVENTORY: ("warehouse", "dealer"), Intent.WAREHOUSE_STOCK: ("part",), Intent.PART_TO_COMPLIANCE: ("compliance",),
    Intent.PART_PROVENANCE: ("metric",), Intent.PART_GRAPH: ("path",), Intent.MACHINE_GRAPH: ("machine",), Intent.MACHINE_LIST: ("machine",),
    Intent.SHARED_PARTS: ("part",), Intent.PART_TO_SERVICE_PLAN: ("service_plan",), Intent.PART_TO_ORDERS: ("order",), Intent.LOW_STOCK_PARTS: ("part",),
    Intent.SUPPLIER_GRAPH: ("part",), Intent.DEALER_GRAPH: ("part",), Intent.DATA_QUALITY: ("metric",), Intent.ENTITY_PATH: ("path",),
    Intent.ORDER_STATUS: ("order", "shipment"), Intent.GEO_LOCATION: ("dealer", "supplier", "warehouse"), Intent.UNSUPPORTED: (),
}

# One short line per intent for the understanding prompt (the model only needs to tell them apart; the full description is for people).
HINTS: dict[Intent, str] = {
    Intent.PART_SEARCH: "find parts by name, number, category or machine",
    Intent.PART_TO_MACHINE: "machines a named part fits; does a part fit a machine",
    Intent.MACHINE_TO_PART: "parts that fit a named machine, optionally one category",
    Intent.PART_TO_CATEGORY: "category of a part",
    Intent.PART_TO_ASSEMBLY: "assemblies containing a part",
    Intent.ASSEMBLY_TO_PART: "parts in a named assembly",
    Intent.PART_TO_PART: "related parts; alternatives, replacements, interchangeability (stored links only)",
    Intent.PART_TO_SUPPLIER: "suppliers of a part; primary supplier; lead time",
    Intent.PART_TO_DEALER: "dealers stocking a part",
    Intent.PART_TO_LOCATION: "where a part is available (warehouses and dealers)",
    Intent.PART_TO_WAREHOUSE: "which warehouses hold a part, with units",
    Intent.PART_TO_INVENTORY: "stock quantity of a part",
    Intent.WAREHOUSE_STOCK: "what is in stock at one named warehouse",
    Intent.PART_TO_COMPLIANCE: "compliance requirements or certification of a part",
    Intent.PART_PROVENANCE: "where a part's data comes from; real or demo",
    Intent.PART_GRAPH: "everything directly connected to a part",
    Intent.MACHINE_GRAPH: "about one named machine, model or machine type",
    Intent.MACHINE_LIST: "list the machines; no specific machine named",
    Intent.SHARED_PARTS: "parts fitting several machines",
    Intent.PART_TO_SERVICE_PLAN: "service plans requiring a part",
    Intent.PART_TO_ORDERS: "orders containing a part",
    Intent.LOW_STOCK_PARTS: "catalogue-wide low-stock or backorder parts; no warehouse named",
    Intent.SUPPLIER_GRAPH: "parts of one named supplier",
    Intent.DEALER_GRAPH: "parts stocked by one named dealer",
    Intent.DATA_QUALITY: "missing information or data gaps, for a part or the catalogue",
    Intent.ENTITY_PATH: "how two named things are connected",
    Intent.ORDER_STATUS: "status or shipment of one order",
    Intent.GEO_LOCATION: "dealers, suppliers or warehouses in a city or country",
}
