"""Two questions about ONE part that the discovery context (machine -> part) does not answer, read straight from the same records:

  PART_FITMENT  "Which machine uses this part?"        the machines the part is approved for, from the fitment records
  PART_ORIGIN   "Where did this part come from?"       the recorded manufacturer, catalogue record and approved sources, with their provenance

No rule lives here: a machine is listed only when a fitment record APPROVES it (the same test the discovery and warranty rules use), a source only when an approved-source record exists, and
anything the records do not hold is reported as not recorded, never as a confirmed negative. The result carries the common context contract (decision, evidence, evidence path, source records,
confidence) so it is shown and audited like every other answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.commerce import contract as c
from app.commerce.engine import CommerceContextEngine
from app.lifecycle.rules import APPROVED

PART_FITMENT, PART_ORIGIN = "PART_FITMENT", "PART_ORIGIN"


@dataclass(kw_only=True)
class PartLookupContext(c.CommerceContext):
    lookup: str = PART_FITMENT
    part: dict[str, Any] | None = None
    machines: list[dict[str, Any]] = field(default_factory=list)  # PART_FITMENT: approved machines; other fitment statuses are listed apart
    other_fitments: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)  # PART_ORIGIN: approved sources
    catalogue: dict[str, Any] | None = None


def _context(engine: CommerceContextEngine, kind: str, inputs: dict[str, Any], decision: c.CommerceDecision, records: list[dict[str, Any]], evidence: list[dict[str, Any]],
             path: list[dict[str, Any]], **fields: Any) -> PartLookupContext:
    meta = c.meta("DISCOVERY", {**inputs, "lookup": kind}, engine._today().isoformat(), engine._generated_at(), decision, records, evidence, path)
    ctx = PartLookupContext(**meta, lookup=kind, **fields)
    ctx.visibility = {"role": "ALL", "hidden_fields": []}
    return ctx


def _not_found(engine: CommerceContextEngine, kind: str, part_id: str) -> PartLookupContext:
    d = c.CommerceDecision(status=c.NOT_FOUND, decision="NOT_FOUND", summary=f"No part {part_id} is recorded.", missing=["part"])
    return _context(engine, kind, {"part_id": part_id}, d, [], [], [])


def part_fitment(engine: CommerceContextEngine, part_id: str) -> PartLookupContext:
    part = engine.discovery.part(part_id)
    if part is None:
        return _not_found(engine, PART_FITMENT, part_id)
    approved, other = [], []
    for m in engine.discovery.machines():
        for f in engine.discovery.fitments(m["machine_id"], part_id):
            row = {"machine_id": m["machine_id"], "model": m["model"], "name": m["name"], "fitment_id": f["fitment_id"], "approval_status": f["approval_status"], "fitment_rule": f.get("fitment_rule"),
                   "data_status": f.get("data_status")}
            (approved if f["approval_status"] == APPROVED else other).append(row)
    label = f"{part['name']} ({part['part_number']})"
    records = [c.record("Part", part_id, part)] + [c.record("Fitment", r["fitment_id"], r) for r in approved + other]
    evidence = [c.evidence_item(f"{part['part_number']} is approved for {r['model']}", "Fitment", r["fitment_id"], r) for r in approved]
    path = [c.path_step(1, "Part", part_id, "FITS" if approved else None, part)] + [c.path_step(i + 2, "Fitment", r["fitment_id"], None, r) for i, r in enumerate(approved)]
    if approved:
        d = c.CommerceDecision(status=c.SUCCESS, decision=PART_FITMENT, summary=f"{label} is approved for {len(approved)} machine model(s): {', '.join(r['model'] for r in approved)}.",
                               facts={"part_id": part_id, "approved_models": [r["model"] for r in approved], "other_fitment_records": len(other)},
                               reasons=["a fitment record with approval_status APPROVED links the part to each model"])
    else:
        d = c.CommerceDecision(status=c.SUCCESS, decision="NO_APPROVED_FITMENT", summary=f"No fitment record approves {label} for any machine model" + (f"; {len(other)} record(s) exist with another status." if other else "."),
                               facts={"part_id": part_id, "approved_models": [], "other_fitment_records": len(other)}, reasons=["no fitment record with approval_status APPROVED"])
    return _context(engine, PART_FITMENT, {"part_id": part_id}, d, records, evidence, path, part=part, machines=approved, other_fitments=other)


def part_origin(engine: CommerceContextEngine, part_id: str) -> PartLookupContext:
    part = engine.discovery.part(part_id)
    if part is None:
        return _not_found(engine, PART_ORIGIN, part_id)
    sources = [s for s in engine.discovery.approved_sources(part_id)]
    approved = [s for s in sources if s.get("approval_status") == APPROVED]
    label = f"{part['name']} ({part['part_number']})"
    kind = {"SOURCE_DERIVED": "supplied catalogue data", "DERIVED": "data derived from the supplied catalogue", "REAL": "real data", "SYNTHETIC_DEMO": "synthetic demonstration data"}.get(part.get("data_status") or "", "data of unstated kind")
    catalogue = {"manufacturer": part.get("manufacturer"), "oem_status": part.get("oem_status"), "catalogue_status": part.get("status"), "data_status": part.get("data_status"), "source_type": part.get("source_type")}
    bits = [f"manufacturer {part['manufacturer']}" if part.get("manufacturer") else "manufacturer not recorded", f"catalogue record is {kind}",
            f"{len(approved)} approved source(s): {', '.join(s['source_id'] for s in approved)}" if approved else "no approved source is recorded"]
    records = [c.record("Part", part_id, part)] + [c.record("ApprovedSource", s["approved_source_id"], s) for s in sources]
    evidence = [c.evidence_item(f"{part['part_number']} catalogue record: {kind}", "Part", part_id, part)] + [
        c.evidence_item(f"{part['part_number']} has an approved {str(s.get('source_kind')).lower()} source {s['source_id']}", "ApprovedSource", s["approved_source_id"], s) for s in approved]
    path = [c.path_step(1, "Part", part_id, "APPROVED_SOURCE" if approved else None, part)] + [c.path_step(i + 2, "ApprovedSource", s["approved_source_id"], None, s) for i, s in enumerate(approved)]
    d = c.CommerceDecision(status=c.SUCCESS, decision=PART_ORIGIN, summary=f"Recorded origin of {label}: " + "; ".join(bits) + ".",
                           facts={"part_id": part_id, "manufacturer": part.get("manufacturer"), "approved_source_count": len(approved), "approved_sources": [s["source_id"] for s in approved], "data_status": part.get("data_status")},
                           reasons=["read from the part's catalogue record and its approved-source records"], warnings=([] if approved else ["no approved source is recorded for this part"]))
    return _context(engine, PART_ORIGIN, {"part_id": part_id}, d, records, evidence, path, part=part, sources=approved, catalogue=catalogue)
