"""Agentic Shopping API models. Every value comes from the graph; the model only reads the request."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalogue import PartSummary


class AgentRequest(BaseModel):
    request: str = Field(min_length=2, max_length=400)


class Interpretation(BaseModel):
    machine: str | None = None  # as resolved in the graph
    part_type: str | None = None
    preference: Literal["cheapest", "fastest", "none"] = "none"
    delivery_place: str | None = None
    quantity: int | None = None
    budget_max: float | None = None  # as the user stated it; compared with graph prices, never used to invent one
    budget_currency: str | None = None
    availability: Literal["require", "prefer", "none"] = "none"


class Step(BaseModel):
    key: Literal["request", "understand", "machine", "part", "fitment", "availability", "fulfilment", "compare", "recommend"]
    label: str
    status: Literal["done", "blocked", "skipped"]
    message: str


class Option(BaseModel):
    """A clarification choice. `refine` is appended to the request when chosen."""

    label: str
    refine: str


class EvidenceItem(BaseModel):
    key: Literal["fit", "verified", "budget", "availability", "inventory", "supplier", "delivery", "ranking"]
    ok: bool
    label: str
    detail: str
    data_class: str | None = None


class StockLocation(BaseModel):
    warehouse: str
    city: str | None = None
    available: int


class SupplierRef(BaseModel):
    name: str
    lead_time_days: int | None = None
    primary: bool = False


class Candidate(BaseModel):
    """One valid option. Every decision field carries an explicit state: a recorded value, or a plain "not recorded" wording."""

    part: PartSummary
    recommended: bool
    availability_label: str  # "In stock" / "Limited" / "Backorder" / "Availability not recorded"
    fitment_status: str | None = None
    fitment_label: str = "Fitment not verified"  # "Confirmed fit" / "Conditional fit · verification required"
    inventory: str = "Not recorded"  # "81 units across 4 warehouses"; unknown is never shown as zero
    stock_locations: list[StockLocation] = []
    fulfilment: str = "Fulfilment not recorded"  # how it is supplied: from stock, or after the supplier lead time
    delivery: str = "Estimate not recorded"  # when it reaches the requested place, only from a recorded estimate
    supplier_label: str = "Not recorded"
    suppliers: list[SupplierRef] = []
    price_basis: str | None = None  # "ex VAT": graph prices are list prices excluding VAT
    order_action: Literal["add_to_cart", "identify", "unavailable"] = "unavailable"
    order_note: str | None = None
    supplier: str | None = None  # primary supplier recorded in the graph
    supplier_lead_days: int | None = None
    fulfilment_days: int | None = None  # recorded delivery estimate, or supplier lead time when nothing is in stock
    within_budget: bool | None = None  # None when no budget was given
    tradeoffs: list[str] = []  # how an alternative differs from the recommendation, only where both values are recorded
    can_add_to_cart: bool = False  # verified, orderable, confirmed fitment and a recorded price


class Excluded(BaseModel):
    part_number: str
    name: str
    status_label: str


class Delivery(BaseModel):
    city: str
    warehouse: str
    warehouse_city: str | None = None
    standard_days: int | None = None
    express_days: int | None = None


class DecisionView(BaseModel):
    """What the decision was made on: hard requirements, then the ranking priorities in order, then the outcome in one line."""

    requirements: list[str]
    priorities: list[str]
    summary: str


class WhyItem(BaseModel):
    title: str
    detail: str


class ProvenanceRow(BaseModel):
    label: str
    value: str


class AgentResponse(BaseModel):
    request: str
    state: Literal["recommendation", "need_part", "need_machine", "need_detail", "choose_machine", "choose_type", "no_match", "out_of_scope"]
    interpretation: Interpretation
    steps: list[Step]
    question: str | None = None  # what the agent needs to know, for the clarification states
    options: list[Option] = []
    candidates: list[Candidate] = []
    recommended: str | None = None  # part number
    reason: str | None = None
    evidence: list[EvidenceItem] = []
    comparison: str | None = None
    excluded: list[Excluded] = []
    delivery: Delivery | None = None
    decision: DecisionView | None = None
    why: list[WhyItem] = []
    how_we_know: list[ProvenanceRow] = []
    notes: list[str] = []
    disclaimer: str = "Recommendation built from the Noordveld demo graph: fitment comes from the catalogue; status, price, stock, suppliers and delivery estimates are synthetic demo data. No order is placed until you check out, and order placement is not connected in this demo."


class AgentSuggestion(BaseModel):
    request: str
    need: str  # the part
    context: str  # the machine and its situation
    action: str  # what the agent should optimise for
