"""Domain-independent readiness checks for reusable knowledge; no model calls or mutations."""

from collections import defaultdict
from hashlib import sha256
import re

QUALITY_VERSION = "2"


def assess(pack):
    findings = []

    def add(code, item, detail):
        findings.append({"code": code, "item": item, "detail": detail})

    rules = {r.id: r for r in pack.business.rules}
    used = {r for w in pack.workflows for s in w.states for r in s.rule_ids}
    used |= {t.condition.field for w in pack.workflows for t in w.transitions if t.condition.field}
    equivalent = defaultdict(list)
    for rule in pack.business.rules:
        equivalent[re.sub(r"\W+", " ", rule.description.casefold()).strip()].append(rule.id)
        if rule.execution is None:
            add("RULE_NOT_EXECUTABLE", rule.id, "Rule has no executable binding.")
        if rule.id not in used:
            add(
                "RULE_NOT_LINKED",
                rule.id,
                "No workflow in this pack applies the rule; dependent packs may apply shared rules.",
            )
    for ids in equivalent.values():
        if len(ids) > 1:
            add("DUPLICATE_RULE", ids[0], ", ".join(ids))
    tasks = [
        s for w in pack.workflows for s in w.states if s.kind not in ("start", "end", "branch")
    ]
    for step in tasks:
        if step.writes_entity_ids and step.input_fields is None:
            add("TASK_FIELDS_UNSCOPED", step.id, "This task falls back to the whole entity form.")
        if step.preconditions or step.postconditions:
            add("PROSE_CONDITION", step.id, "Prose conditions cannot execute in the runtime.")
        if not step.role_id or not step.permission:
            add("TASK_ACCESS_INCOMPLETE", step.id, "Task needs a responsible role and permission.")
    for integration in pack.business.integrations:
        if not integration.entity_ids:
            add(
                "INTEGRATION_SCHEMA_MISSING",
                integration.id,
                "No entity schema is declared for record exchange.",
            )
    reference_findings = findings if pack.usage == "source_reference" else []
    if pack.usage == "source_reference":
        findings = []
    payload = pack.model_dump_json()
    return {
        "quality_version": QUALITY_VERSION,
        "pack_id": pack.id,
        "pack_version": pack.version,
        "content_sha256": sha256(payload.encode()).hexdigest(),
        "usage": pack.usage,
        "reference_findings": reference_findings,
        "configuration_required": [
            {
                "integration_id": i.id,
                "status": "not_configured",
                "note": "Signed record exchange is generated; configure the customer system, field mapping and service role. Binary documents and provider-specific delivery require an adapter.",
            }
            for i in pack.business.integrations
        ]
        if pack.usage == "blueprint"
        else [],
        "status": "source_reference"
        if pack.usage == "source_reference"
        else ("needs_work" if findings else "structurally_ready"),
        "note": "Structural assessment only; not business approval or production certification.",
        "counts": {
            "entities": len(pack.business.entities),
            "roles": len(pack.business.roles),
            "rules": len(rules),
            "executable_rules": sum(r.execution is not None for r in rules.values()),
            "tasks": len(tasks),
        },
        "findings": findings,
    }


def catalog_report(provider):
    reports = [assess(pack) for pack in sorted(provider.packs(), key=lambda item: item.id)]
    return {
        "quality_version": QUALITY_VERSION,
        "packs": reports,
        "summary": {
            "packs": len(reports),
            "findings": sum(len(r["findings"]) for r in reports),
            "source_reference_packs": sum(r["usage"] == "source_reference" for r in reports),
            "reference_findings": sum(len(r["reference_findings"]) for r in reports),
            "configuration_required": sum(len(r["configuration_required"]) for r in reports),
        },
    }
