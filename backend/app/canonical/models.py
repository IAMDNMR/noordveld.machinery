"""Canonical data contracts (schema version 1.0).

Conventions
  * A field without a default is REQUIRED TO BE PRESENT in a record; where the source may not state a value its type allows None. A value is never
    invented to satisfy a field.
  * Every record carries provenance: data_status, source_type, optional source_record_id, effective_from/to, and (set by the engine)
    ingestion_timestamp. The existing graph vocabulary is kept: SOURCE_DERIVED, DERIVED and USER_PROVIDED stay valid next to REAL,
    SYNTHETIC_DEMO, REFERENCE and TEST.
  * CSV cells arrive as text: blanks become None, list fields are written 'a|b|c'.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

DataStatus = Literal["REAL", "SYNTHETIC_DEMO", "REFERENCE", "TEST", "SOURCE_DERIVED", "DERIVED", "USER_PROVIDED"]
SourceType = Literal["OEM_MASTER", "ERP", "PLM", "MES", "SERVICE", "DEALER", "LOGISTICS", "SYNTHETIC_DEMO", "REFERENCE"]
FitmentStatus = Literal["APPROVED", "CONDITIONAL", "DEPRECATED", "NOT_APPROVED"]
# The brief names SEA, AIR, ROAD and SEA_PLUS_ROAD as the initial modes; the existing network also uses these, so they are valid too (never remapped).
TransportMode = Literal["SEA", "AIR", "ROAD", "SEA_PLUS_ROAD", "SHORT_SEA", "RAIL", "MULTIMODAL", "INLAND_WATERWAY"]
SourceKind = Literal["OEM", "SUPPLIER", "DEALER"]
ApprovalStatus = Literal["APPROVED", "CONDITIONAL", "DEPRECATED", "NOT_APPROVED"]
StartRule = Literal["INSTALLATION_DATE", "DELIVERY_DATE", "PURCHASE_DATE"]
EvidenceType = Literal["SERVICE_REPORT", "INSTALLATION_RECORD", "INSPECTION_RECORD", "WORK_ORDER", "DEALER_RECORD", "TECHNICIAN_RECORD", "PART_RECORD", "SHIPMENT_RECORD", "ORDER_RECORD"]
ValidationStatus = Literal["VALID", "INCOMPLETE"]
LocationKind = Literal["PLANT", "DEPOT", "SHIP_TO", "CITY", "COUNTRY", "DEALER", "TERMINAL", "SUPPLIER"]  # structural kind: what sort of graph record holds it
LogisticsType = Literal["WAREHOUSE", "DISTRIBUTION_CENTER", "DEALER", "PORT", "AIRPORT", "TERMINAL", "CUSTOMS", "SUPPLIER", "PLANT"]  # what it is in a logistics network
Region = Literal["EUROPE", "USA", "AFRICA", "ASIA"]
TerminalType = Literal["SEAPORT", "AIRPORTCARGOTERMINAL", "CROSSDOCK", "INLANDPORT", "RAILTERMINAL"]
# PICKED is the legacy first event of the seeded shipments; the rest is the lifecycle of a managed shipment (see app/logistics/rules.py for the allowed order)
TrackingType = Literal["PICKED", "ORDER_CONFIRMED", "BOOKED", "DEPARTED_ORIGIN", "IN_TRANSIT", "ARRIVED_PORT", "CUSTOMS", "DEPARTED_PORT", "ARRIVED_DC", "OUT_FOR_DELIVERY", "DELIVERED"]
RouteResolution = Literal["LINKED", "ROUTE_NOT_DETERMINABLE"]
OemStatus = Literal["OEM", "NON_OEM", "UNKNOWN"]

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")


def _blank(v: Any) -> Any:
    return None if isinstance(v, str) and v.strip() == "" else v


def _pipe(v: Any) -> Any:
    v = _blank(v)
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split("|") if x.strip()]
    return v


def _iso(v: str | None) -> str | None:
    if v is not None and not ISO.match(v):
        raise ValueError(f"not an ISO date or timestamp: {v!r}")
    return v


Blank = BeforeValidator(_blank)
Iso = Annotated[str | None, Blank, AfterValidator(_iso)]
IsoRequired = Annotated[str, AfterValidator(_iso)]
Opt = Annotated[str | None, Blank]
OptInt = Annotated[int | None, Blank]
OptFloat = Annotated[float | None, Blank]
OptBool = Annotated[bool | None, Blank]
Pipe = Annotated[list[str], BeforeValidator(_pipe)]
Id = Annotated[str, Field(min_length=1, max_length=160)]


class Canon(BaseModel):
    """Base of every canonical record: strict fields plus the provenance block."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ID: ClassVar[str] = ""
    data_status: DataStatus
    source_type: SourceType
    source_record_id: Opt = None
    ingestion_timestamp: Iso = None
    effective_from: Iso = None
    effective_to: Iso = None

    @property
    def id(self) -> str:
        return getattr(self, self.ID)

    @model_validator(mode="after")
    def _effective_range(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to is before effective_from")
        return self


# ── master data ──────────────────────────────────────────────────────────────────────────────────
class Machine(Canon):
    ID = "machine_id"
    machine_id: Id
    manufacturer: Opt
    model: Id
    machine_type: Id
    model_year: OptInt
    variant_id: Opt
    plant_id: Opt
    status: Opt
    name: Opt = None


class MachineInstance(Canon):
    """The physical machine. A variant is the product definition; the instance has a serial number."""

    ID = "machine_instance_id"
    machine_instance_id: Id
    machine_id: Id
    variant_id: Id
    serial_number: Id
    model_year: OptInt
    owner_id: Opt
    location_id: Opt
    status: Id


class Part(Canon):
    ID = "part_id"
    part_id: Id
    part_number: Id
    name: Id
    description: Opt
    category_id: Id
    subcategory_id: Opt
    manufacturer: Opt
    oem_status: Annotated[OemStatus | None, Blank]
    status: Opt
    aliases: Pipe = []
    common_names: Pipe = []
    technical_terms: Pipe = []
    symptoms: Pipe = []


class Category(Canon):
    ID = "category_id"
    category_id: Id
    name: Id
    parent_category_id: Opt
    status: Opt


class Specification(Canon):
    ID = "specification_id"
    specification_id: Id
    part_id: Id
    name: Id
    value: Opt
    unit: Opt
    source_text: Opt
    group: Opt = None


class Supplier(Canon):
    ID = "supplier_id"
    supplier_id: Id
    name: Id
    city: Opt = None
    country_code: Opt = None
    supplier_type: Opt = None
    status: Opt = None


class Dealer(Canon):
    ID = "dealer_id"
    dealer_id: Id
    name: Id
    city: Opt = None
    country_code: Opt = None
    dealer_type: Opt = None
    status: Opt = None
    latitude: OptFloat = None
    longitude: OptFloat = None
    location_id: Opt = None  # a dealer is its own place: this is the dealer_id, so routes and shipments can end at it
    country: Opt = None
    region: Annotated[Region | None, Blank] = None
    authorized_status: Opt = None
    service_capable: OptBool = None
    warranty_capable: OptBool = None


class Plant(Canon):
    ID = "plant_id"
    plant_id: Id
    name: Id
    city: Opt = None
    country_code: Opt = None


class Location(Canon):
    """One namespace of places. `graph_label` says which graph node holds it (Warehouse, ShipTo, Plant or Location)."""

    ID = "location_id"
    location_id: Id
    name: Opt
    location_kind: LocationKind
    graph_label: Literal["Warehouse", "ShipTo", "Plant", "Location", "TransportTerminal", "Dealer", "Supplier"]
    country_code: Opt = None
    city: Opt = None
    latitude: OptFloat = None
    longitude: OptFloat = None
    geo_basis: Opt = None
    location_type: Annotated[LogisticsType | None, Blank] = None  # set for logistics-relevant places; None for ship-tos, cities and countries
    country: Opt = None
    region: Annotated[Region | None, Blank] = None
    timezone: Opt = None
    terminal_type: Annotated[TerminalType | None, Blank] = None  # for terminals: also becomes the node's second label
    modes: Pipe = []


# ── relationships ────────────────────────────────────────────────────────────────────────────────
class Fitment(Canon):
    """Context around one FITS relationship. fitment_id is the id of that FITS relationship, so the two stay 1:1."""

    ID = "fitment_id"
    fitment_id: Id
    machine_id: Id
    variant_id: Opt
    part_id: Id
    fitment_status: FitmentStatus
    approval_status: ApprovalStatus
    fitment_rule: Opt
    valid_from: Iso = None
    valid_to: Iso = None


class ApprovedSource(Canon):
    """The part's approved source. `source_kind` is the brief's `source_type` (OEM, SUPPLIER, DEALER); `source_type` is the provenance field."""

    ID = "approved_source_id"
    approved_source_id: Id
    part_id: Id
    source_id: Id
    source_kind: SourceKind
    approval_status: ApprovalStatus
    approved_regions: Pipe = []
    valid_from: Iso = None
    valid_to: Iso = None


class AssemblyLink(Canon):
    ID = "link_id"
    link_id: Id
    part_id: Id
    assembly_id: Id
    quantity: OptInt = None
    basis: Opt = None


class LegacyPartMapping(Canon):
    ID = "legacy_mapping_id"
    legacy_mapping_id: Id
    part_id: Id
    legacy_part_number: Opt
    legacy_system: Opt = None


# ── commerce ─────────────────────────────────────────────────────────────────────────────────────
class Customer(Canon):
    ID = "customer_id"
    customer_id: Id
    name: Id
    city: Opt = None
    country_code: Opt = None
    customer_type: Opt = None
    status: Opt = None


class Order(Canon):
    ID = "order_id"
    order_id: Id
    customer_id: Opt
    dealer_id: Opt
    order_date: IsoRequired
    status: Id
    priority: Opt
    currency: Opt
    total_value: OptFloat
    channel: Opt = None


class OrderLine(Canon):
    ID = "order_line_id"
    order_line_id: Id
    order_id: Id
    part_id: Id
    quantity: Annotated[int, Field(ge=1)]
    unit_price: OptFloat
    requested_date: Iso = None


class Inventory(Canon):
    ID = "inventory_id"
    inventory_id: Id
    part_id: Id
    location_id: Id
    quantity: OptInt
    available_quantity: OptInt
    reserved_quantity: OptInt
    status: Id
    last_updated: Iso = None


class Pricing(Canon):
    ID = "price_id"
    price_id: Id
    part_id: Id
    dealer_id: Opt
    region: Opt
    currency: Id
    unit_price: Annotated[float, Field(ge=0)]
    valid_from: Iso = None
    valid_to: Iso = None
    status: Opt = None


# ── logistics ────────────────────────────────────────────────────────────────────────────────────
class Route(Canon):
    """Route-level estimate. Shipment actuals live on the shipment, never here."""

    ID = "route_id"
    route_id: Id
    origin_location_id: Id
    destination_location_id: Id
    transport_mode: TransportMode
    planned_transit_days: OptInt
    estimated_cost: OptFloat
    currency: Opt
    service_level: Opt
    status: Opt


class RouteLeg(Canon):
    ID = "route_leg_id"
    route_leg_id: Id
    route_id: Id
    leg_id: Id
    sequence: Annotated[int, Field(ge=1)]
    origin_location_id: Opt
    destination_location_id: Opt
    transport_mode: Annotated[TransportMode | None, Blank]
    planned_transit_days: OptInt
    estimated_cost: OptFloat
    status: Opt
    distance_km: OptFloat = None


class Shipment(Canon):
    ID = "shipment_id"
    shipment_id: Id
    order_id: Opt
    carrier: Opt
    route_id: Opt
    origin_location_id: Opt
    destination_location_id: Opt
    transport_mode: Annotated[TransportMode | None, Blank]
    status: Id
    departure_date: Iso = None
    planned_eta: Iso = None
    actual_eta: Iso = None
    tracking_ref: Opt = None
    remediation_flags: Pipe = []
    route_resolution_status: Annotated[RouteResolution | None, Blank] = None
    order_line_id: Opt = None
    carrier_id: Opt = None

    @model_validator(mode="after")
    def _resolution_matches_route(self):
        if self.route_resolution_status == "LINKED" and not self.route_id:
            raise ValueError("a LINKED shipment needs a route_id")
        if self.route_resolution_status == "ROUTE_NOT_DETERMINABLE" and self.route_id:
            raise ValueError("a shipment with a route_id is not ROUTE_NOT_DETERMINABLE")
        return self


class TrackingEvent(Canon):
    ID = "tracking_event_id"
    tracking_event_id: Id
    shipment_id: Id
    timestamp: IsoRequired
    location_id: Opt
    location_text: Opt = None
    status: Id
    event_type: TrackingType
    description: Opt
    sequence: OptInt = None


# ── lifecycle ────────────────────────────────────────────────────────────────────────────────────
class Technician(Canon):
    ID = "technician_id"
    technician_id: Id
    dealer_id: Id
    name: Id
    certification: Opt
    specialization: Opt
    status: Id


class WorkOrder(Canon):
    ID = "work_order_id"
    work_order_id: Id
    machine_instance_id: Id
    dealer_id: Id
    technician_id: Opt
    service_date: IsoRequired
    service_type: Id
    status: Id
    reason: Opt


class InstallationEvent(Canon):
    ID = "installation_id"
    installation_id: Id
    machine_instance_id: Id
    part_id: Id
    part_serial_number: Opt
    dealer_id: Id
    technician_id: Opt
    work_order_id: Opt
    installation_date: IsoRequired
    removal_date: Iso = None
    status: Literal["CURRENT", "REMOVED"]
    # computed by app.lifecycle.rules.validate_installation: a record with a reference that is intentionally unavailable is INCOMPLETE, never silently filled
    validation_status: Annotated[ValidationStatus | None, Blank] = None
    validation_issues: Pipe = []

    @model_validator(mode="after")
    def _removal(self):
        if self.removal_date and self.removal_date < self.installation_date:
            raise ValueError("removal_date is before installation_date")
        if self.status == "CURRENT" and self.removal_date:
            raise ValueError("a CURRENT installation has no removal_date")
        if self.status == "REMOVED" and not self.removal_date:
            raise ValueError("a REMOVED installation needs a removal_date")
        return self


class ReplacementEvent(Canon):
    ID = "replacement_id"
    replacement_id: Id
    machine_instance_id: Id
    removed_part_id: Id
    installed_part_id: Id
    removed_installation_id: Id
    new_installation_id: Id
    replacement_date: IsoRequired
    reason: Opt
    work_order_id: Opt


class WarrantyPolicy(Canon):
    """A part's warranty as data: how long, from when, and WHICH conditions apply (codes from app.lifecycle.rules.CONDITIONS). region None = every region."""

    ID = "warranty_policy_id"
    warranty_policy_id: Id
    part_id: Id
    coverage_type: Id
    coverage_period_days: Annotated[int, Field(ge=1)]
    coverage_conditions: Pipe = []
    start_rule: StartRule
    region: Opt
    status: Id

    @model_validator(mode="after")
    def _known_conditions(self):
        from app.lifecycle.rules import CONDITIONS

        unknown = [c for c in self.coverage_conditions if c not in CONDITIONS]
        if unknown:
            raise ValueError(f"unknown warranty condition(s): {', '.join(unknown)}")
        return self


class WarrantyClaim(Canon):
    ID = "claim_id"
    claim_id: Id
    machine_instance_id: Id
    part_id: Id
    installation_id: Opt
    failure_date: IsoRequired
    claim_date: IsoRequired
    dealer_id: Opt
    status: Literal["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "CLOSED"]
    decision: Opt
    decision_reason: Opt


class Evidence(Canon):
    """A pointer to a record that supports a fact. `reference` is never a fabricated URL or document id: synthetic evidence says so."""

    ID = "evidence_id"
    evidence_id: Id
    evidence_type: EvidenceType
    entity_type: Id
    entity_id: Id
    reference: Opt
    created_at: Iso = None

    @model_validator(mode="after")
    def _no_fake_references(self):
        if self.reference and re.match(r"^(https?|ftp)://", self.reference, re.IGNORECASE) and self.data_status != "REAL":
            raise ValueError("a non-REAL evidence record must not carry a URL reference")
        return self


class FeaturedScenario(Canon):
    """Which graph records a demo story features (replaces the FILM_* constants). Data only: no workflow reads it yet."""

    ID = "scenario_id"
    scenario_id: Id
    scenario_type: Literal["DISCOVERY", "LOGISTICS", "WARRANTY", "FILM"]
    title: Id
    machine_id: Opt = None
    part_id: Opt = None
    customer_id: Opt = None
    machine_instance_id: Opt = None
    shipment_id: Opt = None
    order_id: Opt = None
    notes: Opt = None
