"""WarrantyContext: the stable contract over the Phase 3 warranty context.

The decision is `app.lifecycle.rules.evaluate`, reached through `WarrantyContextBuilder`; this module re-evaluates nothing. It adds the common metadata, maps the outcome onto the
common statuses, gives every decision factor the record(s) it was read from, and builds the traceability evidence path.

  ELIGIBLE -> SUCCESS   NOT_ELIGIBLE -> NOT_ELIGIBLE   REQUIRES_REVIEW -> REQUIRES_REVIEW   INSUFFICIENT_DATA -> INSUFFICIENT_DATA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.commerce import contract as c
from app.lifecycle import rules
from app.lifecycle.context import WarrantyContextBuilder
from app.lifecycle.readers import LifecycleReader

STATUS_FOR = {rules.ELIGIBLE: c.SUCCESS, rules.NOT_ELIGIBLE: c.NOT_ELIGIBLE, rules.REQUIRES_REVIEW: c.REQUIRES_REVIEW, rules.INSUFFICIENT_DATA: c.INSUFFICIENT_DATA}
NEXT_ACTION = {
    rules.ELIGIBLE: "Explain that every applicable condition holds, citing the decision factors; the claim still goes through the normal approval step.",
    rules.NOT_ELIGIBLE: "Explain which condition failed and the record it was read from; do not suggest the claim can be approved.",
    rules.REQUIRES_REVIEW: "Say the claim needs a person to review it and why (the prior claim or replacement); do not decide it.",
    rules.INSUFFICIENT_DATA: "Say which facts are missing; do not assume them. Ask for the missing records or route to a person.",
}


@dataclass(kw_only=True)
class WarrantyContext(c.CommerceContext):
    machine: dict[str, Any] | None = None
    current_part: dict[str, Any] | None = None
    installation: dict[str, Any] | None = None
    dealer: dict[str, Any] | None = None
    technician: dict[str, Any] | None = None
    work_order: dict[str, Any] | None = None
    fitment: dict[str, Any] | None = None
    approved_source: dict[str, Any] | None = None
    warranty_policy: dict[str, Any] | None = None
    coverage_start: str | None = None
    coverage_end: str | None = None
    replacement_history: list[dict[str, Any]] = field(default_factory=list)
    prior_claims: list[dict[str, Any]] = field(default_factory=list)
    claim: dict[str, Any] | None = None
    decision_factors: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    reference_date: str | None = None
    traceability: dict[str, Any] | None = None


def _entity_index(f: rules.Facts) -> dict[str, str]:
    """record id -> graph entity, for every record the evaluator was given."""
    idx: dict[str, str] = {}

    def add(entity: str, rows: Any, key: str) -> None:
        for r in ([rows] if isinstance(rows, dict) else rows or []):
            if r and r.get(key):
                idx[r[key]] = entity

    add("MachineInstance", f.instance, "machine_instance_id")
    add("Installation", f.installation, "installation_id")
    add("Part", f.part, "part_id")
    add("Dealer", f.dealer, "dealer_id")
    add("Technician", f.technician, "technician_id")
    add("WorkOrder", f.work_order, "work_order_id")
    add("Fitment", f.fitment, "fitment_id")
    add("ApprovedSource", f.approved_sources, "approved_source_id")
    add("WarrantyPolicy", f.policies, "warranty_policy_id")
    add("WarrantyClaim", f.claim, "claim_id")
    add("WarrantyClaim", f.other_claims, "claim_id")
    add("Replacement", f.replacements, "replacement_id")
    return idx


def _scope(code: str, f: rules.Facts) -> tuple[str, str | None]:
    """Where to look for the source of a factor that rests on the absence of a record (no earlier claim, no fitment...): the record whose relations were searched."""
    machine = f.instance["machine_instance_id"] if f.instance else None
    part = f.part["part_id"] if f.part else (f.installation or {}).get("part_id")
    return {"NO_PRIOR_CLAIM": ("MachineInstance", machine), "NO_PRIOR_REPLACEMENT": ("MachineInstance", machine), "APPROVED_MACHINE_FITMENT": ("Part", part),
            "POLICY_FOUND": ("Part", part), "PART_INSTALLED": ("MachineInstance", machine), "COVERAGE_PERIOD_ACTIVE": ("Installation", (f.installation or {}).get("installation_id")),
            "INSTALLATION_EVIDENCED": ("Installation", (f.installation or {}).get("installation_id")), "APPROVED_PART": ("Part", part),
            "AUTHORISED_DEALER_INSTALL": ("Installation", (f.installation or {}).get("installation_id"))}.get(code, ("MachineInstance", machine))


def factor_views(decision_factors: list[dict[str, Any]], f: rules.Facts) -> list[dict[str, Any]]:
    """Every factor with its result and the record(s) it came from. A factor that rests on the absence of a record names the record that was searched, and says so."""
    idx = _entity_index(f)
    out = []
    for x in decision_factors:
        sources = [{"entity": idx.get(rid, "Record"), "id": rid} for rid in x["records"]]
        basis = "RECORDS"
        if not sources:
            entity, rid = _scope(x["code"], f)
            sources = [{"entity": entity, "id": rid}] if rid else []
            basis = "ABSENCE_OF_RECORD"
        out.append({"name": x["code"].lower(), "code": x["code"], "label": x["label"], "result": {"PASS": True, "FAIL": False}.get(x["status"]), "status": x["status"], "detail": x["detail"],
                    "on_fail": x["on_fail"], "sources": sources, "basis": basis, "evidence": x["evidence"]})
    return out


class WarrantyContextAssembler:
    """Named for what it adds to WarrantyContextBuilder: the common contract. The rules stay in app.lifecycle.rules."""

    def __init__(self, reader: LifecycleReader, as_of: date, generated_at: str) -> None:
        self.r = reader
        self.as_of = as_of
        self.generated_at = generated_at
        self._b = WarrantyContextBuilder(reader, as_of)

    def for_claim(self, claim_id: str) -> WarrantyContext:
        if self.r.claim(claim_id) is None:
            return self._not_found({"claim_id": claim_id}, f"No warranty claim {claim_id} is recorded.")
        return self._from_facts(self._b.facts_for_claim(claim_id), {"claim_id": claim_id})

    def for_part(self, machine_instance_id: str, part_id: str) -> WarrantyContext:
        inputs = {"machine_instance_id": machine_instance_id, "part_id": part_id}
        if self.r.instance(machine_instance_id) is None:
            return self._not_found(inputs, f"No machine instance {machine_instance_id} is recorded.")
        return self._from_facts(self._b.facts_for_part(machine_instance_id, part_id), inputs)

    def _not_found(self, inputs: dict[str, Any], summary: str) -> WarrantyContext:
        d = c.CommerceDecision(status=c.NOT_FOUND, decision="NOT_FOUND", summary=summary, missing=["claim_or_machine"], recommended_next_action="Ask the user to check the reference.")
        return WarrantyContext(**c.meta("WARRANTY", inputs, self.as_of.isoformat(), self.generated_at, d, [], [], []))

    def clarify(self, question: str, options: list[dict[str, Any]], inputs: dict[str, Any]) -> WarrantyContext:
        d = c.CommerceDecision(status=c.REQUIRES_CLARIFICATION, decision=c.REQUIRES_CLARIFICATION, summary=question, facts={"options": options}, missing=["claim_or_machine_and_part"],
                               recommended_next_action="Ask the user: " + question)
        return WarrantyContext(**c.meta("WARRANTY", inputs, self.as_of.isoformat(), self.generated_at, d, [], [], []))

    def _from_facts(self, facts: rules.Facts, inputs: dict[str, Any]) -> WarrantyContext:
        ctx = self._b.build(facts)  # the Phase 3 context: the decision comes from rules.evaluate and nowhere else
        factors = factor_views([x for x in ctx.to_dict()["decision_factors"]], facts)
        by = {x["code"]: x["result"] for x in factors}
        records = [c.record(idx_entity, rid, row) for idx_entity, rid, row in self._rows(facts)]
        records += [c.record("Evidence", e["evidence_id"], e) for e in facts.evidence]
        evidence = [{**c.evidence_item(f"{e['evidence_type']} for {e['entity_type']} {e['entity_id']}", "Evidence", e["evidence_id"], e), "evidence_type": e["evidence_type"],
                     "entity_type": e["entity_type"], "entity_id": e["entity_id"]} for e in sorted(facts.evidence, key=lambda e: e["evidence_id"])]
        path = self._path(facts, ctx)
        status = STATUS_FOR[ctx.outcome]
        facts_out = {"outcome": ctx.outcome, "coverage_active": by.get("COVERAGE_PERIOD_ACTIVE"), "authorized_dealer": by.get("AUTHORISED_DEALER_INSTALL"), "approved_part": by.get("APPROVED_PART"),
                     "approved_machine_fitment": by.get("APPROVED_MACHINE_FITMENT"), "installation_evidenced": by.get("INSTALLATION_EVIDENCED"), "no_prior_claim": by.get("NO_PRIOR_CLAIM"),
                     "no_prior_replacement": by.get("NO_PRIOR_REPLACEMENT"), "coverage_start": ctx.coverage_start, "coverage_end": ctx.coverage_end, "reference_date": ctx.reference_date,
                     "policy_id": (ctx.warranty_policy or {}).get("warranty_policy_id")}
        warnings = [] if ctx.outcome == rules.ELIGIBLE else [r for r in ctx.reasons if ctx.outcome == rules.REQUIRES_REVIEW]
        decision = c.CommerceDecision(status=status, decision=ctx.outcome, summary=self._summary(ctx), facts=facts_out, reasons=list(ctx.reasons), evidence=evidence, missing=list(ctx.missing),
                                      warnings=warnings, recommended_next_action=NEXT_ACTION[ctx.outcome])
        trace = self._b.traceability(facts.instance["machine_instance_id"], (facts.part or {}).get("part_id")) if facts.instance else None
        return WarrantyContext(
            **c.meta("WARRANTY", inputs, self.as_of.isoformat(), self.generated_at, decision, records, evidence, path), machine=ctx.machine, current_part=ctx.current_part, installation=ctx.installation,
            dealer=ctx.dealer, technician=ctx.technician, work_order=ctx.work_order, fitment=ctx.fitment, approved_source=ctx.approved_source, warranty_policy=ctx.warranty_policy,
            coverage_start=ctx.coverage_start, coverage_end=ctx.coverage_end, replacement_history=ctx.replacement_history, prior_claims=ctx.prior_claims, claim=ctx.claim,
            decision_factors=factors, provenance=ctx.provenance, reference_date=ctx.reference_date, traceability=trace)

    @staticmethod
    def _summary(ctx: Any) -> str:
        if ctx.outcome == rules.ELIGIBLE:
            return "Every applicable warranty condition holds on complete, evidenced facts."
        return {rules.NOT_ELIGIBLE: "Not eligible: ", rules.REQUIRES_REVIEW: "Needs review: ", rules.INSUFFICIENT_DATA: "Not enough data to decide: "}[ctx.outcome] + (ctx.reasons[0] if ctx.reasons else "")

    @staticmethod
    def _rows(f: rules.Facts) -> list[tuple[str, str, dict[str, Any]]]:
        out: list[tuple[str, str, dict[str, Any]]] = []
        for entity, row, key in (("MachineInstance", f.instance, "machine_instance_id"), ("Installation", f.installation, "installation_id"), ("Part", f.part, "part_id"), ("Dealer", f.dealer, "dealer_id"),
                                 ("Technician", f.technician, "technician_id"), ("WorkOrder", f.work_order, "work_order_id"), ("Fitment", f.fitment, "fitment_id"), ("WarrantyClaim", f.claim, "claim_id")):
            if row:
                out.append((entity, row[key], row))
        out += [("ApprovedSource", s["approved_source_id"], s) for s in f.approved_sources]
        out += [("WarrantyPolicy", p["warranty_policy_id"], p) for p in f.policies]
        out += [("WarrantyClaim", x["claim_id"], x) for x in f.other_claims]
        out += [("Replacement", x["replacement_id"], x) for x in f.replacements]
        return out

    @staticmethod
    def _path(f: rules.Facts, ctx: Any) -> list[dict[str, Any]]:
        """MachineInstance -> Installation -> WorkOrder -> Dealer -> WarrantyPolicy -> Claim -> Evidence, only the links that exist."""
        chain: list[tuple[str, str, dict[str, Any] | None, str | None]] = []
        if f.instance:
            chain.append(("MachineInstance", f.instance["machine_instance_id"], f.instance, "HAS_INSTALLATION"))
        if f.installation:
            chain.append(("Installation", f.installation["installation_id"], f.installation, "RECORDED_IN"))
        if f.work_order:
            chain.append(("WorkOrder", f.work_order["work_order_id"], f.work_order, "PERFORMED_BY_DEALER"))
        if f.dealer:
            chain.append(("Dealer", f.dealer["dealer_id"], f.dealer, "GOVERNED_BY"))
        if ctx.warranty_policy:
            chain.append(("WarrantyPolicy", ctx.warranty_policy["warranty_policy_id"], ctx.warranty_policy, "EVALUATED_FOR"))
        if f.claim:
            chain.append(("WarrantyClaim", f.claim["claim_id"], f.claim, "SUPPORTED_BY"))
        chain += [("Evidence", e["evidence_id"], e, None) for e in sorted(f.evidence, key=lambda e: e["evidence_id"])]
        steps = []
        for i, (entity, rid, row, rel) in enumerate(chain, 1):
            steps.append(c.path_step(i, entity, rid, rel if i < len(chain) else None, row))
        return steps
