"""Canonical graph builder for the Noordveld Parts Intelligence knowledge graph.

Turns the complete workbook into (nodes, edges) with explicit provenance on every node and relationship. Pure Python and
read-only: it never talks to Neo4j. graph_build.py validates the result, writes the audit pack and serialises the Cypher.

Rules the builder follows:
- one workbook row (or a documented deterministic function of one) per node and per relationship; nothing is invented
- the workbook's own data classes are mapped one-to-one (see PROVENANCE) and never re-labelled
- NOT_STATED / NOT_CONFIGURED values are left out (absent property), never turned into 0, false or a guess
- symmetric facts are stored once; rows that would turn "unknown" into "0" are excluded and listed
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Callable

from graph_audit_lib import COMPLETE, blank, token_missing

SOURCE_FILE = COMPLETE.name

# workbook data_class -> provenance category. DEMO is content declared fictional by the project brief (the three plants and
# the order-status vocabulary): it is the brief's own content, so USER_PROVIDED, not SYNTHETIC.
PROVENANCE = {"SOURCE_DERIVED": "SOURCE_DERIVED", "DERIVED": "DERIVED", "SYNTHETIC": "SYNTHETIC_DEMO", "DEMO": "USER_PROVIDED"}
# Which workbook source record (SYN_data_sources, plus the project brief) a provenance category traces to
DATA_SOURCE = {"SOURCE_DERIVED": "SRC-001", "DERIVED": "SRC-002", "SYNTHETIC_DEMO": "SRC-003", "USER_PROVIDED": "SRC-BRIEF"}

Getter = Callable[[dict], "str | None"]


@dataclass
class NodeSpec:
    label: str
    sheet: str
    id_prop: str
    id_col: str
    props: dict[str, str]
    derived_id: Callable[[dict], str] | None = None
    ints: tuple[str, ...] = ()
    floats: tuple[str, ...] = ()
    bools: tuple[str, ...] = ()
    #: the workbook column the canonical id came from, when it is not the canonical id itself
    source_id_col: str | None = None


@dataclass
class EdgeSpec:
    type: str
    sheet: str
    from_label: str
    from_id: Getter
    to_label: str
    to_id: Getter
    id_col: str
    props: dict[str, str] = field(default_factory=dict)
    where: Callable[[dict], bool] = lambda r: True
    symmetric: bool = False
    ints: tuple[str, ...] = ()
    floats: tuple[str, ...] = ()
    const: dict[str, object] = field(default_factory=dict)
    class_override: str | None = None


def col(name: str) -> Getter:
    def f(r: dict) -> str | None:
        v = r.get(name)
        return None if blank(v) or token_missing(v) else str(v).strip()

    return f


def clean(v):
    return None if blank(v) or token_missing(v) else v


def to_int(v):
    v = clean(v)
    return None if v is None else int(float(v))


def to_float(v):
    v = clean(v)
    return None if v is None else float(v)


def to_bool(v):
    v = clean(v)
    return None if v is None else str(v).strip().upper() == "TRUE"


def split_pipe(v):
    v = clean(v)
    return [] if v is None else [x for x in str(v).split("|") if x]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def carrier_id(name: str) -> str:
    return f"CAR-{slug(name)}"


# Nodes ----------------------------------------------------------------------------------------------------------------
NODE_SPECS: list[NodeSpec] = [
    NodeSpec("BusinessUnit", "business_units", "business_unit_id", "business_unit_id", {"name": "business_unit_name", "relationship_to_noordveld": "relationship_to_noordveld", "acquired_year": "acquired_year"}, ints=("acquired_year",)),
    NodeSpec("Plant", "plants", "plant_id", "plant_id", {"name": "plant_name", "city": "city", "country_code": "country_code", "is_fictional_demo": "is_fictional_demo", "manufacturing_role": "manufacturing_role"}, bools=("is_fictional_demo",)),
    NodeSpec("Location", "locations", "location_id", "location_id", {"name": "name", "location_type": "location_type", "country_code": "country_code", "region": "region", "postal_code": "postal_code"}),
    NodeSpec("MachineFamily", "machine_families", "family_id", "family_id", {"name": "family_name", "model_prefix": "model_prefix", "derivation_rule": "derivation_rule", "review_flags": "review_flags"}),
    NodeSpec("MachineType", "machine_types", "machine_type_id", "machine_type_id", {"name": "machine_type_name"}),
    NodeSpec(
        "Machine", "machines", "machine_id", "machine_id",
        {"model_code": "model_code", "name": "machine_name", "machine_type": "machine_type", "origin_plant": "origin_plant", "country": "country", "machine_category": "machine_category", "status": "status", "introduction_year": "introduction_year", "production_status": "production_status", "description": "description", "review_flags": "review_flags"},
        ints=("introduction_year",),
    ),
    NodeSpec("Category", "categories", "category_id", "category_id", {"name": "category_name", "level": "level", "basis": "basis", "description": "description", "review_flags": "review_flags"}, ints=("level",)),
    NodeSpec(
        "Part", "parts", "part_id", "part_id",
        {"part_number": "unified_part_number", "name": "part_name", "category": "part_category", "subcategory": "part_subcategory", "part_type": "part_type", "brand": "brand", "origin_plant": "origin_plant", "oem_status": "oem_status", "part_status": "part_status", "criticality": "criticality", "part_nature": "part_nature", "compatible_models_source": "compatible_models_source", "spec_note_source": "spec_note_source", "review_flags": "review_flags"},
    ),
    NodeSpec(
        "LegacyReference", "legacy_part_mapping", "legacy_reference_id", "mapping_id",
        {"legacy_part_number": "legacy_part_number", "legacy_source_note": "legacy_source_note", "legacy_code_prefix": "legacy_code_prefix", "legacy_business": "legacy_business", "legacy_plant": "legacy_plant", "legacy_system": "legacy_system", "mapping_type": "mapping_type", "mapping_confidence": "mapping_confidence", "business_basis": "business_basis", "review_flags": "review_flags"},
    ),
    NodeSpec("PartSpecification", "part_specifications", "specification_id", "specification_id", {"group": "specification_group", "name": "specification_name", "source_label": "source_label", "value": "value", "unit": "unit", "normalized_value": "normalized_value", "normalized_unit": "normalized_unit", "derived_from": "derived_from", "source_text": "source_text"}),
    NodeSpec("OrderStatus", "order_statuses", "order_status_code", "order_status_code", {"label": "label", "sequence": "sequence"}, ints=("sequence",)),
    # ---- synthetic demonstration layer
    NodeSpec("Warehouse", "SYN_warehouses", "warehouse_id", "warehouse_id", {"name": "warehouse_name", "city": "city", "country_code": "country_code", "pickup_allowed": "pickup_allowed", "ships_to": "ships_to"}, bools=("pickup_allowed",)),
    NodeSpec("Supplier", "SYN_suppliers", "supplier_id", "supplier_id", {"name": "supplier_name", "supplier_type": "supplier_type", "city": "city", "country_code": "country_code", "categories_supplied": "categories_supplied", "payment_terms_days": "payment_terms_days", "quality_rating_demo": "quality_rating_demo", "supplier_status": "supplier_status"}, ints=("payment_terms_days",), floats=("quality_rating_demo",)),
    NodeSpec("Dealer", "SYN_dealers", "dealer_id", "dealer_id", {"name": "dealer_name", "dealer_type": "dealer_type", "city": "city", "country_code": "country_code", "pickup_allowed": "pickup_allowed", "dealer_status": "dealer_status"}, bools=("pickup_allowed",)),
    NodeSpec("Customer", "SYN_customers", "customer_id", "customer_id", {"name": "customer_name", "customer_type": "customer_type", "city": "city", "country_code": "country_code", "customer_status": "customer_status"}),
    NodeSpec("Address", "SYN_addresses", "address_id", "address_id", {"owner_type": "owner_type", "street": "street", "house_number": "house_number", "postal_code": "postal_code", "city": "city", "state_region": "state_region", "country_code": "country_code", "address_note": "address_note"}),
    NodeSpec("Region", "SYN_countries_regions", "region_id", "region_id", {"country_code": "country_code", "country": "country", "name": "region", "currency": "currency", "vat_rate_demo": "vat_rate_demo"}, floats=("vat_rate_demo",)),
    NodeSpec("Price", "SYN_pricing", "price_id", "price_id", {"currency": "currency", "list_price_ex_vat": "list_price_ex_vat", "price_basis": "price_basis", "valid_from": "valid_from", "valid_to": "valid_to", "price_status": "price_status"}, floats=("list_price_ex_vat",)),
    NodeSpec("PartCatalogProfile", "SYN_part_catalog", "profile_id", "part_id", {"part_status": "part_status", "orderable": "orderable", "weight_kg": "weight_kg", "warranty_months": "warranty_months", "return_window_days": "return_window_days", "availability_state": "availability_state", "status_reason": "status_reason", "image_path": "image_path"}, bools=("orderable",), floats=("weight_kg",), ints=("warranty_months", "return_window_days"), derived_id=lambda r: f"PCP-{r['part_id']}", source_id_col="part_id"),
    NodeSpec("ComplianceRequirement", "SYN_compliance", "compliance_id", "compliance_id", {"requirement": "requirement", "standard": "standard", "certification": "certification", "certificate_status": "certificate_status", "valid_until": "valid_until", "categories_covered": "categories_covered"}),
    NodeSpec("Assembly", "SYN_assembly_master", "assembly_id", "assembly_id", {"name": "assembly_name", "bom_status": "bom_status"}),
    NodeSpec("ServicePlan", "SYN_services", "service_plan_id", "service_id", {"service_template": "service_template", "name": "service_name", "interval_hours": "interval_hours", "interval_status": "interval_status"}, ints=("interval_hours",)),
    NodeSpec("MachineSpecification", "SYN_machine_specifications", "machine_spec_id", "machine_spec_id", {"name": "specification_name", "value": "value", "unit": "unit"}),
    NodeSpec("MachineVariant", "SYN_machine_variants", "variant_id", "variant_id", {"variant_name": "variant_name", "serial_from": "serial_from", "serial_to": "serial_to", "variant_status": "variant_status"}),
    NodeSpec("IdentificationRequirement", "SYN_identification_requirements", "requirement_id", "requirement_id", {"identification_needed": "identification_needed", "reason": "reason", "fits_variant_ids": "fits_variant_ids"}),
    NodeSpec("SupplierBackorder", "SYN_supplier_backorders", "backorder_id", "backorder_id", {"quantity_on_order": "quantity_on_order", "expected_restock_days": "expected_restock_days", "backorder_status": "backorder_status"}, ints=("quantity_on_order", "expected_restock_days")),
    NodeSpec("Cart", "SYN_carts", "cart_id", "cart_id", {"cart_status": "cart_status"}),
    NodeSpec("CartLine", "SYN_cart_items", "cart_line_id", "cart_item_id", {"quantity": "quantity", "unit_price_eur": "unit_price_eur"}, ints=("quantity",), floats=("unit_price_eur",)),
    NodeSpec("Order", "SYN_orders", "order_id", "order_id", {"order_status": "order_status", "order_date": "order_date", "currency": "currency", "subtotal_ex_vat": "subtotal_ex_vat", "shipping_ex_vat": "shipping_ex_vat", "shipping_method": "shipping_method", "vat_rate": "vat_rate", "vat_amount": "vat_amount", "order_total_incl_vat": "order_total_incl_vat", "channel": "channel"}, floats=("subtotal_ex_vat", "shipping_ex_vat", "vat_rate", "vat_amount", "order_total_incl_vat")),
    NodeSpec("OrderLine", "SYN_order_items", "order_line_id", "order_item_id", {"line_no": "line_no", "quantity": "quantity", "unit_price_eur": "unit_price_eur", "line_total_eur": "line_total_eur", "allocation_status": "allocation_status"}, ints=("line_no", "quantity"), floats=("unit_price_eur", "line_total_eur")),
    NodeSpec("OrderStatusEvent", "SYN_order_status_history", "status_event_id", "history_id", {"sequence": "sequence", "order_status": "order_status"}, ints=("sequence",)),
    NodeSpec("Shipment", "SYN_shipments", "shipment_id", "shipment_id", {"shipment_status": "shipment_status", "straight_line_km": "straight_line_km", "est_road_km": "est_road_km", "tracking_ref": "tracking_ref"}, floats=("straight_line_km", "est_road_km")),
    NodeSpec("TrackingEvent", "SYN_shipment_events", "tracking_event_id", "event_id", {"event_seq": "event_seq", "event_status": "event_status", "event_location": "event_location", "event_date": "event_date"}, ints=("event_seq",)),
    NodeSpec("DeliveryEstimate", "SYN_delivery_options", "delivery_estimate_id", "lead_id", {"est_road_km": "est_road_km", "standard_price_ex_vat": "standard_price_ex_vat", "standard_days": "standard_days", "express_price_ex_vat": "express_price_ex_vat", "express_days": "express_days", "note": "note"}, floats=("est_road_km", "standard_price_ex_vat", "express_price_ex_vat"), ints=("standard_days", "express_days")),
    NodeSpec("ShippingRate", "SYN_shipping_rates", "rate_id", "rate_id", {"distance_band": "distance_band", "from_km": "from_km", "to_km": "to_km", "method": "method", "price_ex_vat": "price_ex_vat", "transit_days": "transit_days"}, ints=("from_km", "to_km", "transit_days"), floats=("price_ex_vat",)),
    NodeSpec("SearchAlias", "SYN_search_aliases", "alias_id", "alias_id", {"alias": "alias", "alias_type": "alias_type", "entity_type": "entity_type"}),
]


def _decorated(S: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Adds lookup columns the workbook names differently (machine type id, sub-category id, inventory pairing)."""
    type_id = {r["machine_type_name"]: r["machine_type_id"] for r in S["machine_types"]}
    sub_id = {(r["parent_category_id"], r["category_name"]): r["category_id"] for r in S["categories"] if str(r["level"]) == "2"}
    out = dict(S)
    out["machines"] = [{**r, "machine_type_id": type_id.get(r["machine_type"])} for r in S["machines"]]
    out["parts"] = [{**r, "subcategory_id": r.get("subcategory_id") or sub_id.get((r["category_id"], r["part_subcategory"]))} for r in S["parts"]]
    return out


c = col
EDGE_SPECS: list[EdgeSpec] = [
    # ---- catalogue layer (source-derived and rule-derived)
    EdgeSpec("FITS", "machine_part_fitment", "Part", c("part_id"), "Machine", c("machine_id"), "fitment_id", {"fitment_type": "fitment_type", "fitment_evidence": "fitment_evidence", "condition_note": "notes", "review_flags": "review_flags", "source_confidence": "confidence"}),
    EdgeSpec("MANUFACTURED_AT", "machines", "Machine", c("machine_id"), "Plant", c("plant_id"), "machine_id"),
    EdgeSpec("OF_TYPE", "machines", "Machine", c("machine_id"), "MachineType", c("machine_type_id"), "machine_id"),
    EdgeSpec("MEMBER_OF_FAMILY", "machines", "Machine", c("machine_id"), "MachineFamily", c("family_id"), "machine_id", class_override="DERIVED"),
    EdgeSpec("BRANDED_AS", "machines", "Machine", c("machine_id"), "BusinessUnit", c("business_unit_id"), "machine_id"),
    EdgeSpec("PRODUCT_FAMILY_OF", "machine_families", "MachineFamily", c("family_id"), "BusinessUnit", c("business_unit_id"), "family_id"),
    EdgeSpec("OWNED_BY", "plants", "Plant", c("plant_id"), "BusinessUnit", c("business_unit_id"), "plant_id"),
    EdgeSpec("LOCATED_IN", "plants", "Plant", c("plant_id"), "Location", c("location_id"), "plant_id"),
    EdgeSpec("IN_COUNTRY", "locations", "Location", c("location_id"), "Location", c("parent_location_id"), "location_id", where=lambda r: not blank(r.get("parent_location_id"))),
    EdgeSpec("SUBCATEGORY_OF", "categories", "Category", c("category_id"), "Category", c("parent_category_id"), "category_id", where=lambda r: str(r["level"]) == "2"),
    EdgeSpec("IN_CATEGORY", "parts", "Part", c("part_id"), "Category", c("category_id"), "part_id"),
    EdgeSpec("IN_SUBCATEGORY", "parts", "Part", c("part_id"), "Category", c("subcategory_id"), "part_id", class_override="DERIVED"),
    EdgeSpec("ORIGINATES_AT", "parts", "Part", c("part_id"), "Plant", c("plant_id"), "part_id"),
    EdgeSpec("HAS_LEGACY_REFERENCE", "legacy_part_mapping", "Part", c("current_part_id"), "LegacyReference", c("mapping_id"), "mapping_id"),
    EdgeSpec("ISSUED_BY_BUSINESS_UNIT", "legacy_part_mapping", "LegacyReference", c("mapping_id"), "BusinessUnit", c("legacy_business_unit_id"), "mapping_id", class_override="DERIVED"),
    EdgeSpec("HAS_SPECIFICATION", "part_specifications", "Part", c("part_id"), "PartSpecification", c("specification_id"), "specification_id"),
    EdgeSpec("SAME_NAME_GROUP_AS", "part_relationships", "Part", c("from_part_id"), "Part", c("to_part_id"), "part_relationship_id", {"evidence": "evidence", "source_interchangeability": "interchangeability"}, where=lambda r: r["relationship_type"] == "SAME_SUBCATEGORY", symmetric=True, const={"interchangeability_status": "UNKNOWN"}),
    EdgeSpec("RELATED_COMPONENT", "part_relationships", "Part", c("from_part_id"), "Part", c("to_part_id"), "part_relationship_id", {"evidence": "evidence", "source_interchangeability": "interchangeability"}, where=lambda r: r["relationship_type"] == "RELATED_COMPONENT", const={"interchangeability_status": "UNKNOWN"}),
    # ---- synthetic demonstration layer
    EdgeSpec("CO_ORDERED_WITH", "SYN_part_relationships", "Part", c("from_part_id"), "Part", c("to_part_id"), "syn_relationship_id", {"evidence": "evidence", "source_relationship_type": "relationship_type", "source_interchangeability": "interchangeability"}, symmetric=True, const={"interchangeability_status": "UNKNOWN"}),
    EdgeSpec("SUPPLIED_BY", "SYN_part_supplier", "Part", c("part_id"), "Supplier", c("supplier_id"), "part_supplier_id", {"is_primary": "is_primary", "supplier_part_number": "supplier_part_number", "unit_cost_eur": "unit_cost_eur", "lead_time_days": "lead_time_days", "min_order_qty": "min_order_qty", "relationship_status": "relationship_status"}, floats=("unit_cost_eur",), ints=("lead_time_days", "min_order_qty")),
    EdgeSpec("PLACED_WITH", "SYN_supplier_backorders", "SupplierBackorder", c("backorder_id"), "Supplier", c("supplier_id"), "backorder_id"),
    EdgeSpec("FOR_PART", "SYN_supplier_backorders", "SupplierBackorder", c("backorder_id"), "Part", c("part_id"), "backorder_id"),
    EdgeSpec("LOCATED_AT_PLANT", "SYN_warehouses", "Warehouse", c("warehouse_id"), "Plant", c("plant_id"), "warehouse_id"),
    EdgeSpec("LOCATED_AT_ADDRESS", "SYN_warehouses", "Warehouse", c("warehouse_id"), "Address", c("address_id"), "warehouse_id"),
    EdgeSpec("LOCATED_AT_ADDRESS", "SYN_suppliers", "Supplier", c("supplier_id"), "Address", c("address_id"), "supplier_id"),
    EdgeSpec("LOCATED_AT_ADDRESS", "SYN_dealers", "Dealer", c("dealer_id"), "Address", c("address_id"), "dealer_id"),
    EdgeSpec("LOCATED_AT_ADDRESS", "SYN_customers", "Customer", c("customer_id"), "Address", c("address_id"), "customer_id"),
    EdgeSpec("LOCATED_AT_ADDRESS", "SYN_addresses", "Plant", c("owner_id"), "Address", c("address_id"), "address_id", where=lambda r: r["owner_type"] == "PLANT"),
    EdgeSpec("IN_REGION", "SYN_addresses", "Address", c("address_id"), "Region", c("region_id"), "address_id"),
    # Inventory: warehouse stock is AVAILABLE_AT; dealer stock is STOCKED_BY (listing from SYN_part_dealer + quantities from SYN_inventory)
    EdgeSpec("AVAILABLE_AT", "SYN_inventory", "Part", c("part_id"), "Warehouse", c("location_id"), "inventory_id", {"on_hand": "on_hand", "reserved": "reserved", "available": "available", "reorder_point": "reorder_point", "stock_status": "stock_status"}, where=lambda r: r["location_type"] == "WAREHOUSE", ints=("on_hand", "reserved", "available", "reorder_point")),
    EdgeSpec("STOCKED_BY", "SYN_part_dealer", "Part", c("part_id"), "Dealer", c("dealer_id"), "part_dealer_id", {"stocking_status": "stocking_status", "inventory_id": "inventory_id", "on_hand": "on_hand", "reserved": "reserved", "available": "available", "reorder_point": "reorder_point", "stock_status": "stock_status"}, ints=("on_hand", "reserved", "available", "reorder_point")),
    EdgeSpec("SERVES_FAMILY", "SYN_dealers", "Dealer", c("dealer_id"), "MachineFamily", c("family_id"), "dealer_family_id"),
    EdgeSpec("PRICES_PART", "SYN_pricing", "Price", c("price_id"), "Part", c("part_id"), "price_id"),
    EdgeSpec("PROFILES_PART", "SYN_part_catalog", "PartCatalogProfile", lambda r: f"PCP-{r['part_id']}", "Part", c("part_id"), "part_id"),
    EdgeSpec("HAS_COMPLIANCE", "SYN_part_compliance", "Part", c("part_id"), "ComplianceRequirement", c("compliance_id"), "part_compliance_id"),
    EdgeSpec("IDENTIFIED_BY_PART", "SYN_assembly_master", "Assembly", c("assembly_id"), "Part", c("assembly_part_id"), "assembly_id"),
    EdgeSpec("PART_OF", "SYN_assembly_components", "Part", c("component_part_id"), "Assembly", c("assembly_id"), "component_id", {"quantity": "quantity", "basis": "basis"}, ints=("quantity",)),
    EdgeSpec("FOR_MACHINE", "SYN_services", "ServicePlan", c("service_id"), "Machine", c("machine_id"), "service_id"),
    EdgeSpec("REQUIRES_PART", "SYN_service_parts", "ServicePlan", c("service_id"), "Part", c("part_id"), "service_part_id", {"quantity": "quantity", "basis": "basis"}, ints=("quantity",)),
    EdgeSpec("HAS_MACHINE_SPECIFICATION", "SYN_machine_specifications", "Machine", c("machine_id"), "MachineSpecification", c("machine_spec_id"), "machine_spec_id"),
    EdgeSpec("VARIANT_OF", "SYN_machine_variants", "MachineVariant", c("variant_id"), "Machine", c("machine_id"), "variant_id"),
    EdgeSpec("FOR_PART", "SYN_identification_requirements", "IdentificationRequirement", c("requirement_id"), "Part", c("part_id"), "requirement_id"),
    EdgeSpec("FOR_MACHINE", "SYN_identification_requirements", "IdentificationRequirement", c("requirement_id"), "Machine", c("machine_id"), "requirement_id"),
    EdgeSpec("ADMITS_VARIANT", "SYN_identification_requirements", "IdentificationRequirement", c("requirement_id"), "MachineVariant", c("variant_id"), "requirement_variant_id"),
    EdgeSpec("OPENED_BY", "SYN_carts", "Cart", c("cart_id"), "Customer", c("customer_id"), "cart_id"),
    EdgeSpec("CONTAINS_LINE", "SYN_cart_items", "Cart", c("cart_id"), "CartLine", c("cart_item_id"), "cart_item_id"),
    EdgeSpec("REFERENCES_PART", "SYN_cart_items", "CartLine", c("cart_item_id"), "Part", c("part_id"), "cart_item_id"),
    EdgeSpec("ORDERED_BY", "SYN_orders", "Order", c("order_id"), "Customer", c("customer_id"), "order_id"),
    EdgeSpec("DELIVERS_TO_ADDRESS", "SYN_orders", "Order", c("order_id"), "Address", c("delivery_address_id"), "order_id"),
    EdgeSpec("CONTAINS_LINE", "SYN_order_items", "Order", c("order_id"), "OrderLine", c("order_item_id"), "order_item_id"),
    EdgeSpec("REFERENCES_PART", "SYN_order_items", "OrderLine", c("order_item_id"), "Part", c("part_id"), "order_item_id"),
    # A line whose stock is reserved or already shipped is ALLOCATED_FROM; a line not yet allocated only has a planned source
    EdgeSpec("ALLOCATED_FROM", "SYN_order_items", "OrderLine", c("order_item_id"), "Warehouse", c("fulfilment_location_id"), "order_item_id", {"allocation_status": "allocation_status"}, where=lambda r: r["allocation_status"] in ("RESERVED", "SHIPPED")),
    EdgeSpec("PLANNED_FULFILMENT_FROM", "SYN_order_items", "OrderLine", c("order_item_id"), "Warehouse", c("fulfilment_location_id"), "order_item_id", {"allocation_status": "allocation_status"}, where=lambda r: r["allocation_status"] not in ("RESERVED", "SHIPPED")),
    EdgeSpec("HAS_STATUS_EVENT", "SYN_order_status_history", "Order", c("order_id"), "OrderStatusEvent", c("history_id"), "history_id"),
    EdgeSpec("RECORDS_STATUS", "SYN_order_status_history", "OrderStatusEvent", c("history_id"), "OrderStatus", c("order_status"), "history_id"),
    EdgeSpec("HAS_SHIPMENT", "SYN_shipments", "Order", c("order_id"), "Shipment", c("shipment_id"), "shipment_id"),
    EdgeSpec("SHIPS_LINE", "SYN_shipments", "Shipment", c("shipment_id"), "OrderLine", c("order_item_id"), "shipment_id"),
    EdgeSpec("DISPATCHED_FROM", "SYN_shipments", "Shipment", c("shipment_id"), "Warehouse", c("from_location_id"), "shipment_id"),
    EdgeSpec("DELIVERS_TO_CUSTOMER", "SYN_shipments", "Shipment", c("shipment_id"), "Customer", c("to_customer_id"), "shipment_id"),
    EdgeSpec("CARRIED_BY", "SYN_shipments", "Shipment", c("shipment_id"), "Carrier", lambda r: carrier_id(str(r["carrier"])), "shipment_id"),
    EdgeSpec("HAS_TRACKING_EVENT", "SYN_shipment_events", "Shipment", c("shipment_id"), "TrackingEvent", c("event_id"), "event_id"),
    EdgeSpec("FROM_WAREHOUSE", "SYN_delivery_options", "DeliveryEstimate", c("lead_id"), "Warehouse", c("from_warehouse_id"), "lead_id"),
    EdgeSpec("TO_CUSTOMER", "SYN_delivery_options", "DeliveryEstimate", c("lead_id"), "Customer", c("to_id"), "lead_id", where=lambda r: r["to_type"] == "CUSTOMER"),
    EdgeSpec("TO_DEALER", "SYN_delivery_options", "DeliveryEstimate", c("lead_id"), "Dealer", c("to_id"), "lead_id", where=lambda r: r["to_type"] == "DEALER"),
    EdgeSpec("HAS_ALIAS", "SYN_search_aliases", "*", c("entity_id"), "SearchAlias", c("alias_id"), "alias_id"),
    # Added by the coverage audit: stated in the workbook, previously only kept as text properties
    EdgeSpec("HOME_PLANT", "business_units", "BusinessUnit", c("business_unit_id"), "Plant", c("home_plant_id"), "business_unit_id"),
    EdgeSpec("SUPPLIES_CATEGORY", "SYN_suppliers", "Supplier", c("supplier_id"), "Category", c("category_id"), "supplier_category_id"),
    EdgeSpec("COVERS_CATEGORY", "SYN_compliance", "ComplianceRequirement", c("compliance_id"), "Category", c("category_id"), "compliance_category_id"),
    EdgeSpec("SHIPS_TO_COUNTRY", "SYN_warehouses", "Warehouse", c("warehouse_id"), "Location", c("country_location_id"), "warehouse_country_id"),
]

ALIAS_TARGETS = {"PART": "Part", "MACHINE": "Machine", "CATEGORY": "Category", "SUPPLIER": "Supplier", "DEALER": "Dealer", "CUSTOMER": "Customer"}
#: Columns that are provenance metadata, not facts (excluded from the "missing token" leak check)
PROV_KEYS = ("provenance_type", "data_status", "source_id", "source_file", "source_sheet", "source_record_id", "source_name", "source_ref", "confidence", "authoritative_flag", "last_updated")


def prov(row: dict, sheet: str, rec_id: str | None, class_override: str | None = None) -> dict:
    cls = class_override or row.get("data_class") or "UNKNOWN"
    ptype = PROVENANCE.get(cls, "UNKNOWN")
    src = str(row.get("source") or "")
    return {
        "provenance_type": ptype,
        "data_status": ptype,
        "source_id": DATA_SOURCE.get(ptype),
        "source_file": SOURCE_FILE,
        "source_sheet": sheet,
        "source_record_id": rec_id,
        "source_name": "gen_synthetic.py (seed 42)" if src.startswith("gen_synthetic") else (clean(src) or None),
        "source_ref": clean(row.get("source_ref")),
        # the workbook's own confidence marker, kept verbatim (NOT_STATED means the workbook states none)
        "confidence": clean(row.get("confidence")) or "NOT_STATED",
        # nothing in the workbook is externally verified, including the catalogue layer
        "authoritative_flag": False,
        "last_updated": clean(row.get("last_updated")),
    }


@dataclass
class Graph:
    nodes: dict[str, dict[str, dict]] = field(default_factory=lambda: collections.defaultdict(dict))
    edges: list[dict] = field(default_factory=list)
    #: (label, property) -> [populated, not stated]
    prop_stats: dict[tuple[str, str], list[int]] = field(default_factory=lambda: collections.defaultdict(lambda: [0, 0]))
    #: source rows deliberately kept out of the graph, with the reason
    excluded: list[dict] = field(default_factory=list)
    #: relationships the data model expects but the source does not state (an endpoint is NOT_STATED / absent)
    missing_links: list[dict] = field(default_factory=list)
    node_issues: list[dict] = field(default_factory=list)


def build(S: dict[str, list[dict]]) -> Graph:
    g = Graph()
    S = _decorated(S)

    # Rows that would become "0 in stock" for a dealer that is not recorded as stocking the part. Missing is not zero.
    listed = {(r["dealer_id"], r["part_id"]) for r in S["SYN_part_dealer"]}
    inv_by_pair = {(r["location_id"], r["part_id"]): r for r in S["SYN_inventory"] if r["location_type"] == "DEALER"}
    for (dealer, part), r in inv_by_pair.items():
        if (dealer, part) not in listed:
            g.excluded.append({"record_id": r["inventory_id"], "source_sheet": "SYN_inventory", "would_have_been": f"(:Part {{part_id:'{part}'}})-[:STOCKED_BY {{available: {r['available']}}}]->(:Dealer {{dealer_id:'{dealer}'}})", "reason": "EXPLICIT_ZERO_WITHOUT_STOCKING_RECORD", "explanation": "SYN_inventory has a 0-stock row for a dealer that SYN_part_dealer does not list as stocking the part. The fact is UNKNOWN, not ZERO, so it is not imported.", "data_status": "SYNTHETIC_DEMO"})
    # Dealer stocking rows carry the matching inventory quantities (one-to-one by dealer and part)
    S["SYN_part_dealer"] = [{**r, **{k: v for k, v in inv_by_pair.get((r["dealer_id"], r["part_id"]), {}).items() if k in ("inventory_id", "on_hand", "reserved", "available", "reorder_point", "stock_status")}} for r in S["SYN_part_dealer"]]
    S["SYN_addresses"] = [{**r, "region_id": next((x["region_id"] for x in S["SYN_countries_regions"] if x["country_code"] == r["country_code"] and x["region"] == r["state_region"]), None)} for r in S["SYN_addresses"]]
    S["SYN_dealers"] = S["SYN_dealers"]
    dealer_families = [{**r, "family_id": fam, "dealer_family_id": f"{r['dealer_id']}>{fam}"} for r in S["SYN_dealers"] for fam in split_pipe(r.get("families_served"))]
    supplier_cats = [{**r, "category_id": cat, "supplier_category_id": f"{r['supplier_id']}>{cat}"} for r in S["SYN_suppliers"] for cat in split_pipe(r.get("categories_supplied"))]
    compliance_cats = [{**r, "category_id": cat, "compliance_category_id": f"{r['compliance_id']}>{cat}"} for r in S["SYN_compliance"] for cat in split_pipe(r.get("categories_covered"))]
    country_loc = {r["country_code"]: r["location_id"] for r in S["locations"] if r["location_type"] == "COUNTRY"}
    ship_rows = []
    for r in S["SYN_warehouses"]:
        for code in split_pipe(r.get("ships_to")):
            if code in country_loc:
                ship_rows.append({**r, "country_location_id": country_loc[code], "warehouse_country_id": f"{r['warehouse_id']}>{code}"})
            else:
                g.missing_links.append({"relationship": "SHIPS_TO_COUNTRY", "from_label": "Warehouse", "from_id": r["warehouse_id"], "to_label": "Location", "to_id": None, "source_sheet": "SYN_warehouses", "record_id": f"{r['warehouse_id']}>{code}", "reason": f"COUNTRY_{code}_HAS_NO_LOCATION_NODE (the catalogue lists only the NL and DE countries)"})
    variant_links = [{**r, "variant_id": v, "requirement_variant_id": f"{r['requirement_id']}>{v}"} for r in S["SYN_identification_requirements"] for v in split_pipe(r.get("fits_variant_ids"))]

    for spec in NODE_SPECS:
        for r in S[spec.sheet]:
            nid = spec.derived_id(r) if spec.derived_id else col(spec.id_col)(r)
            if nid is None:
                g.node_issues.append({"label": spec.label, "sheet": spec.sheet, "issue": "NULL_ID", "record": str(r)[:80]})
                continue
            if nid in g.nodes[spec.label]:
                g.node_issues.append({"label": spec.label, "sheet": spec.sheet, "issue": "DUPLICATE_ID", "record": nid})
                continue
            props: dict = {spec.id_prop: nid}
            if spec.id_prop != spec.id_col or spec.source_id_col:
                props["source_id_value"] = str(r[spec.source_id_col or spec.id_col])
            for gp, sc in spec.props.items():
                v = r.get(sc)
                if gp in spec.ints:
                    v = to_int(v)
                elif gp in spec.floats:
                    v = to_float(v)
                elif gp in spec.bools:
                    v = to_bool(v)
                else:
                    v = clean(v)
                    v = None if v is None else (v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
                stat = g.prop_stats[(spec.label, gp)]
                if v is None:
                    stat[1] += 1
                else:
                    stat[0] += 1
                    props[gp] = v
            props.update(prov(r, spec.sheet, str(r[spec.id_col])))
            g.nodes[spec.label][nid] = props

    # Carrier: the workbook has no carrier id, so the key is derived deterministically from the carrier name
    for r in S["SYN_shipments"]:
        cid = carrier_id(str(r["carrier"]))
        if cid not in g.nodes["Carrier"]:
            g.nodes["Carrier"][cid] = {"carrier_id": cid, "name": str(r["carrier"]), "key_basis": "DERIVED_FROM_NAME", **prov(r, "SYN_shipments", cid)}

    # Data sources: the workbook's own source register, plus the project brief it cites for DEMO-class content
    for r in S["SYN_data_sources"]:
        g.nodes["DataSource"][r["source_id"]] = {"source_id": r["source_id"], "name": r["source_name"], "layer": r["layer"], "verification": r["verification"], "limitations": r["limitations"], **{k: v for k, v in prov(r, "SYN_data_sources", r["source_id"]).items() if k != "source_id"}}
    g.nodes["DataSource"]["SRC-BRIEF"] = {"source_id": "SRC-BRIEF", "name": "Project brief and OEM Agentic Commerce wireframe (cited by the workbook)", "layer": "DEMO-class rows (plants, order-status vocabulary)", "verification": "As cited in the workbook's source / source_ref columns", "limitations": "Declares the plants and workflow vocabulary fictional/demonstration", "provenance_type": "USER_PROVIDED", "data_status": "USER_PROVIDED", "source_file": SOURCE_FILE, "source_sheet": "01_Legend", "source_record_id": "DEMO", "source_name": "01_Legend data_class DEMO", "source_ref": None, "confidence": "NOT_STATED", "authoritative_flag": False, "last_updated": None}

    extra_rows = {"SYN_dealers": dealer_families, "SYN_identification_requirements:variants": variant_links}
    for spec in EDGE_SPECS:
        rows = {"ADMITS_VARIANT": variant_links, "SERVES_FAMILY": dealer_families, "SUPPLIES_CATEGORY": supplier_cats, "COVERS_CATEGORY": compliance_cats, "SHIPS_TO_COUNTRY": ship_rows}.get(spec.type, S[spec.sheet])
        for r in rows:
            if not spec.where(r):
                continue
            rec_id = str(r[spec.id_col])
            from_label = ALIAS_TARGETS.get(str(r.get("entity_type"))) if spec.from_label == "*" else spec.from_label
            f, t = spec.from_id(r), spec.to_id(r)
            if from_label is None or f is None or t is None:
                g.missing_links.append({"relationship": spec.type, "from_label": spec.from_label, "from_id": f, "to_label": spec.to_label, "to_id": t, "source_sheet": spec.sheet, "record_id": rec_id, "reason": "ENDPOINT_NOT_STATED_IN_SOURCE"})
                continue
            props = {}
            for gp, sc in spec.props.items():
                v = r.get(sc)
                v = to_int(v) if gp in spec.ints else to_float(v) if gp in spec.floats else to_bool(v) if gp == "is_primary" else clean(v)
                if v is not None:
                    props[gp] = v
            props.update(spec.const)
            g.edges.append({"type": spec.type, "from_label": from_label, "from_id": f, "to_label": spec.to_label, "to_id": t, "rel_id": f"{spec.type}:{rec_id}", "symmetric": spec.symmetric, "props": props, **prov(r, spec.sheet, rec_id, spec.class_override)})
    del extra_rows

    # FITS carries an explicit status; SOURCE_STATED_CONDITIONAL is never promoted to CONFIRMED
    for e in g.edges:
        if e["type"] == "FITS":
            e["props"]["fitment_status"] = "CONDITIONAL" if e["props"].get("source_confidence") == "SOURCE_STATED_CONDITIONAL" else "CONFIRMED"

    # Symmetric facts (A co-ordered with B is B co-ordered with A) are stored once: lower id -> higher id
    kept: dict[tuple, dict] = {}
    out = []
    for e in g.edges:
        if not e["symmetric"]:
            out.append(e)
            continue
        a, b = sorted((e["from_id"], e["to_id"]))
        key = (e["type"], a, b)
        if key in kept:
            first = kept[key]
            first["props"]["merged_source_record_ids"] = sorted({first["source_record_id"], e["source_record_id"], *first["props"].get("merged_source_record_ids", [])})
            g.excluded.append({"record_id": e["source_record_id"], "source_sheet": e["source_sheet"], "would_have_been": f"(:Part {{part_id:'{e['from_id']}'}})-[:{e['type']}]->(:Part {{part_id:'{e['to_id']}'}})", "reason": "DUPLICATE_SYMMETRIC_FACT", "explanation": f"The same symmetric fact is already stored as {first['rel_id']} ({a} - {b}). Its record id is kept on that relationship (merged_source_record_ids).", "data_status": e["data_status"]})
            continue
        e["from_id"], e["to_id"] = a, b
        kept[key] = e
        out.append(e)
    g.edges = out
    return g
