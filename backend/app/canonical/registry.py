"""Dataset registry: every canonical dataset, its file, its model and exactly how it maps onto the EXISTING graph labels and relationship types.

Reading guide
  NodeTarget  a record becomes (or is checked against) one node. `fields` maps canonical field -> graph property. `mode`:
                merge   canonical data owns the node's mapped properties (synthetic and new domains);
                verify  the graph owns it: the record is only compared (supplied catalogue, live orders and inventory).
              Whatever the mode, the engine never writes a node that is protected (SOURCE_DERIVED / DERIVED / REAL / non-app USER_PROVIDED) or written by
              the running app (source_id APP-SESSION).
  RelTarget   the record IS a relationship, identified by (type, from id, to id).
  RelDef      an extra relationship from a node record to another entity.
  refs        a field that must point at an existing entity (validated, never written).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.canonical import models as m
from app.logistics.rules import tracking_group_check

# entity kind -> candidate (graph label, key property). A kind with several candidates is resolved per id.
KINDS: dict[str, tuple[tuple[str, str], ...]] = {
    "machine": (("Machine", "machine_id"),),
    "variant": (("MachineVariant", "variant_id"),),
    "part": (("Part", "part_id"),),
    "category": (("Category", "category_id"),),
    "supplier": (("Supplier", "supplier_id"),),
    "dealer": (("Dealer", "dealer_id"),),
    "business_unit": (("BusinessUnit", "business_unit_id"),),
    "customer": (("Customer", "customer_id"),),
    "plant": (("Plant", "plant_id"),),
    "location": (("Warehouse", "warehouse_id"), ("ShipTo", "shipto_id"), ("Plant", "plant_id"), ("Location", "location_id"), ("TransportTerminal", "terminal_id"),
                 ("Dealer", "dealer_id"), ("Supplier", "supplier_id")),
    "carrier": (("Carrier", "carrier_id"),),
    "assembly": (("Assembly", "assembly_id"),),
    "legacy": (("LegacyReference", "legacy_reference_id"),),
    "order": (("Order", "order_id"),),
    "order_line": (("OrderLine", "order_line_id"),),
    "shipment": (("Shipment", "shipment_id"),),
    "route": (("TransportRoute", "route_id"),),
    "leg": (("TransportLeg", "leg_id"),),
    "fitment": (("FitmentContext", "fitment_id"),),
    "price": (("Price", "price_id"),),
    "machine_instance": (("MachineInstance", "machine_instance_id"),),
    "technician": (("Technician", "technician_id"),),
    "work_order": (("WorkOrder", "work_order_id"),),
    "installation": (("InstallationEvent", "installation_id"),),
    "replacement": (("ReplacementEvent", "replacement_id"),),
    "warranty_policy": (("WarrantyPolicy", "warranty_policy_id"),),
    "claim": (("WarrantyClaim", "claim_id"),),
    "evidence": (("Evidence", "evidence_id"),),
    "scenario": (("FeaturedScenario", "scenario_id"),),
    "tracking_event": (("TrackingEvent", "tracking_event_id"),),
}
LOCATION_KEYS = {"Warehouse": "warehouse_id", "ShipTo": "shipto_id", "Plant": "plant_id", "Location": "location_id", "TransportTerminal": "terminal_id", "Dealer": "dealer_id",
                 "Supplier": "supplier_id"}
TERMINAL_LABELS = {"SEAPORT": "SeaPort", "AIRPORTCARGOTERMINAL": "AirportCargoTerminal", "CROSSDOCK": "CrossDock", "INLANDPORT": "InlandPort", "RAILTERMINAL": "RailTerminal"}
SOURCE_KIND_TO_KIND = {"SUPPLIER": "supplier", "DEALER": "dealer", "OEM": "business_unit"}
ENTITY_TYPE_TO_KIND = {"WORK_ORDER": "work_order", "INSTALLATION": "installation", "MACHINE_INSTANCE": "machine_instance", "SHIPMENT": "shipment", "ORDER": "order",
                       "WARRANTY_CLAIM": "claim", "REPLACEMENT": "replacement", "DEALER": "dealer", "TECHNICIAN": "technician", "PART": "part"}

# labels this phase introduces (their id property gets a uniqueness constraint)
NEW_LABELS = {"FitmentContext": "fitment_id", "MachineInstance": "machine_instance_id", "Technician": "technician_id", "WorkOrder": "work_order_id",
              "InstallationEvent": "installation_id", "ReplacementEvent": "replacement_id", "WarrantyPolicy": "warranty_policy_id", "WarrantyClaim": "claim_id",
              "Evidence": "evidence_id", "FeaturedScenario": "scenario_id"}


@dataclass(frozen=True)
class RelDef:
    type: str
    field: str
    kind: str | None  # target kind; None when `kind_from` decides
    reverse: bool = False  # True: (target)-[type]->(this)
    kind_from: tuple[str, dict[str, str]] | None = None  # (field, value -> kind)
    props: tuple[str, ...] = ()  # canonical fields copied onto the relationship


@dataclass(frozen=True)
class NodeTarget:
    label: str | None
    key: str
    fields: dict[str, str]
    label_field: str | None = None  # take the graph label from this canonical field (the key then comes from LOCATION_KEYS)
    id_fn: Callable | None = None
    mode: str = "merge"
    create: bool = True
    rels: tuple[RelDef, ...] = ()
    casefold: tuple[str, ...] = ()  # fields whose canonical form is a normalisation of the graph value (a case-only difference is not drift)
    extra_label_field: str | None = None  # a canonical field whose value, mapped through extra_label_map, is a second label for the node
    extra_label_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RelTarget:
    type: str
    from_field: str
    from_kind: str
    to_field: str
    to_kind: str | None
    rel_id: str  # template, {id} = the record id
    fields: dict[str, str] = field(default_factory=dict)  # canonical field -> relationship property
    mode: str = "merge"
    to_kind_from: tuple[str, dict[str, str]] | None = None


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    path: str
    model: type[m.Canon]
    kind: str | None = None
    targets: tuple[NodeTarget, ...] = ()
    rel: RelTarget | None = None
    refs: tuple[tuple[str, str], ...] = ()
    depends: tuple[str, ...] = ()
    domain: str = ""
    group_check: Callable | None = None  # records of the whole dataset -> {record id: reason} for records that are impossible together (e.g. a tracking sequence)

    @property
    def fmt(self) -> str:
        return self.path.rsplit(".", 1)[1]

    @property
    def new_labels(self) -> list[str]:
        return [t.label for t in self.targets if t.label in NEW_LABELS]


def _t(label, key, fields, **kw):
    return NodeTarget(label=label, key=key, fields=fields, **kw)


LOCATION_FIELDS = {"name": "name", "country_code": "country_code", "city": "city", "latitude": "latitude", "longitude": "longitude", "geo_basis": "geo_basis",
                   "location_type": "logistics_type", "country": "country", "region": "region", "timezone": "timezone", "terminal_type": "terminal_type", "modes": "modes"}
LOCATION_TARGET = NodeTarget(label=None, label_field="graph_label", key="", fields=LOCATION_FIELDS, extra_label_field="terminal_type", extra_label_map=TERMINAL_LABELS)
DEALER_FIELDS = {"dealer_id": "dealer_id", "name": "name", "city": "city", "country_code": "country_code", "dealer_type": "dealer_type", "status": "dealer_status",
                 "latitude": "latitude", "longitude": "longitude", "location_id": "location_id", "country": "country", "region": "region", "authorized_status": "authorized_status",
                 "service_capable": "service_capable", "warranty_capable": "warranty_capable"}
SHIPMENT_FIELDS = {"shipment_id": "shipment_id", "status": "shipment_status", "tracking_ref": "tracking_ref", "route_id": "route_id", "departure_date": "departure_date",
                   "planned_eta": "planned_eta", "actual_eta": "actual_eta", "remediation_flags": "remediation_flags", "route_resolution_status": "route_resolution_status",
                   "transport_mode": "transport_mode"}
SHIPMENT_RELS = (RelDef("USES_ROUTE", "route_id", "route"), RelDef("DISPATCHED_FROM", "origin_location_id", "location"), RelDef("DELIVERS_TO_LOCATION", "destination_location_id", "location"),
                 RelDef("HAS_SHIPMENT", "order_id", "order", reverse=True), RelDef("SHIPS_LINE", "order_line_id", "order_line"), RelDef("CARRIED_BY", "carrier_id", "carrier"))
TRACKING_FIELDS = {"tracking_event_id": "tracking_event_id", "timestamp": "event_date", "status": "event_status", "event_type": "event_type", "location_text": "event_location",
                   "sequence": "event_seq", "description": "description"}
TRACKING_RELS = (RelDef("HAS_TRACKING_EVENT", "shipment_id", "shipment", reverse=True), RelDef("AT_LOCATION", "location_id", "location"))
ROUTE_FIELDS = {"route_id": "route_id", "transport_mode": "transport_mode", "planned_transit_days": "total_estimated_days", "service_level": "service_level", "status": "route_status",
                "origin_location_id": "origin_location_id", "destination_location_id": "destination_location_id", "estimated_cost": "estimated_cost", "currency": "currency"}

SPECS: tuple[DatasetSpec, ...] = (
    # ── master ───────────────────────────────────────────────────────────────────────────────────
    DatasetSpec("plants", "master/plants.json", m.Plant, "plant", domain="master",
                targets=(_t("Plant", "plant_id", {"plant_id": "plant_id", "name": "name", "city": "city", "country_code": "country_code"}, mode="verify"),)),
    DatasetSpec("locations", "master/locations.json", m.Location, "location", domain="master", depends=("plants",),
                targets=(LOCATION_TARGET,)),
    DatasetSpec("categories", "master/categories.json", m.Category, "category", domain="master",
                targets=(_t("Category", "category_id", {"category_id": "category_id", "name": "name"}, mode="verify"),)),
    DatasetSpec("machines", "master/machines.json", m.Machine, "machine", domain="master", depends=("plants",),
                targets=(_t("Machine", "machine_id", {"machine_id": "machine_id", "model": "model_code", "machine_type": "machine_type", "name": "name"}, mode="verify"),)),
    DatasetSpec("suppliers", "master/suppliers.json", m.Supplier, "supplier", domain="master",
                targets=(_t("Supplier", "supplier_id", {"supplier_id": "supplier_id", "name": "name", "city": "city", "country_code": "country_code",
                                                      "supplier_type": "supplier_type", "status": "supplier_status"}),)),
    DatasetSpec("dealers", "master/dealers.json", m.Dealer, "dealer", domain="master",
                targets=(_t("Dealer", "dealer_id", DEALER_FIELDS),)),
    DatasetSpec("parts", "master/parts.json", m.Part, "part", domain="master", depends=("categories",), refs=(("category_id", "category"), ("subcategory_id", "category")),
                targets=(_t("Part", "part_id", {"part_id": "part_id", "part_number": "part_number", "name": "name", "manufacturer": "brand"}, mode="verify"),
                         # discovery text lives on the synthetic catalogue profile of the part, never on the protected Part node
                         _t("PartCatalogProfile", "profile_id", {"description": "description", "common_names": "common_names", "technical_terms": "technical_terms",
                                                                 "symptoms": "symptoms", "oem_status": "oem_status", "status": "part_status"},
                            id_fn=lambda r: f"PCP-{r.part_id}", create=False))),
    DatasetSpec("specifications", "master/specifications.json", m.Specification, "specification", domain="master", depends=("parts",), refs=(("part_id", "part"),),
                targets=(_t("PartSpecification", "specification_id", {"specification_id": "specification_id", "name": "name", "value": "value", "source_text": "source_text",
                                                                      "group": "group"}, mode="verify", casefold=("name",)),)),
    # ── relationships ────────────────────────────────────────────────────────────────────────────
    DatasetSpec("fitment", "relationships/fitment.csv", m.Fitment, "fitment", domain="relationships", depends=("machines", "parts"),
                targets=(_t("FitmentContext", "fitment_id", {"fitment_id": "fitment_id", "machine_id": "machine_id", "part_id": "part_id", "fitment_status": "fitment_status",
                                                             "approval_status": "approval_status", "fitment_rule": "fitment_rule", "valid_from": "valid_from",
                                                             "valid_to": "valid_to", "variant_id": "variant_id"},
                            rels=(RelDef("FITMENT_OF_PART", "part_id", "part"), RelDef("FITMENT_ON_MACHINE", "machine_id", "machine"))),)),
    DatasetSpec("approved_sources", "relationships/approved_sources.csv", m.ApprovedSource, domain="relationships", depends=("parts", "suppliers", "dealers"),
                rel=RelTarget("APPROVED_SOURCE", "part_id", "part", "source_id", None, "APPROVED_SOURCE:{id}", to_kind_from=("source_kind", SOURCE_KIND_TO_KIND),
                              fields={"source_kind": "source_kind", "approval_status": "approval_status", "approved_regions": "approved_regions",
                                      "valid_from": "valid_from", "valid_to": "valid_to"})),
    DatasetSpec("assemblies", "relationships/assemblies.csv", m.AssemblyLink, domain="relationships", depends=("parts",),
                rel=RelTarget("PART_OF", "part_id", "part", "assembly_id", "assembly", "PART_OF:{id}", fields={"quantity": "quantity", "basis": "basis"}, mode="verify")),
    DatasetSpec("legacy_part_mappings", "relationships/legacy_part_mappings.csv", m.LegacyPartMapping, domain="relationships", depends=("parts",),
                rel=RelTarget("HAS_LEGACY_REFERENCE", "part_id", "part", "legacy_mapping_id", "legacy", "HAS_LEGACY_REFERENCE:{id}", mode="verify")),
    # ── commerce ─────────────────────────────────────────────────────────────────────────────────
    DatasetSpec("customers", "commerce/customers.csv", m.Customer, "customer", domain="commerce",
                targets=(_t("Customer", "customer_id", {"customer_id": "customer_id", "name": "name", "city": "city", "country_code": "country_code",
                                                      "customer_type": "customer_type", "status": "customer_status"}),)),
    DatasetSpec("orders", "commerce/orders.csv", m.Order, "order", domain="commerce", depends=("customers", "dealers"),
                refs=(("customer_id", "customer"), ("dealer_id", "dealer")),
                targets=(_t("Order", "order_id", {"order_id": "order_id", "order_date": "order_date", "status": "order_status", "currency": "currency",
                                                  "total_value": "order_total_incl_vat", "channel": "channel"}, mode="verify"),)),
    DatasetSpec("order_lines", "commerce/order_lines.csv", m.OrderLine, "order_line", domain="commerce", depends=("orders", "parts"),
                refs=(("order_id", "order"), ("part_id", "part")),
                targets=(_t("OrderLine", "order_line_id", {"order_line_id": "order_line_id", "quantity": "quantity", "unit_price": "unit_price_eur"}, mode="verify"),)),
    DatasetSpec("inventory", "commerce/inventory.csv", m.Inventory, domain="commerce", depends=("parts", "locations"),
                rel=RelTarget("AVAILABLE_AT", "part_id", "part", "location_id", "location", "AVAILABLE_AT:{id}", mode="verify",
                              fields={"quantity": "on_hand", "available_quantity": "available", "reserved_quantity": "reserved", "status": "stock_status"})),
    DatasetSpec("pricing", "commerce/pricing.csv", m.Pricing, "price", domain="commerce", depends=("parts",), refs=(("dealer_id", "dealer"),),
                targets=(_t("Price", "price_id", {"price_id": "price_id", "currency": "currency", "unit_price": "list_price_ex_vat", "valid_from": "valid_from",
                                                  "valid_to": "valid_to", "status": "price_status"}),)),
    # ── logistics ────────────────────────────────────────────────────────────────────────────────
    DatasetSpec("routes", "logistics/routes.json", m.Route, "route", domain="logistics", depends=("locations",),
                targets=(_t("TransportRoute", "route_id", {"route_id": "route_id", "transport_mode": "transport_mode", "planned_transit_days": "total_estimated_days",
                                                           "service_level": "service_level", "status": "route_status", "origin_location_id": "origin_depot_id",
                                                           "destination_location_id": "destination_shipto_id"}),)),
    DatasetSpec("route_legs", "logistics/route_legs.csv", m.RouteLeg, domain="logistics", depends=("routes",),
                rel=RelTarget("HAS_LEG", "route_id", "route", "leg_id", "leg", "HAS_LEG:{id}", fields={"sequence": "sequence"}, mode="verify")),
    DatasetSpec("shipments", "logistics/shipments.csv", m.Shipment, "shipment", domain="logistics", depends=("orders", "routes", "locations"),
                refs=(("order_id", "order"), ("origin_location_id", "location"), ("destination_location_id", "location")),
                targets=(_t("Shipment", "shipment_id", SHIPMENT_FIELDS, rels=SHIPMENT_RELS),)),
    DatasetSpec("tracking_events", "logistics/tracking_events.csv", m.TrackingEvent, "tracking_event", domain="logistics", depends=("shipments",),
                refs=(("shipment_id", "shipment"), ("location_id", "location")),
                group_check=tracking_group_check, targets=(_t("TrackingEvent", "tracking_event_id", TRACKING_FIELDS, rels=TRACKING_RELS),)),
    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────
    DatasetSpec("machine_instances", "lifecycle/machine_instances.csv", m.MachineInstance, "machine_instance", domain="lifecycle", depends=("machines", "customers", "locations"),
                targets=(_t("MachineInstance", "machine_instance_id", {"machine_instance_id": "machine_instance_id", "serial_number": "serial_number", "model_year": "model_year",
                                                                       "status": "status", "machine_id": "machine_id", "variant_id": "variant_id"},
                            rels=(RelDef("INSTANCE_OF_VARIANT", "variant_id", "variant"), RelDef("INSTANCE_OF_MACHINE", "machine_id", "machine"),
                                  RelDef("OWNED_BY_CUSTOMER", "owner_id", "customer"), RelDef("LOCATED_AT", "location_id", "location"))),)),
    DatasetSpec("technicians", "lifecycle/technicians.csv", m.Technician, "technician", domain="lifecycle", depends=("dealers",),
                targets=(_t("Technician", "technician_id", {"technician_id": "technician_id", "name": "name", "certification": "certification", "specialization": "specialization",
                                                            "status": "status", "dealer_id": "dealer_id"},
                            rels=(RelDef("EMPLOYED_BY", "dealer_id", "dealer"),)),)),
    DatasetSpec("work_orders", "lifecycle/work_orders.csv", m.WorkOrder, "work_order", domain="lifecycle", depends=("machine_instances", "technicians"),
                targets=(_t("WorkOrder", "work_order_id", {"work_order_id": "work_order_id", "service_date": "service_date", "service_type": "service_type", "status": "status",
                                                           "reason": "reason"},
                            rels=(RelDef("HAS_WORK_ORDER", "machine_instance_id", "machine_instance", reverse=True), RelDef("PERFORMED_BY_DEALER", "dealer_id", "dealer"),
                                  RelDef("ASSIGNED_TO", "technician_id", "technician"))),)),
    DatasetSpec("installations", "lifecycle/installations.csv", m.InstallationEvent, "installation", domain="lifecycle", depends=("work_orders",),
                targets=(_t("InstallationEvent", "installation_id", {"installation_id": "installation_id", "part_serial_number": "part_serial_number",
                                                                     "installation_date": "installation_date", "removal_date": "removal_date", "status": "status",
                                                                     "validation_status": "validation_status", "validation_issues": "validation_issues"},
                            # the physical history of one machine: (MachineInstance)-HAS_INSTALLATION->(InstallationEvent)-INSTALLED_PART->(Part), done by a technician at a dealer, recorded in a work order
                            rels=(RelDef("HAS_INSTALLATION", "machine_instance_id", "machine_instance", reverse=True), RelDef("INSTALLED_PART", "part_id", "part"),
                                  RelDef("PERFORMED_AT", "dealer_id", "dealer"), RelDef("PERFORMED_BY", "technician_id", "technician"),
                                  RelDef("RECORDED_IN", "work_order_id", "work_order"))),)),
    DatasetSpec("replacements", "lifecycle/replacements.csv", m.ReplacementEvent, "replacement", domain="lifecycle", depends=("installations",),
                refs=(("removed_part_id", "part"), ("installed_part_id", "part")),
                targets=(_t("ReplacementEvent", "replacement_id", {"replacement_id": "replacement_id", "replacement_date": "replacement_date", "reason": "reason"},
                            rels=(RelDef("HAS_REPLACEMENT", "machine_instance_id", "machine_instance", reverse=True), RelDef("REMOVED_INSTALLATION", "removed_installation_id", "installation"),
                                  RelDef("NEW_INSTALLATION", "new_installation_id", "installation"), RelDef("RECORDED_IN", "work_order_id", "work_order"))),)),
    DatasetSpec("warranty_policies", "lifecycle/warranty_policies.json", m.WarrantyPolicy, "warranty_policy", domain="lifecycle", depends=("parts",),
                targets=(_t("WarrantyPolicy", "warranty_policy_id", {"warranty_policy_id": "warranty_policy_id", "coverage_type": "coverage_type",
                                                                     "coverage_period_days": "coverage_period_days", "coverage_conditions": "coverage_conditions",
                                                                     "start_rule": "start_rule", "region": "region", "status": "status"},
                            rels=(RelDef("WARRANTY_FOR_PART", "part_id", "part"),)),)),
    DatasetSpec("warranty_claims", "lifecycle/warranty_claims.csv", m.WarrantyClaim, "claim", domain="lifecycle", depends=("installations", "warranty_policies"),
                targets=(_t("WarrantyClaim", "claim_id", {"claim_id": "claim_id", "failure_date": "failure_date", "claim_date": "claim_date", "status": "status",
                                                          "decision": "decision", "decision_reason": "decision_reason"},
                            rels=(RelDef("HAS_CLAIM", "machine_instance_id", "machine_instance", reverse=True), RelDef("CLAIM_FOR_PART", "part_id", "part"),
                                  RelDef("CLAIM_ON_INSTALLATION", "installation_id", "installation"), RelDef("FILED_BY_DEALER", "dealer_id", "dealer"))),)),
    DatasetSpec("evidence", "lifecycle/evidence.csv", m.Evidence, "evidence", domain="lifecycle", depends=("installations", "work_orders", "warranty_claims"),
                targets=(_t("Evidence", "evidence_id", {"evidence_id": "evidence_id", "evidence_type": "evidence_type", "entity_type": "entity_type", "entity_id": "entity_id",
                                                        "reference": "reference", "created_at": "created_at"},
                            rels=(RelDef("SUPPORTS", "entity_id", None, kind_from=("entity_type", ENTITY_TYPE_TO_KIND)),)),)),
    # ── Phase 2: the global network (authored in reference/network_definition.json, expanded by app/canonical/network.py) ──
    DatasetSpec("network_suppliers", "master/network_suppliers.json", m.Supplier, "supplier", domain="network",
                targets=(_t("Supplier", "supplier_id", {"supplier_id": "supplier_id", "name": "name", "city": "city", "country_code": "country_code",
                                                      "supplier_type": "supplier_type", "status": "supplier_status"}),)),
    DatasetSpec("network_dealers", "master/network_dealers.json", m.Dealer, "dealer", domain="network",
                targets=(_t("Dealer", "dealer_id", DEALER_FIELDS),)),
    DatasetSpec("network_locations", "master/network_locations.json", m.Location, "location", domain="network", depends=("locations", "network_dealers", "network_suppliers"),
                targets=(LOCATION_TARGET,)),
    DatasetSpec("network_routes", "logistics/network_routes.json", m.Route, "route", domain="network", depends=("network_locations",),
                refs=(("origin_location_id", "location"), ("destination_location_id", "location")),
                targets=(_t("TransportRoute", "route_id", ROUTE_FIELDS, rels=(RelDef("ORIGIN_LOCATION", "origin_location_id", "location"),
                                                                                 RelDef("DESTINATION_LOCATION", "destination_location_id", "location"))),)),
    DatasetSpec("network_route_legs", "logistics/network_route_legs.csv", m.RouteLeg, "leg", domain="network", depends=("network_routes",),
                refs=(("origin_location_id", "location"), ("destination_location_id", "location")),
                targets=(NodeTarget(label="TransportLeg", key="leg_id", id_fn=lambda r: r.leg_id,
                                    fields={"leg_id": "leg_id", "origin_location_id": "origin_location_id", "destination_location_id": "destination_location_id", "transport_mode": "mode",
                                            "planned_transit_days": "planned_transit_days", "estimated_cost": "estimated_cost", "status": "leg_status", "distance_km": "distance_km"},
                                    rels=(RelDef("HAS_LEG", "route_id", "route", reverse=True, props=("sequence",)),)),)),
    DatasetSpec("network_orders", "commerce/network_orders.csv", m.Order, "order", domain="network", depends=("customers", "dealers", "network_dealers"),
                refs=(("customer_id", "customer"), ("dealer_id", "dealer")),
                targets=(_t("Order", "order_id", {"order_id": "order_id", "order_date": "order_date", "status": "order_status", "currency": "currency", "total_value": "order_total_incl_vat",
                                                  "channel": "channel"}, rels=(RelDef("ORDERED_BY", "customer_id", "customer"), RelDef("FOR_DEALER", "dealer_id", "dealer"))),)),
    DatasetSpec("network_order_lines", "commerce/network_order_lines.csv", m.OrderLine, "order_line", domain="network", depends=("network_orders", "parts"),
                targets=(_t("OrderLine", "order_line_id", {"order_line_id": "order_line_id", "quantity": "quantity", "unit_price": "unit_price_eur"},
                            rels=(RelDef("CONTAINS_LINE", "order_id", "order", reverse=True), RelDef("REFERENCES_PART", "part_id", "part"))),)),
    DatasetSpec("network_shipments", "logistics/network_shipments.csv", m.Shipment, "shipment", domain="network", depends=("network_orders", "network_order_lines", "network_routes", "network_locations"),
                refs=(("order_id", "order"), ("origin_location_id", "location"), ("destination_location_id", "location")),
                targets=(_t("Shipment", "shipment_id", SHIPMENT_FIELDS, rels=SHIPMENT_RELS),)),
    DatasetSpec("network_tracking_events", "logistics/network_tracking_events.csv", m.TrackingEvent, "tracking_event", domain="network", depends=("network_shipments",),
                refs=(("shipment_id", "shipment"), ("location_id", "location")), group_check=tracking_group_check,
                targets=(_t("TrackingEvent", "tracking_event_id", TRACKING_FIELDS, rels=TRACKING_RELS),)),
    # ── scenarios (data only: nothing reads these yet) ───────────────────────────────────────────
    *[DatasetSpec(f"scenarios_{n}", f"scenarios/{n}.json", m.FeaturedScenario, "scenario", domain="scenarios", depends=("machine_instances", "shipments", "orders"),
                  targets=(_t("FeaturedScenario", "scenario_id", {"scenario_id": "scenario_id", "scenario_type": "scenario_type", "title": "title", "notes": "notes"},
                              rels=(RelDef("FEATURES_MACHINE", "machine_id", "machine"), RelDef("FEATURES_PART", "part_id", "part"),
                                    RelDef("FEATURES_CUSTOMER", "customer_id", "customer"), RelDef("FEATURES_INSTANCE", "machine_instance_id", "machine_instance"),
                                    RelDef("FEATURES_SHIPMENT", "shipment_id", "shipment"), RelDef("FEATURES_ORDER", "order_id", "order"))),))
      for n in ("discovery", "logistics", "warranty")],
)
BY_NAME = {s.name: s for s in SPECS}


def order(names: list[str] | None = None) -> list[DatasetSpec]:
    """The requested datasets (all when None) in dependency order, each dataset after the ones it depends on."""
    wanted = list(BY_NAME) if not names else names
    unknown = [n for n in wanted if n not in BY_NAME]
    if unknown:
        raise KeyError(f"unknown dataset(s): {', '.join(unknown)}")
    out: list[DatasetSpec] = []
    seen: set[str] = set()

    def visit(n: str, wanted_set: set[str]) -> None:
        if n in seen or n not in wanted_set:
            return
        seen.add(n)
        for d in BY_NAME[n].depends:
            visit(d, wanted_set)
        out.append(BY_NAME[n])

    ws = set(wanted)
    for n in wanted:
        visit(n, ws)
    return out
