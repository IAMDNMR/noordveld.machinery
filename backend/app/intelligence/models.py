"""Internal domain types for Parts Intelligence."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.schemas.intelligence import Evidence, ResultItem


class Intent(StrEnum):
    PART_SEARCH = "PART_SEARCH"
    PART_TO_MACHINE = "PART_TO_MACHINE"
    MACHINE_TO_PART = "MACHINE_TO_PART"
    PART_TO_CATEGORY = "PART_TO_CATEGORY"
    PART_TO_ASSEMBLY = "PART_TO_ASSEMBLY"
    ASSEMBLY_TO_PART = "ASSEMBLY_TO_PART"
    PART_TO_PART = "PART_TO_PART"
    PART_TO_SUPPLIER = "PART_TO_SUPPLIER"
    PART_TO_DEALER = "PART_TO_DEALER"
    PART_TO_LOCATION = "PART_TO_LOCATION"
    PART_TO_WAREHOUSE = "PART_TO_WAREHOUSE"
    WAREHOUSE_STOCK = "WAREHOUSE_STOCK"
    PART_TO_INVENTORY = "PART_TO_INVENTORY"
    PART_TO_COMPLIANCE = "PART_TO_COMPLIANCE"
    PART_PROVENANCE = "PART_PROVENANCE"
    PART_GRAPH = "PART_GRAPH"
    MACHINE_GRAPH = "MACHINE_GRAPH"
    MACHINE_LIST = "MACHINE_LIST"
    SHARED_PARTS = "SHARED_PARTS"
    PART_TO_SERVICE_PLAN = "PART_TO_SERVICE_PLAN"
    PART_TO_ORDERS = "PART_TO_ORDERS"
    LOW_STOCK_PARTS = "LOW_STOCK_PARTS"
    SUPPLIER_GRAPH = "SUPPLIER_GRAPH"
    DEALER_GRAPH = "DEALER_GRAPH"
    DATA_QUALITY = "DATA_QUALITY"
    ENTITY_PATH = "ENTITY_PATH"
    ORDER_STATUS = "ORDER_STATUS"
    GEO_LOCATION = "GEO_LOCATION"
    UNSUPPORTED = "UNSUPPORTED"


class Kind(StrEnum):
    PART = "PART"
    MACHINE = "MACHINE"
    SUPPLIER = "SUPPLIER"
    DEALER = "DEALER"
    ASSEMBLY = "ASSEMBLY"
    CATEGORY = "CATEGORY"
    ORDER = "ORDER"
    WAREHOUSE = "WAREHOUSE"


@dataclass(frozen=True)
class ParsedQuestion:
    """What the question is about, before any entity is looked up. Always produced by the language model."""

    intent: Intent | None
    mentions: tuple[str, ...] = ()
    text: str = ""  # free-text residue, used by PART_SEARCH
    source: str = "llm"
    clarification: str | None = None
    single: bool = False  # "tell me about X": one entity expected, several matches are offered as a choice
    needs_clarification: bool = False  # the model asked for more detail instead of choosing an intent
    filters: dict = field(default_factory=dict)  # place, place_kind, proximity, location, target_kind, as returned by the model
    need: str = ""  # the requested kind of part, extracted by the model apart from the machine
    machine_named: str = ""  # a machine the question names, as written; it must resolve or the question is not answered


@dataclass(frozen=True)
class Resolved:
    kind: Kind
    id: str
    label: str
    detail: str | None
    data_status: str | None
    tier: int


@dataclass
class Outcome:
    """The result of executing one intent: structured results plus the evidence behind them. The summary here is deterministic."""

    summary: str
    results: list[ResultItem] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    total: int = 0
    warnings: list[str] = field(default_factory=list)
    actions: list = field(default_factory=list)
