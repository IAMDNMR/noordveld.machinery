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
    PART_TO_INVENTORY = "PART_TO_INVENTORY"
    PART_TO_COMPLIANCE = "PART_TO_COMPLIANCE"
    PART_PROVENANCE = "PART_PROVENANCE"
    PART_GRAPH = "PART_GRAPH"
    MACHINE_GRAPH = "MACHINE_GRAPH"
    SUPPLIER_GRAPH = "SUPPLIER_GRAPH"
    DEALER_GRAPH = "DEALER_GRAPH"
    DATA_QUALITY = "DATA_QUALITY"
    UNSUPPORTED = "UNSUPPORTED"


class Kind(StrEnum):
    PART = "PART"
    MACHINE = "MACHINE"
    SUPPLIER = "SUPPLIER"
    DEALER = "DEALER"
    ASSEMBLY = "ASSEMBLY"
    CATEGORY = "CATEGORY"


@dataclass(frozen=True)
class ParsedQuestion:
    """What the question is about, before any entity is looked up. Produced by rules first, by an LLM only if rules cannot tell."""

    intent: Intent | None
    mentions: tuple[str, ...] = ()
    text: str = ""  # free-text residue, used by PART_SEARCH
    source: str = "rules"  # rules | llm
    clarification: str | None = None


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
