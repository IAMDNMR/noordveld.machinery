"""A repeatable quality evaluation of what Design Studio builds from approved knowledge, with no language model and no network.

Each scenario adopts real packs into a blank project, then measures the result against the platform's own rules: do the requirements
reach a step, is every process connected from start to an end, is each record kept once, can every record be created by someone,
does every working role have a process, and what visual layer does the application get. WMS is one scenario of several.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.design_studio.completeness import analyze, unmaintained_reference_data
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import KnowledgeProvider, LocalKnowledgeProvider, apply_pack
from app.design_studio.templates import automatic, navigation_for

# What each scenario adopts; verified packs only, so the evaluation measures composition rather than draft knowledge.
SCENARIOS: dict[str, list[str]] = {
    "warehouse (WMS)": ["cat_warehouse_fulfilment", "cat_stock_control"],
    "procurement": ["cat_procure_to_pay", "cat_supplier_lifecycle"],
    "after-sales": ["cat_aftersales_warranty"],
    "e-commerce": ["cat_ecommerce_order_to_delivery"],
    "transport tracking": ["cat_shipment_tracking"],
    "multi-domain (warehouse + procurement + transport)": [
        "cat_warehouse_fulfilment",
        "cat_stock_control",
        "cat_procure_to_pay",
        "cat_shipment_tracking",
    ],
}


@dataclass
class Result:
    name: str
    metrics: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def reachable(workflow) -> tuple[set[str], set[str]]:
    """Steps reachable from the start, and steps from which an end can be reached."""
    forward = {state.id for state in workflow.states if state.kind == "start"}
    backward = {state.id for state in workflow.states if state.kind == "end"}
    for seen, source, target in ((forward, "source", "target"), (backward, "target", "source")):
        grew = True
        while grew:
            grew = False
            for edge in workflow.transitions:
                if getattr(edge, source) in seen and getattr(edge, target) not in seen:
                    seen.add(getattr(edge, target))
                    grew = True
    return forward, backward


def duplicate_records(definition) -> list[str]:
    names: dict[str, int] = {}
    for entity in definition.business.entities:
        key = " ".join(entity.name.lower().split())
        names[key] = names.get(key, 0) + 1
    return sorted(name for name, count in names.items() if count > 1)


def evaluate(name: str, definition) -> Result:
    result = Result(name)
    business = definition.business
    steps = [(w, s) for w in definition.workflow_definitions for s in w.states if s.kind not in ("start", "end")]
    active = [r for r in business.requirements if r.status in ("draft", "agreed")]
    served = {rid for _, s in steps for rid in s.requirement_ids}
    uncovered = [r.id for r in active if r.id not in served]
    broken = []
    for workflow in definition.workflow_definitions:
        forward, backward = reachable(workflow)
        broken += [f"{workflow.id}/{s.id}" for s in workflow.states if s.id not in forward or s.id not in backward]
    working = {s.role_id for _, s in steps if s.role_id}
    idle = [r.id for r in business.roles if r.id not in working and not r.permissions]
    duplicates = duplicate_records(definition)
    unmaintained = [e.id for e in unmaintained_reference_data(definition)]
    findings = analyze(definition)["findings"]
    errors = [f["code"] for f in findings if f["severity"] == "error" and f["code"] != "PROCESS_NOT_APPROVED"]
    layer = automatic(definition)
    result.metrics = {
        "processes": len(definition.workflow_definitions),
        "steps": len(steps),
        "records": len(business.entities),
        "roles": len(business.roles),
        "requirements": len(active),
        "requirement coverage": f"{len(active) - len(uncovered)}/{len(active)}",
        "disconnected steps": len(broken),
        "duplicate records": len(duplicates),
        "records nobody maintains": len(unmaintained),
        "roles with no work": len(idle),
        "blocking findings": len(errors),
        "visual layer": f"{layer.id} - {navigation_for(definition, layer.nav_style)}" if layer else "none",
    }
    for label, values in (
        ("requirements no step serves", uncovered),
        ("steps not connected start to end", broken),
        ("records defined twice", duplicates),
        ("records nobody can create", unmaintained),
        ("blocking findings", errors),
    ):
        if values:
            result.failures.append(f"{label}: {', '.join(values[:4])}{' …' if len(values) > 4 else ''}")
    if layer is None:
        result.failures.append("no visual layer was chosen")
    return result


def build(pack_ids: list[str], provider: KnowledgeProvider | None = None):
    provider = provider or LocalKnowledgeProvider()
    definition = blank_definition()
    for pack_id in pack_ids:
        definition, _ = apply_pack(definition, pack_id, provider)
    return definition


def run(scenarios: dict[str, list[str]] | None = None) -> list[Result]:
    results = []
    for name, packs in (scenarios or SCENARIOS).items():
        started = time.perf_counter()
        result = evaluate(name, build(packs))
        result.metrics["seconds"] = round(time.perf_counter() - started, 2)
        results.append(result)
    return results


def with_evaluation_approval(definition):
    """The same definition with both approvals recorded, so the generator will produce the application. An evaluation fixture only:
    it is made in memory for a scratch definition and approves nothing in any real project."""
    from app.design_studio.approval import digest
    from app.schemas.application_definition import ApprovalRecord

    approved = definition.model_copy(deep=True)
    approved.revision = max(1, approved.revision)  # an approval covers a saved revision
    approved.approvals = [
        ApprovalRecord(
            scope=scope,
            revision=1,
            content_sha256=digest(approved, scope),
            approved_by="evaluation_fixture",
            approved_at="2026-10-22T00:00:00Z",
            comment="Evaluation of generated output only; not a real approval",
        )
        for scope in ("process", "design")
    ]
    return approved
