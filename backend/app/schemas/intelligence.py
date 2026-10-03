"""API models for Parts Intelligence. Optional means the graph holds no value; nothing is defaulted or inferred."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Where a value comes from. NOT_CONNECTED means the graph has no such data at all (unknown, never zero).
DataClass = Literal["REAL", "SOURCE_DERIVED", "DERIVED", "SYNTHETIC_DEMO", "USER_PROVIDED", "TEST_DATA", "INTERNAL_REFERENCE_ONLY", "UNKNOWN", "NOT_CONNECTED"]
EntityKind = Literal["PART", "MACHINE", "SUPPLIER", "DEALER", "ASSEMBLY", "CATEGORY"]


class Fact(BaseModel):
    label: str
    value: str | None = None  # None renders as "Not available"


class FactGroup(BaseModel):
    label: str
    values: list[str]


class Action(BaseModel):
    kind: Literal["view_part", "parts_store", "investigate", "identify", "ask"]
    label: str
    href: str | None = None
    question: str | None = None


class ResultItem(BaseModel):
    """One thing in an answer, shaped for display: a primary key, a title, and separate labelled facts (never one long line)."""

    kind: Literal["part", "machine", "supplier", "dealer", "assembly", "category", "relationship", "compliance", "stock", "metric", "path"]
    key: str
    title: str
    subtitle: str | None = None
    part_number: str | None = None  # present when the item is a part the UI can open
    relationship: str | None = None
    data_class: DataClass = "UNKNOWN"
    facts: list[Fact] = []
    groups: list[FactGroup] = []


class Evidence(BaseModel):
    entity: str
    entity_kind: str
    relationship: str
    target: str
    target_kind: str
    data_class: DataClass


class ProvenanceSummary(BaseModel):
    data_class: DataClass
    count: int


class EntityRef(BaseModel):
    kind: EntityKind
    key: str
    label: str
    detail: str | None = None
    match: Literal["exact", "alias", "partial"]
    data_class: DataClass = "UNKNOWN"


class Candidate(BaseModel):
    kind: EntityKind
    key: str
    label: str
    detail: str | None = None


class Clarification(BaseModel):
    question: str
    candidates: list[Candidate] = []
    suggestions: list[str] = []


class Answer(BaseModel):
    summary: str
    grounded: bool  # true when every statement comes from graph evidence returned with this response
    source: Literal["template", "gemini"]


class SelectedEntity(BaseModel):
    kind: EntityKind
    key: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    selected: list[SelectedEntity] = Field(default=[], max_length=4)  # entities the user picked after a clarification
    limit: int = Field(default=12, ge=1, le=40)


class QueryResponse(BaseModel):
    question: str
    intent: str
    intent_label: str
    understood_by: Literal["rules", "llm", "selection"]
    entities: list[EntityRef]
    answer: Answer
    results: list[ResultItem]
    total: int
    evidence: list[Evidence]
    provenance: list[ProvenanceSummary]
    graph_path: list[str]
    warnings: list[str]
    actions: list[Action]
    clarification: Clarification | None = None
    elapsed_ms: int


# ── part workspace ────────────────────────────────────────────────────────────────────────────────
class PartStatus(BaseModel):
    code: Literal["VERIFIED", "IDENTIFICATION_REQUIRED", "UNVERIFIED", "OTHER"]
    label: str


class IdentificationNeed(BaseModel):
    model_code: str | None = None
    reason: str | None = None
    needed: str | None = None


class PartOverview(BaseModel):
    part_id: str
    part_number: str
    name: str
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    manufacturer: str | None = None
    origin_plant: str | None = None
    status: PartStatus
    identification: list[IdentificationNeed] = []
    data_class: DataClass
    source: str | None = None
    last_updated: str | None = None
    orderable: bool | None = None
    actions: list[Action]


class FitmentItem(BaseModel):
    model_code: str
    name: str | None = None
    machine_type: str | None = None
    family: str | None = None
    fitment_status: str | None = None
    condition_note: str | None = None
    data_class: DataClass


class RelatedItem(BaseModel):
    part_number: str
    name: str
    category: str | None = None
    relation: str
    relation_label: str
    interchangeability_status: str | None = None
    data_class: DataClass


class Component(BaseModel):
    part_number: str
    name: str
    quantity: int | None = None


class AssemblyItem(BaseModel):
    assembly_id: str
    name: str | None = None
    quantity: int | None = None
    bom_status: str | None = None
    identified_by: str | None = None
    component_count: int
    components: list[Component]
    data_class: DataClass


class SupplierItem(BaseModel):
    supplier_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    relation: str = "SUPPLIED_BY"
    is_primary: bool | None = None
    lead_time_days: int | None = None
    categories: list[str] = []
    data_class: DataClass


class DealerItem(BaseModel):
    dealer_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    relation: str = "STOCKED_BY"
    pickup_allowed: bool | None = None
    stocking_status: str | None = None
    available: int | None = None
    data_class: DataClass


class WarehouseItem(BaseModel):
    warehouse_id: str
    name: str | None = None
    city: str | None = None
    country_code: str | None = None
    available: int | None = None
    stock_status: str | None = None
    data_class: DataClass


class InventoryView(BaseModel):
    state: Literal["CONNECTED", "NOT_CONNECTED"]
    total_available: int | None = None  # None means unknown, never zero
    warehouses: list[WarehouseItem]
    dealers: list[DealerItem]
    data_class: DataClass
    note: str | None = None


class ComplianceItem(BaseModel):
    requirement: str | None = None
    standard: str | None = None
    certification: str | None = None
    certificate_status: str | None = None
    valid_until: str | None = None
    covers: list[str] = []
    data_class: DataClass


class RelationshipSource(BaseModel):
    relationship: str
    connected_label: str
    count: int
    data_class: DataClass


class ProvenanceReport(BaseModel):
    classification: DataClass
    source_name: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_record_id: str | None = None
    confidence: str | None = None
    authoritative: bool
    verification: str
    relationship_sources: list[RelationshipSource]
    limitations: list[str]
    last_updated: str | None = None


class Insight(BaseModel):
    key: str
    label: str
    value: int | str | None  # counts are computed in Neo4j/Python, never by a model
    detail: str | None = None
    state: Literal["present", "gap", "not_connected"] = "present"


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    part_number: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    data_class: DataClass


class GraphView(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False


class Kpis(BaseModel):
    parts: int
    machines: int
    fitments: int
    suppliers: int
    dealers: int
    assemblies: int
    relationships: int
    nodes: int
    synthetic_nodes: int
    provenance_coverage_pct: float  # nodes + relationships carrying data_status / all, computed deterministically
