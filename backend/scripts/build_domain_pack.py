"""Build the Noordveld Machinery domain pack from repository sources. Deterministic; reads files only.

Sources (all in this repository):
  graph/schema/node_schema.csv, relationship_schema.csv, identifier_contract.md  - labels, properties, relationships
  data/canonical/lifecycle/*.csv, commerce/inventory.csv                          - lifecycle and stock record shapes
  app/design_studio/knowledge/packs/noordveld_spare_parts.json                    - rules, open decisions, workflows

Classification of labels into domains, attribute types inferred from property names, and the curated synonyms below are
editorial; each is marked `derived` / `needs_review` rather than verified. Run:  python scripts/build_domain_pack.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.domain_knowledge.models import DomainPack  # noqa: E402
from app.domain_knowledge.packs import canonical_bytes  # noqa: E402

VERSION = "1.1.0"
OUT = ROOT / "app" / "domain_knowledge" / "packs" / f"noordveld_machinery-{VERSION}.json"
BUILDER = "scripts/build_domain_pack.py"

DOMAINS = [
    ("dom_core", "Core business", None, [], "Parties, places, provenance and reference data every domain reuses.", ["customer", "address", "region", "location", "business unit"]),
    ("dom_machinery", "Manufacturing and machinery", "dom_core", [], "Machine models, types, families, variants, plants and installed units.", ["machine", "tractor", "harvester", "model", "variant", "plant", "serial"]),
    ("dom_spare_parts", "Spare-parts management", "dom_machinery", ["dom_machinery"], "Parts, categories, specifications, fitment, legacy numbers and assemblies.", ["part", "spare", "fitment", "compatible", "legacy", "category", "specification"]),
    ("dom_inventory", "Inventory and warehouse management", "dom_core", ["dom_spare_parts"], "Warehouses, stock levels and availability.", ["stock", "inventory", "warehouse", "depot", "availability"]),
    ("dom_procurement", "Procurement and supplier management", "dom_core", ["dom_spare_parts"], "Suppliers, approved sources and backorders.", ["supplier", "procurement", "backorder", "sourcing"]),
    ("dom_customer_dealer", "Customer and dealer management", "dom_core", [], "Customers, dealers and the machine families dealers serve.", ["dealer", "customer", "account", "service network"]),
    ("dom_pricing", "Finance, pricing and credit", "dom_core", ["dom_spare_parts"], "Prices and their validity. Credit is not modelled.", ["price", "pricing", "credit", "invoice", "currency"]),
    ("dom_commerce", "E-commerce and order management", "dom_core", ["dom_spare_parts", "dom_inventory", "dom_customer_dealer", "dom_pricing"], "Carts, orders, order lines, allocation and status history.", ["order", "cart", "checkout", "e-commerce", "ordering", "allocation"]),
    ("dom_logistics", "Logistics and transportation", "dom_core", ["dom_commerce", "dom_inventory"], "Shipments, carriers, tracking events, rates and delivery estimates.", ["shipment", "delivery", "tracking", "carrier", "logistics", "freight"]),
    ("dom_service", "Service, maintenance and warranty", "dom_machinery", ["dom_spare_parts", "dom_customer_dealer"], "Service plans, work orders, installations, replacements and warranty claims.", ["warranty", "claim", "service", "maintenance", "repair", "technician", "work order"]),
]

LABEL_DOMAIN = {
    "Address": "dom_core", "BusinessUnit": "dom_core", "DataSource": "dom_core", "Location": "dom_core", "Region": "dom_core",
    "Machine": "dom_machinery", "MachineFamily": "dom_machinery", "MachineSpecification": "dom_machinery", "MachineType": "dom_machinery",
    "MachineVariant": "dom_machinery", "Plant": "dom_machinery",
    "Part": "dom_spare_parts", "Category": "dom_spare_parts", "PartSpecification": "dom_spare_parts", "LegacyReference": "dom_spare_parts",
    "Assembly": "dom_spare_parts", "PartCatalogProfile": "dom_spare_parts", "SearchAlias": "dom_spare_parts",
    "IdentificationRequirement": "dom_spare_parts", "ComplianceRequirement": "dom_spare_parts",
    "Warehouse": "dom_inventory", "Supplier": "dom_procurement", "SupplierBackorder": "dom_procurement",
    "Customer": "dom_customer_dealer", "Dealer": "dom_customer_dealer", "Price": "dom_pricing",
    "Cart": "dom_commerce", "CartLine": "dom_commerce", "Order": "dom_commerce", "OrderLine": "dom_commerce",
    "OrderStatus": "dom_commerce", "OrderStatusEvent": "dom_commerce",
    "Shipment": "dom_logistics", "Carrier": "dom_logistics", "TrackingEvent": "dom_logistics", "ShippingRate": "dom_logistics",
    "DeliveryEstimate": "dom_logistics", "ServicePlan": "dom_service",
}

# Lifecycle and stock records exist as canonical CSVs but not as graph labels.
CSV_ENTITIES = [
    ("MachineInstance", "data/canonical/lifecycle/machine_instances.csv", "dom_machinery", "A serial-numbered machine unit owned by a customer.", "machine_instance_id"),
    ("Installation", "data/canonical/lifecycle/installations.csv", "dom_service", "A part fitted to a machine unit by a dealer.", "installation_id"),
    ("Replacement", "data/canonical/lifecycle/replacements.csv", "dom_service", "A part removed from a unit and replaced by another.", "replacement_id"),
    ("WorkOrder", "data/canonical/lifecycle/work_orders.csv", "dom_service", "A dealer service visit on a machine unit.", "work_order_id"),
    ("Technician", "data/canonical/lifecycle/technicians.csv", "dom_service", "A dealer technician and their certification.", "technician_id"),
    ("WarrantyClaim", "data/canonical/lifecycle/warranty_claims.csv", "dom_service", "A claim that a failed part is covered by warranty.", "claim_id"),
    ("InventoryRecord", "data/canonical/commerce/inventory.csv", "dom_inventory", "Stock of one part at one location.", "inventory_id"),
]
CSV_RELATIONSHIPS = [
    ("MachineInstance", "INSTANCE_OF", "Machine", "many_to_one", True, "A unit is one machine model."),
    ("Installation", "INSTALLED_ON", "MachineInstance", "many_to_one", True, "The unit the part was fitted to."),
    ("Installation", "INSTALLS_PART", "Part", "many_to_one", True, "The part that was fitted."),
    ("Installation", "PERFORMED_BY", "Dealer", "many_to_one", False, "The dealer that fitted it."),
    ("Replacement", "REMOVED_PART", "Part", "many_to_one", True, "The part taken out."),
    ("Replacement", "INSTALLED_PART", "Part", "many_to_one", True, "The part put in."),
    ("WorkOrder", "SERVICES", "MachineInstance", "many_to_one", True, "The unit serviced."),
    ("WorkOrder", "ASSIGNED_TO", "Technician", "many_to_one", False, "The technician doing the work."),
    ("Technician", "EMPLOYED_BY", "Dealer", "many_to_one", True, "The technician's dealer."),
    ("WarrantyClaim", "COVERS", "Part", "many_to_one", True, "The failed part claimed for."),
    ("WarrantyClaim", "FOR_UNIT", "MachineInstance", "many_to_one", True, "The unit the part failed on."),
    ("WarrantyClaim", "CLAIMS_INSTALLATION", "Installation", "many_to_one", False, "The installation being claimed against."),
    ("WarrantyClaim", "SUBMITTED_BY", "Dealer", "many_to_one", True, "The dealer submitting the claim."),
    ("InventoryRecord", "STOCKS", "Part", "many_to_one", True, "The part held."),
]
# Curated synonyms, valid inside the named domain only. Deliberately few: similar words with different meanings
# (e.g. a service plan's "part" list vs. a catalogue part) are not merged.
SYNONYMS = {
    "Part": [("spare part", "dom_spare_parts"), ("replacement part", "dom_spare_parts"), ("service part", "dom_service")],
    "Warehouse": [("depot", "dom_inventory"), ("stock location", "dom_inventory")],
    "Machine": [("machine model", "dom_machinery")],
    "MachineInstance": [("machine unit", "dom_machinery"), ("installed machine", "dom_service")],
    "Order": [("purchase order", "dom_commerce"), ("sales order", "dom_commerce")],
    "LegacyReference": [("legacy part number", "dom_spare_parts"), ("superseded number", "dom_spare_parts")],
    "Shipment": [("consignment", "dom_logistics")],
    "Dealer": [("service partner", "dom_customer_dealer")],
}
ACRONYMS = {"OrderLine": ["OL"], "WorkOrder": ["WO"], "BusinessUnit": ["BU"], "SupplierBackorder": ["BO"]}
PERSONAL = {"name", "email", "phone", "street", "house_number", "postal_code", "contact_name", "contact_email", "contact_phone", "serial_number", "address_note", "owner_id"}
PROVENANCE_COLUMNS = {"provenance_type", "data_status", "source_id", "source_file", "source_sheet", "source_record_id", "source_name", "source_ref",
                      "confidence", "authoritative_flag", "last_updated", "source_type", "ingestion_timestamp", "effective_from", "effective_to", "rel_id"}
DESIGN_ENTITY = {"ent_part": "part", "ent_machine": "machine", "ent_fitment": "part", "ent_depot": "warehouse", "ent_inventory": "inventory_record",
                 "ent_ship_to": "address", "ent_route": "shipment", "ent_dealer": "dealer", "ent_order": "order", "ent_order_line": "order_line",
                 "ent_status_event": "order_status_event", "ent_shipment": "shipment", "ent_tracking_event": "tracking_event",
                 "ent_warranty_policy": "warranty_claim", "ent_warranty_claim": "warranty_claim"}
RULE_SOURCE = {"implemented_code": ("verified_source", "verified"), "document": ("verified_source", "verified"), "graph_data": ("verified_source", "needs_review"),
               "business_owner": ("user_provided", "verified"), "workshop": ("user_provided", "unverified"), "synthetic_assumption": ("assumption", "unverified")}
CODE_LISTS = {"order_status": ("Order status", "dom_commerce", ["NEW", "CONFIRMED", "PROCESSING", "ALLOCATED", "SHIPPED", "DELIVERED"],
                               "graph/cypher/01_reference_nodes.cypher (OrderStatus, USER_PROVIDED)")}


def snake(label: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", label).lower()


def provenance(raw: str, ref: str) -> dict:
    raw = raw.strip()
    if raw == "SOURCE_DERIVED":
        return {"kind": "verified_source", "reference": ref, "verification": "verified"}
    if raw == "SYNTHETIC_DEMO":
        return {"kind": "synthetic", "reference": ref, "verification": "unverified"}
    if raw == "USER_PROVIDED":
        return {"kind": "user_provided", "reference": ref, "verification": "unverified"}
    if "SYNTHETIC_DEMO" in raw:  # mixed synthetic and other: the weakest claim wins
        return {"kind": "synthetic", "reference": f"{ref} ({raw})", "verification": "unverified"}
    return {"kind": "derived", "reference": f"{ref} ({raw})", "verification": "needs_review"}


VALUE = re.compile(r'(\w+):\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null|\[[^\]]*\])')
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def graph_observations() -> dict[tuple[str, str], list]:
    """Every property value the generated graph seed (graph/cypher/*.cypher) writes, per (label, property)."""
    seen: dict[tuple[str, str], list] = {}
    for path in sorted((ROOT / "graph/cypher").glob("*.cypher")):
        text = path.read_text(encoding="utf-8")
        for block in re.finditer(r"UNWIND \[\n(.*?)\n\] AS row\nMERGE \(n:(\w+) ", text, re.S):
            body, label = block.groups()
            for key, raw in VALUE.findall(body):
                seen.setdefault((label, key), []).append(None if raw == "null" else "list" if raw.startswith("[") else json.loads(raw))
    return seen


def csv_observations(path: Path) -> dict[str, list]:
    seen: dict[str, list] = {}
    for row in read_csv(path):
        for key, value in row.items():
            seen.setdefault(key, []).append(value if value != "" else None)
    return seen


def observed_type(values: list, from_csv: bool) -> str | None:
    """The narrowest type every observed non-empty value satisfies; None without evidence."""
    present = [value for value in values if value is not None]
    if not present or any(value == "list" for value in present):
        return None
    if all(isinstance(value, bool) for value in present):
        return "boolean"
    if from_csv:
        if all(value in ("true", "false", "True", "False") for value in present):
            return "boolean"
        if all(re.fullmatch(r"-?\d+", value) for value in present):
            return "integer"
        if all(re.fullmatch(r"-?\d+(\.\d+)?", value) for value in present):
            return "decimal"
    elif all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present):
        return "integer" if all(isinstance(value, int) for value in present) else "decimal"
    if all(isinstance(value, str) and DATE.match(value) for value in present):
        return "date"
    if all(isinstance(value, str) and DATETIME.match(value) for value in present):
        return "datetime"
    return "string"


def attribute(name: str, key: bool, required: bool, evidence: list | None, source: str) -> dict:
    """Type from observed source values. Without evidence the attribute stays `string` and is marked for review."""
    kind = observed_type(evidence, source.endswith(".csv")) if evidence is not None else None
    item = {"id": name, "name": name.replace("_", " ").capitalize(), "type": kind or "string", "required": required or key, "key": key, "unique": key,
            "value_source": "imported", "mutability": "immutable" if key else "system_updated",
            "sensitivity": "personal" if name in PERSONAL else "internal"}
    if kind is None:
        item["provenance"] = {"kind": "derived", "reference": f"{BUILDER}: no observed values in {source}; type not established", "verification": "needs_review"}
    else:
        count = sum(1 for value in evidence if value is not None)
        item["provenance"] = {"kind": "verified_source", "reference": f"{source}: type observed in {count} value(s)", "verification": "verified"}
    return item


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))



ASSUMPTION = {"kind": "assumption", "reference": "TMS/WMS design assumption: not in any repository source and not confirmed by the business", "verification": "unverified"}
TRANSPORT_LOGIC = "backend/app/logistics/rules.py (TRANSITIONS)"


def _assumed_entity(pack: dict, entity_id: str, name: str, domain: str, description: str, attributes: list[tuple], operational: str | None = None) -> None:
    """An entity the TMS/WMS design needs but no source defines. Every attribute and the entity itself stay assumptions."""
    attrs = []
    for attr_id, kind, required, key, *rest in attributes:
        item = {"id": attr_id, "name": attr_id.replace("_", " ").capitalize(), "type": kind, "required": required or key, "key": key, "unique": key,
                "value_source": rest[0] if rest else ("system_generated" if key else "user_entered"),
                "mutability": "immutable" if key else "user_updated", "sensitivity": "internal", "provenance": dict(ASSUMPTION)}
        if (rest[0] if rest else "") not in ("", "user_entered"):
            item["mutability"] = "immutable" if key else "system_updated"
        attrs.append(item)
    concept = f"concept_{entity_id}"
    pack["concepts"].append({"id": concept, "canonical_name": name, "kind": "business_concept", "domain_id": domain, "definition": description, "provenance": dict(ASSUMPTION)})
    pack["entities"].append({"id": entity_id, "canonical_name": name, "domain_id": domain, "concept_id": concept, "description": description, "attributes": attrs,
                             "natural_keys": [a["id"] for a in attrs if a["key"]], "operational_label": operational, "provenance": dict(ASSUMPTION)})


def _grounded_entity(pack: dict, entity_id: str, name: str, domain: str, description: str, header: list[str], values: dict[str, list], key: str, source: str) -> None:
    attrs = [attribute(col, col == key, col == key, values.get(col), source) for col in header if col not in PROVENANCE_COLUMNS]
    concept = f"concept_{entity_id}"
    prov = {"kind": "synthetic", "reference": source, "verification": "unverified"}
    pack["concepts"].append({"id": concept, "canonical_name": name, "kind": "business_concept", "domain_id": domain, "definition": description, "provenance": prov})
    pack["entities"].append({"id": entity_id, "canonical_name": name, "domain_id": domain, "concept_id": concept, "description": description, "attributes": attrs,
                             "natural_keys": [key], "operational_label": None, "provenance": prov})


def extend_logistics(pack: dict) -> None:
    """Release 1.1.0: transport management (TMS) and warehouse operations (WMS) on the shared model."""
    from app.logistics.rules import TRANSITIONS
    pack["domains"].extend([
        {"id": "dom_transport", "name": "Transport management", "description": "Planning, carrier and vehicle assignment, dispatch, tracking, delivery confirmation and exception resolution.",
         "scope": "How a shipment is planned, assigned, moved and confirmed. Operational shipments and tracking events live in the operational systems, not here.", "parent_id": "dom_logistics",
         "depends_on": ["dom_logistics", "dom_core", "dom_warehouse_ops", "dom_commerce"], "capabilities": ["Transport request management", "Planning and assignment", "Carrier and vehicle management", "Capacity and eligibility validation",
                                                                                         "Dispatch", "Tracking", "Delivery confirmation and proof of delivery", "Exception resolution"],
         "keywords": ["transport", "tms", "dispatch", "planner", "carrier", "vehicle", "proof of delivery", "pod", "consignment", "route", "freight", "haulage"],
         "dependencies": [
             {"domain_id": "dom_logistics", "kind": "required", "reason": "Shipments, routes and tracking events are the records a transport plan acts on."},
             {"domain_id": "dom_core", "kind": "required", "reason": "Locations and addresses define where goods are collected and delivered."},
             {"domain_id": "dom_commerce", "kind": "required", "reason": "A transport request exists to deliver an order."},
             {"domain_id": "dom_warehouse_ops", "kind": "conditional", "reason": "Dispatch waits for fulfilment when goods leave a managed warehouse.",
              "condition": "goods are collected from a warehouse the business manages"}],
         "provenance": {"kind": "derived", "reference": f"{BUILDER}: TMS domain definition; scope follows backend/app/logistics and data/canonical/logistics", "verification": "needs_review"}},
        {"id": "dom_warehouse_ops", "name": "Warehouse operations", "description": "Allocation, picking, packing and the handoff of packed goods to transport.",
         "scope": "Tasks that turn allocated order lines into packed, handoff-ready goods.", "parent_id": "dom_inventory", "depends_on": ["dom_inventory", "dom_commerce", "dom_procurement"],
         "capabilities": ["Allocation", "Picking", "Packing", "Fulfilment handoff"],
         "keywords": ["warehouse", "wms", "picking", "pick", "packing", "pack", "fulfilment", "fulfillment", "handoff", "allocation", "operator"],
         "dependencies": [
             {"domain_id": "dom_inventory", "kind": "required", "reason": "Stock locations and quantities govern what can be picked."},
             {"domain_id": "dom_commerce", "kind": "required", "reason": "Order lines are what gets picked and packed."},
             {"domain_id": "dom_procurement", "kind": "optional", "reason": "Backorders from suppliers can change what is available to pick."}],
         "provenance": {"kind": "derived", "reference": f"{BUILDER}: WMS domain definition; allocation follows backend/app/services/order_flow.py", "verification": "needs_review"}},
    ])
    # Dependencies that existed in 1.0.0 were never classified by the business; say so instead of calling them mandatory.
    for domain in pack["domains"]:
        if not domain.get("dependencies"):
            domain["dependencies"] = [{"domain_id": dep, "kind": "unclassified", "reason": "Carried over from release 1.0.0; the business has not said whether it is mandatory."}
                                      for dep in domain["depends_on"]]

    routes = json.loads((ROOT / "data/canonical/logistics/network_routes.json").read_text(encoding="utf-8"))["records"]
    route_values: dict[str, list] = {}
    for record in routes:
        for column, value in record.items():
            route_values.setdefault(column, []).append(value if value != "" else None)
    _grounded_entity(pack, "route", "Route", "dom_transport", "A lane between two locations by a transport mode, with its service level and planned transit time.",
                     list(routes[0]), route_values, "route_id", "data/canonical/logistics/network_routes.json")
    leg_path = ROOT / "data/canonical/logistics/network_route_legs.csv"
    _grounded_entity(pack, "route_leg", "Route leg", "dom_transport", "One leg of a route: origin, destination, mode, transit days and distance.",
                     next(csv.reader(leg_path.open(encoding="utf-8"))), csv_observations(leg_path), "route_leg_id", "data/canonical/logistics/network_route_legs.csv")

    _assumed_entity(pack, "transport_request", "Transport request", "dom_transport", "A request to move goods for an order from a collection point to a delivery address.",
                    [("transport_request_id", "string", True, True), ("requested_pickup_date", "date", False, False), ("requested_delivery_date", "date", False, False),
                     ("status", "string", True, False, "system_generated"), ("special_handling", "string", False, False)])
    _assumed_entity(pack, "transport_plan", "Transport plan", "dom_transport", "The planner's decision on how a request will be moved: which carrier, vehicle and route.",
                    [("transport_plan_id", "string", True, True), ("planned_departure", "datetime", False, False), ("planned_arrival", "datetime", False, False),
                     ("status", "string", True, False, "system_generated")])
    _assumed_entity(pack, "vehicle", "Vehicle", "dom_transport", "A vehicle a carrier can assign to a plan, with its capacity.",
                    [("vehicle_id", "string", True, True), ("registration", "string", False, False), ("capacity_kg", "decimal", False, False), ("capacity_volume_m3", "decimal", False, False)])
    _assumed_entity(pack, "proof_of_delivery", "Proof of delivery", "dom_transport", "The confirmation that a shipment reached the receiver.",
                    [("pod_id", "string", True, True), ("delivered_at", "datetime", True, False), ("received_by", "string", True, False), ("evidence_reference", "string", False, False)])
    _assumed_entity(pack, "transport_exception", "Transport exception", "dom_transport", "A delay, failed delivery or other deviation that needs a decision.",
                    [("exception_id", "string", True, True), ("kind", "string", True, False), ("raised_at", "datetime", True, False), ("resolution", "string", False, False),
                     ("status", "string", True, False, "system_generated")])
    _assumed_entity(pack, "pick_task", "Pick task", "dom_warehouse_ops", "An instruction to pick the quantity of one order line from a warehouse.",
                    [("pick_task_id", "string", True, True), ("quantity", "integer", True, False), ("status", "string", True, False, "system_generated")])
    _assumed_entity(pack, "pack_unit", "Pack unit", "dom_warehouse_ops", "A parcel or pallet that holds picked goods for shipping.",
                    [("pack_unit_id", "string", True, True), ("weight_kg", "decimal", False, False), ("status", "string", True, False, "system_generated")])
    _assumed_entity(pack, "fulfilment_handoff", "Fulfilment handoff", "dom_warehouse_ops", "The point where packed goods are released to transport.",
                    [("handoff_id", "string", True, True), ("released_at", "datetime", False, False), ("status", "string", True, False, "system_generated")])

    def rel(source: str, rtype: str, target: str, cardinality: str, meaning: str, required: bool = False, grounded: str | None = None) -> None:
        provenance_ = ({"kind": "synthetic", "reference": grounded, "verification": "unverified"} if grounded else dict(ASSUMPTION))
        pack["relationships"].append({"id": f"rel_{source}_{rtype.lower()}_{target}", "source_id": source, "type": rtype, "target_id": target, "cardinality": cardinality,
                                      "meaning": meaning, "required": required, "acyclic": False, "constraints": [], "provenance": provenance_})

    leg_src = "data/canonical/logistics/network_route_legs.csv (route_id)"
    rel("route_leg", "PART_OF_ROUTE", "route", "many_to_one", "The route this leg belongs to.", True, leg_src)
    rel("shipment", "FOLLOWS_ROUTE", "route", "many_to_one", "The route a shipment is carried on.", False, "data/canonical/logistics/network_shipments.csv (route_id)")
    rel("pick_task", "FOR_LINE", "order_line", "many_to_one", "The order line being picked.", True)
    rel("pick_task", "FROM_WAREHOUSE", "warehouse", "many_to_one", "Where the goods are picked.", True)
    rel("pick_task", "PACKED_INTO", "pack_unit", "many_to_one", "The pack unit the picked goods go into.")
    rel("fulfilment_handoff", "COVERS", "pack_unit", "one_to_many", "The pack units released together.", True)
    rel("fulfilment_handoff", "HANDS_OFF_TO", "transport_request", "one_to_one", "The transport request created from the handoff.", True)
    rel("transport_request", "FOR_ORDER", "order", "many_to_one", "The order whose goods are to be moved.", True)
    rel("transport_request", "COLLECTS_AT", "warehouse", "many_to_one", "Where the goods are collected, when from a managed warehouse.")
    rel("transport_request", "DELIVERS_TO", "address", "many_to_one", "The delivery address.", True)
    rel("transport_plan", "FULFILS", "transport_request", "many_to_one", "The request this plan moves.", True)
    rel("transport_plan", "ASSIGNED_CARRIER", "carrier", "many_to_one", "The carrier chosen for the plan.", True)
    rel("transport_plan", "ASSIGNED_VEHICLE", "vehicle", "many_to_one", "The vehicle assigned, when the carrier assigns one.")
    rel("transport_plan", "USES_ROUTE", "route", "many_to_one", "The route the plan follows.")
    rel("vehicle", "OPERATED_BY", "carrier", "many_to_one", "The carrier that operates the vehicle.", True)
    rel("shipment", "EXECUTES", "transport_plan", "many_to_one", "The plan a shipment carries out.")
    rel("proof_of_delivery", "CONFIRMS", "shipment", "one_to_one", "The shipment whose delivery it confirms.", True)
    rel("transport_exception", "AFFECTS", "shipment", "many_to_one", "The shipment the exception concerns.", True)

    # Tracking-event transitions are implemented behaviour: each is a verified event from the code.
    code_prov = {"kind": "verified_source", "reference": TRANSPORT_LOGIC, "verification": "verified"}
    for source, targets in sorted(TRANSITIONS.items()):
        for target in sorted(targets):
            pack["events"].append({"id": f"evt_tracking_{source.lower()}_to_{target.lower()}", "name": f"Tracking: {source} → {target}", "entity_id": "tracking_event",
                                   "from_state": source, "to_state": target, "provenance": code_prov})
    for event_id, name, entity, state in (("evt_handoff_released", "Handoff released to transport", "fulfilment_handoff", "RELEASED"),
                                          ("evt_plan_assigned", "Transport plan assigned", "transport_plan", "ASSIGNED"),
                                          ("evt_pod_recorded", "Proof of delivery recorded", "proof_of_delivery", "RECORDED"),
                                          ("evt_transport_exception_raised", "Transport exception raised", "transport_exception", "RAISED")):
        pack["events"].append({"id": event_id, "name": name, "entity_id": entity, "from_state": "", "to_state": state, "provenance": dict(ASSUMPTION)})

    rules = [("rule_capacity_check", "decision", "A transport plan may be dispatched only if the assigned vehicle's capacity covers the load."),
             ("rule_carrier_eligibility", "decision", "A carrier may be assigned only if it is eligible for the route and the goods."),
             ("rule_delay_escalation", "policy", "A shipment past its planned arrival raises a transport exception."),
             ("rule_pod_required", "policy", "A delivery is complete only when proof of delivery is recorded."),
             ("rule_handoff_complete", "validation", "Goods are released to transport only when every pick task of the handoff is packed.")]
    for rule_id, kind, text in rules:
        pack["rules"].append({"id": rule_id, "description": text, "type": kind, "status": "assumption", "entity_ids": [],
                              "provenance": {"kind": "assumption", "reference": "TMS/WMS design assumption: the business has not stated this rule", "verification": "unverified"}})
    # The tracking sequence rule already exists (confirmed, implemented); attach the transport entities it governs.
    for rule in pack["rules"]:
        if rule["id"] == "rule_tracking_sequence":
            rule["entity_ids"] = sorted(set(rule["entity_ids"]) | {"tracking_event", "shipment"})
    by_id = {rule["id"]: rule for rule in pack["rules"]}
    by_id["rule_capacity_check"]["entity_ids"] = ["transport_plan", "vehicle"]
    by_id["rule_carrier_eligibility"]["entity_ids"] = ["transport_plan", "carrier", "route"]
    by_id["rule_delay_escalation"]["entity_ids"] = ["shipment", "transport_exception"]
    by_id["rule_pod_required"]["entity_ids"] = ["proof_of_delivery", "shipment"]
    by_id["rule_handoff_complete"]["entity_ids"] = ["fulfilment_handoff", "pick_task", "pack_unit"]

    roles = [("tms_planner", "tms", "Transport planner", ["transport.request.read", "transport.request.write", "transport.plan.write", "transport.assign"]),
             ("tms_dispatcher", "tms", "Dispatcher", ["transport.request.read", "transport.dispatch", "tracking.write", "exception.resolve"]),
             ("tms_carrier_partner", "tms", "Carrier or logistics partner", ["transport.assigned.read", "tracking.write_own", "pod.submit"]),
             ("wms_operator", "wms", "Warehouse operator", ["pick.execute", "pack.execute", "handoff.create"]),
             ("wms_inventory_manager", "wms", "Inventory manager", ["stock.adjust", "allocation.read"])]
    for role_id, app, name, permissions in roles:
        pack["app_roles"].append({"id": role_id, "application_id": app, "name": name, "description": f"{name} in the {app.upper()} application.", "permissions": permissions,
                                  "provenance": dict(ASSUMPTION)})

    pack["processes"].extend([
        {"id": "proc_transport_lifecycle", "name": "Transport lifecycle", "domain_id": "dom_transport",
         "description": "Request, planning, carrier and vehicle assignment, capacity validation, dispatch, tracking, delivery confirmation, proof of delivery and exception resolution.",
         "entity_ids": ["transport_request", "transport_plan", "vehicle", "carrier", "route", "shipment", "tracking_event", "proof_of_delivery", "transport_exception"],
         "rule_ids": ["rule_capacity_check", "rule_carrier_eligibility", "rule_delay_escalation", "rule_pod_required", "rule_tracking_sequence"],
         "event_ids": ["evt_plan_assigned", "evt_pod_recorded", "evt_transport_exception_raised", "evt_tracking_booked_to_departed_origin", "evt_tracking_departed_origin_to_delivered"],
         "roles": ["tms_planner", "tms_dispatcher", "tms_carrier_partner"], "design_template": "noordveld_transport/wf_transport_lifecycle",
         "provenance": {"kind": "derived", "reference": "Tracking steps follow backend/app/logistics/rules.py; planning, assignment and proof-of-delivery steps are design assumptions", "verification": "needs_review"}},
        {"id": "proc_warehouse_fulfilment", "name": "Warehouse fulfilment and handoff", "domain_id": "dom_warehouse_ops",
         "description": "Allocated order lines are picked, packed and released to transport.",
         "entity_ids": ["order", "order_line", "warehouse", "pick_task", "pack_unit", "fulfilment_handoff", "transport_request"],
         "rule_ids": ["rule_allocation", "rule_handoff_complete"], "event_ids": ["evt_handoff_released"], "roles": ["wms_operator", "wms_inventory_manager"],
         "design_template": "noordveld_transport/wf_warehouse_fulfilment",
         "provenance": {"kind": "derived", "reference": "Allocation follows backend/app/services/order_flow.py; picking, packing and handoff are design assumptions", "verification": "needs_review"}}])
    for decision_id, question, affects in (
            ("dec_carrier_selection", "Who selects the carrier: the planner, an automatic rule, or a customer preference, and on what criteria?", ["proc_transport_lifecycle", "rule_carrier_eligibility"]),
            ("dec_delay_threshold", "How late is late? When does a delay become an exception, and who is told?", ["rule_delay_escalation"]),
            ("dec_pod_requirements", "What counts as proof of delivery (signature, photo, code), and can a delivery be closed without it?", ["rule_pod_required", "proof_of_delivery"]),
            ("dec_partial_handoff", "May a handoff release part of an order, and does transport plan each part separately?", ["proc_warehouse_fulfilment", "fulfilment_handoff"])):
        pack["decisions"].append({"id": decision_id, "question": question, "status": "open", "answer": "", "affects": affects,
                                  "provenance": {"kind": "user_provided", "reference": "Open business-owner decision raised by the TMS/WMS design", "verification": "unverified"}})


def build() -> dict:
    nodes = read_csv(ROOT / "graph/schema/node_schema.csv")
    rels = read_csv(ROOT / "graph/schema/relationship_schema.csv")
    design = json.loads((ROOT / "app/design_studio/knowledge/packs/noordveld_spare_parts.json").read_text(encoding="utf-8"))
    pack = {"schema_version": 1, "id": "noordveld_machinery", "version": VERSION, "status": "approved",
            "title": "Noordveld Machinery domain pack",
            "description": "Domains, concepts, entities and relationships of the Noordveld spare-parts business, built from the operational graph "
                           "schema, canonical datasets and the implemented order and warranty rules. Mostly synthetic demo data; every item says so.",
            "synthetic": True, "domains": [], "concepts": [], "entities": [], "relationships": [], "events": [], "rules": [],
            "processes": [], "decisions": [], "mappings": [], "app_roles": []}
    for did, name, parent, deps, desc, keywords in DOMAINS:
        pack["domains"].append({"id": did, "name": name, "description": desc, "scope": desc, "parent_id": parent, "depends_on": deps,
                                "capabilities": [], "keywords": keywords,
                                "provenance": {"kind": "derived", "reference": f"{BUILDER}: domain classification", "verification": "needs_review"}})
    for cid, (name, domain, values, ref) in CODE_LISTS.items():
        pack["concepts"].append({"id": f"code_{cid}", "canonical_name": name, "kind": "code_list", "domain_id": domain,
                                 "definition": f"Allowed values of {name.lower()}.", "code_values": values,
                                 "provenance": {"kind": "user_provided", "reference": ref, "verification": "unverified"}})

    def add_entity(label: str, domain: str, desc: str, attrs: list[dict], prov: dict, operational: str | None):
        eid = snake(label)
        concept = {"id": f"concept_{eid}", "canonical_name": label, "kind": "business_concept", "domain_id": domain, "definition": desc,
                   "synonyms": [{"term": term, "domain_id": dom, "note": ""} for term, dom in SYNONYMS.get(label, [])],
                   "acronyms": ACRONYMS.get(label, []), "provenance": prov}
        pack["concepts"].append(concept)
        keys = [item["id"] for item in attrs if item["key"]]
        pack["entities"].append({"id": eid, "canonical_name": label, "domain_id": domain, "concept_id": concept["id"], "description": desc,
                                 "attributes": attrs, "natural_keys": keys, "operational_label": operational, "provenance": prov})

    observed = graph_observations()
    for row in nodes:
        label, key = row["label"], row["canonical_id"]
        ref = f"graph/schema/node_schema.csv#{label}"
        required = [p for p in row["required_properties"].split("|") if p and p not in PROVENANCE_COLUMNS]
        optional = [p for p in row["optional_properties"].split("|") if p and p not in PROVENANCE_COLUMNS and p not in required]
        evidence = lambda prop: observed.get((label, prop))  # noqa: E731
        attrs = [attribute(name, name == key, True, evidence(name), "graph/cypher") for name in required] + [attribute(name, False, False, evidence(name), "graph/cypher") for name in optional]
        if key not in required:
            attrs.insert(0, attribute(key, True, True, evidence(key), "graph/cypher"))
        if label == "OrderStatus":
            for item in attrs:
                if item["id"] == "order_status_code":
                    item.update(type="code", code_list_id="code_order_status")
        add_entity(label, LABEL_DOMAIN[label], row["meaning"], attrs, provenance(row["provenance"], ref), label)

    for label, path, domain, desc, key in CSV_ENTITIES:
        header = next(csv.reader((ROOT / path).open(encoding="utf-8")))
        values = csv_observations(ROOT / path)
        attrs = [attribute(name, name == key, name == key, values.get(name), path) for name in header if name not in PROVENANCE_COLUMNS]
        add_entity(label, domain, desc, attrs, {"kind": "synthetic", "reference": path, "verification": "unverified"}, None)

    entity_ids = {item["id"] for item in pack["entities"]}
    seen = set()
    for row in rels:
        source, target = snake(row["from_label"]), snake(row["to_label"])
        cardinality = {"N:M": "many_to_many", "N:1": "many_to_one", "1:N": "one_to_many", "1:1": "one_to_one"}.get(row["cardinality"][:3].strip(), "many_to_many")
        rid = f"rel_{source}_{row['relationship'].lower()}_{target}"
        if rid in seen:
            continue
        seen.add(rid)
        pack["relationships"].append({"id": rid, "source_id": source, "type": row["relationship"], "target_id": target, "cardinality": cardinality,
                                      "meaning": row["meaning"], "required": "exactly one" in row["cardinality"],
                                      "acyclic": row["relationship"] in ("SUBCATEGORY_OF", "PART_OF"),
                                      "constraints": [f"inference allowed: {row['inference_allowed']}", f"synthetic allowed: {row['synthetic_allowed']}"],
                                      "provenance": provenance(row["provenance"], f"graph/schema/relationship_schema.csv#{row['relationship']}:{row['from_label']}->{row['to_label']}")})
    for source, rtype, target, cardinality, required, meaning in CSV_RELATIONSHIPS:
        s, t = snake(source), snake(target)
        assert s in entity_ids and t in entity_ids, (s, t)
        pack["relationships"].append({"id": f"rel_{s}_{rtype.lower()}_{t}", "source_id": s, "type": rtype, "target_id": t, "cardinality": cardinality,
                                      "meaning": meaning, "required": required, "acyclic": False, "constraints": [],
                                      "provenance": {"kind": "synthetic", "reference": "data/canonical/lifecycle and commerce CSV foreign-key columns", "verification": "unverified"}})

    # Identifier mappings: the workbook column that feeds each canonical id, where they differ.
    contract = (ROOT / "graph/schema/identifier_contract.md").read_text(encoding="utf-8")
    for match in re.finditer(r"^\| (\w+) \| (\w+) \| (\w+) \|", contract, re.M):
        label, canonical, column = match.groups()
        if label in LABEL_DOMAIN and canonical != column:
            eid = snake(label)
            pack["mappings"].append({"id": f"map_{eid}_{canonical}", "source_system": "Noordveld dataset workbook", "source_entity": label,
                                     "source_attribute": column, "entity_id": eid, "attribute_id": canonical, "transform": "identifier_lookup",
                                     "provenance": {"kind": "verified_source", "reference": "graph/schema/identifier_contract.md", "verification": "verified"}})

    events = [("evt_order_placed", "Order placed", "order", "", "NEW"), ("evt_order_confirmed", "Order confirmed", "order", "NEW", "CONFIRMED"),
              ("evt_order_allocated", "Order allocated", "order", "PROCESSING", "ALLOCATED"), ("evt_order_shipped", "Order shipped", "order", "ALLOCATED", "SHIPPED"),
              ("evt_order_delivered", "Order delivered", "order", "SHIPPED", "DELIVERED"), ("evt_claim_submitted", "Warranty claim submitted", "warranty_claim", "", "SUBMITTED")]
    for eid, name, entity, src, dst in events:
        pack["events"].append({"id": eid, "name": name, "entity_id": entity, "from_state": src, "to_state": dst,
                               "provenance": {"kind": "user_provided", "reference": "OrderStatus vocabulary (graph/cypher/01_reference_nodes.cypher)", "verification": "unverified"}})

    for rule in design["business"]["rules"]:
        kind, verification = RULE_SOURCE[rule["source"]["kind"]]
        pack["rules"].append({"id": rule["id"], "description": rule["description"], "type": rule["type"], "status": rule["status"],
                              "entity_ids": [], "provenance": {"kind": kind, "reference": rule["source"]["reference"], "verification": verification}})
    workflows = {wf["id"]: wf for wf in design["workflows"]}
    for wf_id, domain in (("wf_spare_parts_order", "dom_commerce"), ("wf_warranty_claim", "dom_service")):
        wf = workflows[wf_id]
        touched = sorted({DESIGN_ENTITY[ref] for state in wf["states"] for ref in state.get("reads_entity_ids", []) + state.get("writes_entity_ids", []) if ref in DESIGN_ENTITY})
        rule_ids = sorted({ref for state in wf["states"] for ref in state.get("rule_ids", [])})
        roles = sorted({state["role_id"] for state in wf["states"] if state.get("role_id")})
        pack["processes"].append({"id": wf_id.replace("wf_", "proc_"), "name": wf["name"], "domain_id": domain, "description": f"Template from Design Studio pack noordveld_spare_parts / {wf_id}.",
                                  "entity_ids": touched, "rule_ids": rule_ids, "event_ids": [e[0] for e in events if (e[2] == "order") == (domain == "dom_commerce")],
                                  "roles": roles, "design_template": f"noordveld_spare_parts/{wf_id}",
                                  "provenance": {"kind": "verified_source", "reference": "app/design_studio/knowledge/packs/noordveld_spare_parts.json", "verification": "verified"}})
    used = {}
    for process in pack["processes"]:
        for rid in process["rule_ids"]:
            used.setdefault(rid, set()).update(process["entity_ids"])
    for rule in pack["rules"]:
        rule["entity_ids"] = sorted(used.get(rule["id"], set()))
    for decision in design["business"]["decisions"]:
        affects = sorted({p["id"] for p in pack["processes"] if any(ref in [s["id"] for s in workflows[p["design_template"].split("/")[1]]["states"]] for ref in decision["affects"])})
        pack["decisions"].append({"id": decision["id"], "question": decision["question"], "status": "open", "answer": "", "affects": affects,
                                  "provenance": {"kind": "user_provided", "reference": "Open business-owner decision recorded in noordveld_spare_parts", "verification": "unverified"}})
    extend_logistics(pack)
    pack["version"] = VERSION
    return DomainPack.model_validate(pack).model_dump(mode="json", exclude_none=False)


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(canonical_bytes(DomainPack.model_validate(data)))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['entities'])} entities, {len(data['relationships'])} relationships, {len(data['concepts'])} concepts")
