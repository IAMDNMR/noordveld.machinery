"""Response models for the catalogue API. Optional means the graph does not hold the value; it is never filled with a default."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DataStatus = str  # SOURCE_DERIVED | DERIVED | USER_PROVIDED | SYNTHETIC_DEMO, passed through unchanged


class Money(BaseModel):
    amount: float
    currency: str
    data_status: DataStatus | None = None


class Availability(BaseModel):
    state: str | None = None
    orderable: bool | None = None
    part_status: str | None = None
    total_available: int | None = None
    data_status: DataStatus | None = None


class FitmentBrief(BaseModel):
    model_code: str
    fitment_status: str | None = None


class PartSummary(BaseModel):
    part_id: str
    part_number: str
    name: str
    category: str | None = None
    subcategory: str | None = None
    fitment: list[FitmentBrief]
    price: Money | None = None
    availability: Availability | None = None


class PartPage(BaseModel):
    items: list[PartSummary]
    total: int
    offset: int
    limit: int


class MachineOption(BaseModel):
    machine_id: str
    model_code: str
    name: str
    machine_type: str | None = None
    origin_plant: str | None = None
    country: str | None = None
    part_count: int


class CategoryOption(BaseModel):
    category_id: str
    name: str
    part_count: int


class AvailabilityOption(BaseModel):
    state: str
    part_count: int
    data_status: DataStatus | None = None


class CatalogueFilters(BaseModel):
    categories: list[CategoryOption]
    machines: list[MachineOption]
    availability: list[AvailabilityOption]


class Provenance(BaseModel):
    data_status: DataStatus | None = None
    source_record_id: str | None = None


class PartCore(BaseModel):
    part_id: str
    part_number: str
    name: str
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    origin_plant: str | None = None
    note: str | None = None
    confidence: str | None = None
    data_status: DataStatus | None = None
    source_sheet: str | None = None
    source_record_id: str | None = None


class Fitment(BaseModel):
    machine_id: str
    model_code: str
    name: str
    machine_type: str | None = None
    origin_plant: str | None = None
    fitment_status: str | None = None
    condition_note: str | None = None
    data_status: DataStatus | None = None


class Specification(BaseModel):
    group: str | None = None
    name: str
    value: str | None = None
    unit: str | None = None
    source_text: str | None = None
    data_status: DataStatus | None = None


class LegacyReference(BaseModel):
    legacy_part_number: str | None = None
    legacy_business: str | None = None
    legacy_plant: str | None = None
    mapping_type: str | None = None
    note: str | None = None
    mapping_confidence: str | None = None
    data_status: DataStatus | None = None


class PriceInfo(BaseModel):
    amount: float
    currency: str
    valid_from: str | None = None
    valid_to: str | None = None
    price_status: str | None = None
    data_status: DataStatus | None = None


class Profile(BaseModel):
    availability_state: str | None = None
    orderable: bool | None = None
    part_status: str | None = None
    status_reason: str | None = None
    weight_kg: float | None = None
    warranty_months: int | None = None
    return_window_days: int | None = None
    data_status: DataStatus | None = None


class WarehouseStock(BaseModel):
    warehouse_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    available: int | None = None
    stock_status: str | None = None
    data_status: DataStatus | None = None


class DealerStock(BaseModel):
    dealer_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    pickup_allowed: bool | None = None
    available: int | None = None
    stocking_status: str | None = None
    data_status: DataStatus | None = None


class SupplierInfo(BaseModel):
    supplier_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    is_primary: bool | None = None
    lead_time_days: int | None = None
    min_order_qty: int | None = None
    supplier_part_number: str | None = None
    data_status: DataStatus | None = None


class Compliance(BaseModel):
    requirement: str | None = None
    standard: str | None = None
    certification: str | None = None
    certificate_status: str | None = None
    valid_until: str | None = None
    data_status: DataStatus | None = None


class AssemblyLink(BaseModel):
    assembly_id: str
    name: str | None = None
    quantity: int | None = None
    bom_status: str | None = None
    data_status: DataStatus | None = None


RelationKind = Literal["SAME_NAME_GROUP_AS", "RELATED_COMPONENT", "CO_ORDERED_WITH"]


class RelatedPart(BaseModel):
    """A part connected by a graph relationship. `relation` says what the link means; none of them state interchangeability."""

    part_id: str
    part_number: str
    name: str
    category: str | None = None
    relation: RelationKind
    interchangeability_status: str | None = None
    data_status: DataStatus | None = None


class IdentificationVariant(BaseModel):
    variant_name: str | None = None
    serial_from: str | None = None
    serial_to: str | None = None


class Identification(BaseModel):
    model_code: str | None = None
    reason: str | None = None
    identification_needed: str | None = None
    variants: list[IdentificationVariant] = []
    data_status: DataStatus | None = None


class PartDetail(BaseModel):
    part: PartCore
    fitment: list[Fitment]
    specifications: list[Specification]
    legacy_references: list[LegacyReference]
    price: PriceInfo | None = None
    profile: Profile | None = None
    warehouses: list[WarehouseStock]
    dealers: list[DealerStock]
    suppliers: list[SupplierInfo]
    compliance: list[Compliance]
    assemblies: list[AssemblyLink]
    related: list[RelatedPart]
    identification: list[Identification]
