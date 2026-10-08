"""The common result model of every context: CommerceDecision, the shared metadata, source records, evidence and the evidence path.

Statuses are the only vocabulary an agent has to branch on. Nothing here knows a domain rule; the domain modules decide and fill these in.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SUCCESS, NOT_FOUND, NOT_ELIGIBLE, REQUIRES_REVIEW, REQUIRES_CLARIFICATION, INSUFFICIENT_DATA = (
    "SUCCESS", "NOT_FOUND", "NOT_ELIGIBLE", "REQUIRES_REVIEW", "REQUIRES_CLARIFICATION", "INSUFFICIENT_DATA")
STATUSES = (SUCCESS, NOT_FOUND, NOT_ELIGIBLE, REQUIRES_REVIEW, REQUIRES_CLARIFICATION, INSUFFICIENT_DATA)
UNDECIDED = frozenset({NOT_FOUND, REQUIRES_CLARIFICATION, INSUFFICIENT_DATA})  # no business answer could be given from the records
GRAPH_SUPPORTED = frozenset({"REAL", "SOURCE_DERIVED"})  # the only data_status values that can support the word "verified"


class ContextType(str, Enum):
    DISCOVERY = "DISCOVERY"
    LOGISTICS = "LOGISTICS"
    WARRANTY = "WARRANTY"


def record(entity: str, record_id: str | None, row: dict[str, Any] | None = None) -> dict[str, Any]:
    """A source record reference: which graph entity, which id, and the provenance the record itself carries."""
    row = row or {}
    return {"entity": entity, "id": record_id, "data_status": row.get("data_status"), "source_type": row.get("source_type"), "source_record_id": row.get("source_record_id")}


def evidence_item(fact: str, entity: str, record_id: str | None, row: dict[str, Any] | None = None) -> dict[str, Any]:
    """One supported statement and the record it was read from."""
    return {"fact": fact, "entity": entity, "id": record_id, "data_status": (row or {}).get("data_status")}


def path_step(order: int, entity: str, record_id: str | None, relation_to_next: str | None = None, row: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"step": order, "entity": entity, "id": record_id, "relation_to_next": relation_to_next, "data_status": (row or {}).get("data_status")}


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str | None], dict[str, Any]] = {}
    for r in records:
        if r and (r["entity"], r["id"]) not in seen:
            seen[(r["entity"], r["id"])] = r
    return sorted(seen.values(), key=lambda r: (r["entity"], str(r["id"])))


def aggregate_data_status(records: list[dict[str, Any]]) -> str:
    """One value if every record agrees, MIXED if they differ, NONE if nothing was read. Never upgraded."""
    values = sorted({r["data_status"] for r in records if r.get("data_status")})
    return "NONE" if not values else values[0] if len(values) == 1 else "MIXED"


def confidence_for(status: str, records: list[dict[str, Any]], missing: list[str]) -> dict[str, Any]:
    """How complete the answer is and whether the underlying records can support the word 'verified'. Demonstration data never can."""
    level = "INSUFFICIENT" if status in UNDECIDED else "PARTIAL" if missing else "COMPLETE"
    statuses = {r.get("data_status") for r in records}
    verified = level == "COMPLETE" and bool(records) and statuses <= GRAPH_SUPPORTED
    if not records:
        basis = "No record supports this result."
    elif verified:
        basis = "Every source record is graph-verified data."
    else:
        basis = "Deterministic result on " + ", ".join(sorted(s for s in statuses if s)) + " records; not verified against real-world records."
    return {"level": level, "verified": verified, "basis": basis}


def context_id(context_type: str, inputs: dict[str, Any], as_of: str, status: str, decision: str, records: list[dict[str, Any]]) -> str:
    """Stable for the same request on the same data: derived from the request, the reference day, the outcome and the records used (never the clock)."""
    body = json.dumps({"t": context_type, "in": inputs, "as_of": as_of, "s": status, "d": decision, "r": [(r["entity"], r["id"]) for r in records]}, sort_keys=True, default=str)
    return "CTX-" + hashlib.sha256(body.encode()).hexdigest()[:16].upper()


@dataclass(kw_only=True)
class CommerceDecision:
    """What the agent may say. `facts` are the supported values; `reasons` say why; `evidence` and `source_records` say where they come from."""

    status: str
    decision: str
    summary: str
    facts: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_next_action: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")


@dataclass(kw_only=True)
class CommerceContext:
    """The common metadata of every context. Domain contexts add their own fields after these."""

    context_id: str
    context_type: str
    generated_at: str
    data_status: str
    source_records: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    confidence: dict[str, Any]
    missing: list[str]
    warnings: list[str]
    decision: CommerceDecision
    evidence_path: list[dict[str, Any]]
    visibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_iso(clock: Any = None) -> str:
    return (clock() if clock else datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def meta(context_type: str, inputs: dict[str, Any], as_of: str, generated_at: str, decision: CommerceDecision, records: list[dict[str, Any]], evidence: list[dict[str, Any]],
         path: list[dict[str, Any]]) -> dict[str, Any]:
    """Every common field, computed once and the same way for all three journeys. The decision carries the same records and missing list as the context."""
    records = dedupe_records(records)
    decision.source_records = records
    return {"context_id": context_id(context_type, inputs, as_of, decision.status, decision.decision, records), "context_type": context_type, "generated_at": generated_at,
            "data_status": aggregate_data_status(records), "source_records": records, "evidence": evidence, "confidence": confidence_for(decision.status, records, decision.missing),
            "missing": list(decision.missing), "warnings": list(decision.warnings), "decision": decision, "evidence_path": path}
