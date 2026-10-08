"""WarrantyContext, the traceability chain and the part lifecycle view: pure data built from a reader, no language model, no UI.

The context is what a later layer is allowed to EXPLAIN. The decision in it comes from `rules.evaluate`, never from prose.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.lifecycle import rules
from app.lifecycle.readers import LifecycleReader

_MISSING = None


@dataclass
class WarrantyContext:
    machine: dict[str, Any] | None
    current_part: dict[str, Any] | None
    installation: dict[str, Any] | None
    dealer: dict[str, Any] | None
    technician: dict[str, Any] | None
    work_order: dict[str, Any] | None
    fitment: dict[str, Any] | None
    approved_source: dict[str, Any] | None
    warranty_policy: dict[str, Any] | None
    coverage_start: str | None
    coverage_end: str | None
    replacement_history: list[dict[str, Any]]
    prior_claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    decision_factors: list[dict[str, Any]]
    provenance: dict[str, Any]
    claim: dict[str, Any] | None = None
    outcome: str = rules.INSUFFICIENT_DATA
    reasons: list[str] = field(default_factory=list)
    reference_date: str | None = None
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _prov(*records: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [{k: r.get(k) for k in ("data_status", "source_type", "source_record_id")} for r in records if r]


class WarrantyContextBuilder:
    def __init__(self, reader: LifecycleReader, as_of: date | None = None) -> None:
        self.r = reader
        self.as_of = as_of or datetime.now(timezone.utc).date()

    # ── facts ────────────────────────────────────────────────────────────────────────────────────
    def facts_for_claim(self, claim_id: str) -> rules.Facts:
        claim = self.r.claim(claim_id)
        if claim is None:
            return rules.Facts(reference_date=self.as_of)
        inst = self.r.installation(claim["installation_id"]) if claim.get("installation_id") else None
        if inst is None:  # a claim with no installation falls back to the part's installation on that machine, if exactly one exists
            candidates = [i for i in self.r.installations(claim["machine_instance_id"]) if i["part_id"] == claim["part_id"]]
            inst = candidates[0] if len(candidates) == 1 else None
        failure = date.fromisoformat(claim["failure_date"]) if claim.get("failure_date") else self.as_of
        return self._facts(claim["machine_instance_id"], claim["part_id"], inst, claim, failure)

    def facts_for_part(self, machine_instance_id: str, part_id: str) -> rules.Facts:
        installs = [i for i in self.r.installations(machine_instance_id) if i["part_id"] == part_id]
        current = rules.current_installations(installs)
        inst = current[-1] if current else (installs[-1] if installs else None)
        return self._facts(machine_instance_id, part_id, inst, None, self.as_of)

    def _facts(self, mid: str, part_id: str, inst: dict[str, Any] | None, claim: dict[str, Any] | None, ref: date) -> rules.Facts:
        instance = self.r.instance(mid)
        part = self.r.part(part_id)
        dealer = self.r.dealer(inst["dealer_id"]) if inst and inst.get("dealer_id") else None
        tech = self.r.technician(inst["technician_id"]) if inst and inst.get("technician_id") else None
        wo = self.r.work_order(inst["work_order_id"]) if inst and inst.get("work_order_id") else None
        fit = self.r.fitment(instance["machine_id"], part_id) if instance else None
        claims = [c for c in self.r.claims(mid) if c["part_id"] == part_id and (not claim or c["claim_id"] != claim["claim_id"])]
        evidence: list[dict[str, Any]] = []
        for etype, eid in (("INSTALLATION", inst and inst["installation_id"]), ("WORK_ORDER", wo and wo["work_order_id"]), ("DEALER", dealer and dealer["dealer_id"]),
                           ("TECHNICIAN", tech and tech["technician_id"]), ("PART", part_id if part else None), ("WARRANTY_CLAIM", claim and claim["claim_id"])):
            if eid:
                evidence.extend(self.r.evidence(etype, eid))
        return rules.Facts(instance=instance, installation=inst, part=part, dealer=dealer, technician=tech, work_order=wo, fitment=fit, approved_sources=self.r.approved_sources(part_id),
                           policies=self.r.policies(part_id), claim=claim, other_claims=claims, replacements=self.r.replacements(mid), evidence=evidence, reference_date=ref)

    # ── context ──────────────────────────────────────────────────────────────────────────────────
    def build(self, facts: rules.Facts) -> WarrantyContext:
        d = rules.evaluate(facts)
        inst, instance = facts.installation, facts.instance
        policy = next((p for p in facts.policies if p["warranty_policy_id"] == d.policy_id), None)
        approved = next((s for s in facts.approved_sources if s.get("approval_status") == rules.APPROVED), None)
        current = rules.current_installations([i for i in (self.r.installations(instance["machine_instance_id"]) if instance else []) if facts.part and i["part_id"] == facts.part["part_id"]])
        missing = [name for name, value in (("machine", instance), ("installation", inst), ("part", facts.part), ("dealer", facts.dealer), ("technician", facts.technician),
                                            ("work_order", facts.work_order), ("fitment", facts.fitment), ("approved_source", approved), ("warranty_policy", policy)) if value is None]
        return WarrantyContext(
            machine=instance, current_part=facts.part if current else None, installation=inst, dealer=facts.dealer, technician=facts.technician, work_order=facts.work_order,
            fitment=facts.fitment, approved_source=approved, warranty_policy=policy, coverage_start=d.coverage_start, coverage_end=d.coverage_end,
            replacement_history=facts.replacements, prior_claims=facts.other_claims, evidence=facts.evidence,
            decision_factors=[{"code": f.code, "label": f.label, "status": f.status, "detail": f.detail, "on_fail": f.on_fail, "records": f.records, "evidence": f.evidence} for f in d.factors],
            provenance={"records": _prov(instance, inst, facts.part, facts.dealer, facts.technician, facts.work_order, facts.fitment, approved, policy, facts.claim),
                        "evidence": [e["evidence_id"] for e in facts.evidence]},
            claim=facts.claim, outcome=d.outcome, reasons=d.reasons, reference_date=d.reference_date, missing=missing)

    def for_claim(self, claim_id: str) -> WarrantyContext:
        return self.build(self.facts_for_claim(claim_id))

    def for_part(self, machine_instance_id: str, part_id: str) -> WarrantyContext:
        return self.build(self.facts_for_part(machine_instance_id, part_id))

    # ── traceability ─────────────────────────────────────────────────────────────────────────────
    def traceability(self, machine_instance_id: str, part_id: str | None = None) -> dict[str, Any]:
        """What is installed now, what was before, who installed it, when it was replaced and which claim is linked: every row names the record it came from."""
        installs = self.r.installations(machine_instance_id)
        if part_id:
            installs = [i for i in installs if i["part_id"] == part_id]
        reps = self.r.replacements(machine_instance_id)
        claims = self.r.claims(machine_instance_id)
        removed_by = {r["removed_installation_id"]: r for r in reps}
        replaced_by = {r["new_installation_id"]: r for r in reps}

        def row(i: dict[str, Any]) -> dict[str, Any]:
            tech, dealer = (self.r.technician(i["technician_id"]) if i.get("technician_id") else None), self.r.dealer(i["dealer_id"]) if i.get("dealer_id") else None
            part = self.r.part(i["part_id"])
            rep_out, rep_in = removed_by.get(i["installation_id"]), replaced_by.get(i["installation_id"])
            return {"installation_id": i["installation_id"], "part_id": i["part_id"], "part_number": part and part["part_number"], "part_name": part and part["name"],
                    "serial": i.get("part_serial_number"), "installed_on": i["installation_date"], "removed_on": i.get("removal_date"), "state": "CURRENT" if i in rules.current_installations(installs) else "HISTORICAL",
                    "installed_by": tech and {"technician_id": tech["technician_id"], "name": tech["name"], "specialization": tech["specialization"]},
                    "installed_at": dealer and {"dealer_id": dealer["dealer_id"], "name": dealer["name"], "authorized_status": dealer["authorized_status"]},
                    "work_order_id": i.get("work_order_id"), "replaced_by_event": rep_out and rep_out["replacement_id"], "replaced_on": rep_out and rep_out["replacement_date"],
                    "replaces_installation": rep_in and rep_in["removed_installation_id"], "validation_status": i.get("validation_status"), "validation_issues": i.get("validation_issues") or [],
                    "claims": [c["claim_id"] for c in claims if c.get("installation_id") == i["installation_id"]]}

        rows = [row(i) for i in installs]
        def pick(record: dict[str, Any], *keys: str) -> dict[str, Any]:
            return {k: record.get(k) for k in keys}

        return {"machine_instance_id": machine_instance_id, "installed_now": [r for r in rows if r["state"] == "CURRENT"], "installed_before": [r for r in rows if r["state"] == "HISTORICAL"],
                "replacements": [pick(r, "replacement_id", "removed_installation_id", "new_installation_id", "removed_part_id", "installed_part_id", "replacement_date", "reason", "work_order_id")
                                 for r in reps if not part_id or r["removed_part_id"] == part_id or r["installed_part_id"] == part_id],
                "claims": [pick(c, "claim_id", "part_id", "installation_id", "failure_date", "claim_date", "status", "decision", "dealer_id") for c in claims if not part_id or c["part_id"] == part_id]}

    def part_lifecycle(self, installation_id: str) -> dict[str, Any]:
        """Installed -> Serviced -> Inspected -> Removed -> Replaced -> Current/Historical, each stage dated from a record. A stage with no record is absent, not assumed."""
        inst = self.r.installation(installation_id)
        if inst is None:
            return {"installation_id": installation_id, "stages": []}
        ev = self.r.evidence("INSTALLATION", installation_id)
        stages: list[dict[str, Any]] = [{"stage": "INSTALLED", "date": inst["installation_date"], "record": installation_id}]
        for e in ev:
            if e["evidence_type"] == "SERVICE_REPORT":
                stages.append({"stage": "SERVICED", "date": e["created_at"], "record": e["evidence_id"]})
            elif e["evidence_type"] == "INSPECTION_RECORD":
                stages.append({"stage": "INSPECTED", "date": e["created_at"], "record": e["evidence_id"]})
        if inst.get("removal_date"):
            stages.append({"stage": "REMOVED", "date": inst["removal_date"], "record": installation_id})
            rep = next((r for r in self.r.replacements(inst["machine_instance_id"]) if r["removed_installation_id"] == installation_id), None)
            if rep:
                stages.append({"stage": "REPLACED", "date": rep["replacement_date"], "record": rep["replacement_id"]})
        order = {"INSTALLED": 0, "SERVICED": 1, "INSPECTED": 2, "REMOVED": 3, "REPLACED": 4}
        stages.sort(key=lambda s: (s["date"] or "", order[s["stage"]]))
        return {"installation_id": installation_id, "part_id": inst["part_id"], "machine_instance_id": inst["machine_instance_id"],
                "state": "CURRENT" if rules.current_installations([inst]) else "HISTORICAL", "stages": stages}
