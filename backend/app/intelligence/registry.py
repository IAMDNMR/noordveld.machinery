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
    IntentSpec(Intent.PART_TO_MACHINE, "Part to machine", "Machines a part fits.", Kind.PART, (),
               ("PART_FITMENT",), "machine", "(Part)-[FITS]->(Machine)", _PROV_EDGE, "Which machines use {part}?"),
    IntentSpec(Intent.MACHINE_TO_PART, "Machine to parts", "Parts that fit a machine, optionally within one category.", Kind.MACHINE, (Kind.CATEGORY,),
               ("MACHINE_CORE", "MACHINE_PARTS"), "part", "(Part)-[FITS]->(Machine)", _PROV_EDGE, "Which parts fit the {machine}?"),
    IntentSpec(Intent.PART_TO_CATEGORY, "Part category", "Category and subcategory of a part.", Kind.PART, (),
               ("PART_CATEGORY",), "category", "(Part)-[IN_CATEGORY|IN_SUBCATEGORY]->(Category)", "Category data_status."),
    IntentSpec(Intent.PART_TO_ASSEMBLY, "Part to assembly", "Assemblies that contain a part.", Kind.PART, (),
               ("PART_ASSEMBLIES",), "assembly", "(Part)-[PART_OF]->(Assembly)", _PROV_EDGE, "What assemblies contain {part}?"),
    IntentSpec(Intent.ASSEMBLY_TO_PART, "Assembly components", "Parts that make up an assembly.", Kind.ASSEMBLY, (),
               ("ASSEMBLY_CORE", "ASSEMBLY_PARTS"), "part", "(Part)-[PART_OF]->(Assembly)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_PART, "Related parts", "Parts linked to a part by an explicit graph relationship. Never states interchangeability.", Kind.PART, (),
               ("PART_RELATED",), "relationship", "(Part)-[RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(Part)", _PROV_EDGE, "Which parts are related to {part}?"),
    IntentSpec(Intent.PART_TO_SUPPLIER, "Part suppliers", "Suppliers explicitly connected to a part.", Kind.PART, (),
               ("PART_SUPPLIERS",), "supplier", "(Part)-[SUPPLIED_BY]->(Supplier)", _PROV_EDGE, "Which suppliers are connected to {part}?"),
    IntentSpec(Intent.PART_TO_DEALER, "Part dealers", "Dealers that stock a part.", Kind.PART, (),
               ("PART_DEALERS",), "dealer", "(Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_LOCATION, "Part locations", "Warehouses, dealers and suppliers connected to a part, with their stated city and country.", Kind.PART, (),
               ("PART_WAREHOUSES", "PART_DEALERS", "PART_SUPPLIERS"), "stock", "(Part)-[AVAILABLE_AT|STOCKED_BY|SUPPLIED_BY]->(Warehouse|Dealer|Supplier)", _PROV_EDGE, "Where is {part} available?"),
    IntentSpec(Intent.PART_TO_INVENTORY, "Part inventory", "Stock recorded for a part. Missing stock is unknown, not zero.", Kind.PART, (),
               ("PART_WAREHOUSES", "PART_DEALERS"), "stock", "(Part)-[AVAILABLE_AT]->(Warehouse); (Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.PART_TO_COMPLIANCE, "Part compliance", "Compliance requirements connected to a part.", Kind.PART, (),
               ("PART_COMPLIANCE",), "compliance", "(Part)-[HAS_COMPLIANCE]->(ComplianceRequirement)", _PROV_EDGE),
    IntentSpec(Intent.PART_PROVENANCE, "Part provenance", "Where a part's data comes from and how it is classified.", Kind.PART, (),
               ("PART_CORE", "PART_RELATIONSHIPS"), "metric", "(Part)-[*1]-(any)", _PROV_EDGE, "What is the provenance of {part}?"),
    IntentSpec(Intent.PART_GRAPH, "Part relationships", "Counts of everything directly connected to a part.", Kind.PART, (),
               ("PART_RELATIONSHIPS",), "path", "(Part)-[*1]-(any)", _PROV_EDGE, "Show the relationships for {part}."),
    IntentSpec(Intent.MACHINE_GRAPH, "Machine overview", "What a machine is connected to.", Kind.MACHINE, (),
               ("MACHINE_CORE",), "path", "(Machine)-[*1]-(any)", "Machine node data_status."),
    IntentSpec(Intent.SUPPLIER_GRAPH, "Supplier overview", "Parts and categories connected to a supplier.", Kind.SUPPLIER, (),
               ("SUPPLIER_CORE", "SUPPLIER_PARTS"), "part", "(Part)-[SUPPLIED_BY]->(Supplier)", _PROV_EDGE),
    IntentSpec(Intent.DEALER_GRAPH, "Dealer overview", "Parts and machine families connected to a dealer.", Kind.DEALER, (),
               ("DEALER_CORE", "DEALER_PARTS"), "part", "(Part)-[STOCKED_BY]->(Dealer)", _PROV_EDGE),
    IntentSpec(Intent.DATA_QUALITY, "Data quality", "Which relationships are missing across the catalogue.", None, (),
               ("DATA_QUALITY",), "metric", "counts only", "Computed in Neo4j."),
    IntentSpec(Intent.UNSUPPORTED, "Not supported", "Outside what the graph can answer.", None, (), (), "none", "", ""),
)

REGISTRY: dict[Intent, IntentSpec] = {s.intent: s for s in _SPECS}


def spec_for(intent: Intent) -> IntentSpec:
    return REGISTRY[intent]


def answerable_intents() -> list[Intent]:
    return [i for i in REGISTRY if i is not Intent.UNSUPPORTED]
