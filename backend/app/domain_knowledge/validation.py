"""Judgement-level checks of a structurally valid pack: possible duplicates, ambiguous terms, unverified knowledge.

Possible duplicates are only ever suggested for review. Nothing is merged because two names look alike.
"""

from __future__ import annotations

import re

from app.domain_knowledge.models import DomainPack

SEVERITY = {"error": 0, "warning": 1, "info": 2}


def normalize(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).lower())
    return " ".join(word[:-1] if word.endswith("s") and len(word) > 3 else word for word in words)


def analyze(pack: DomainPack) -> dict:
    findings: list[dict] = []

    def add(code: str, severity: str, items: list[str], message: str):
        findings.append(
            {
                "id": f"{code}:{'+'.join(items)}",
                "code": code,
                "severity": severity,
                "items": items,
                "message": message,
            }
        )

    by_name: dict[str, list[str]] = {}
    for entity in pack.entities:
        by_name.setdefault(normalize(entity.canonical_name), []).append(entity.id)
    for name, ids in sorted(by_name.items()):
        if len(ids) > 1:
            add(
                "DUPLICATE_CANDIDATE",
                "warning",
                sorted(ids),
                f"Entities {', '.join(sorted(ids))} have the same normalized name '{name}'. Review; they are not merged.",
            )
    terms: dict[tuple[str | None, str], list[str]] = {}
    for concept in pack.concepts:
        terms.setdefault((concept.domain_id, normalize(concept.canonical_name)), []).append(
            concept.id
        )
        for synonym in concept.synonyms:
            terms.setdefault(
                (synonym.domain_id or concept.domain_id, normalize(synonym.term)), []
            ).append(concept.id)
    for (domain, term), ids in sorted(terms.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
        unique = sorted(set(ids))
        if len(unique) > 1:
            add(
                "TERM_AMBIGUOUS",
                "warning",
                unique,
                f"'{term}' names more than one concept in {domain}: {', '.join(unique)}. Choose explicitly when it is used.",
            )
    related = {rel.source_id for rel in pack.relationships} | {
        rel.target_id for rel in pack.relationships
    }
    for entity in pack.entities:
        if not entity.natural_keys:
            add("ENTITY_NO_KEY", "warning", [entity.id], f"Entity {entity.id} has no natural key.")
        if entity.id not in related:
            add("ENTITY_ISOLATED", "info", [entity.id], f"Entity {entity.id} has no relationships.")
    for rule in pack.rules:
        if rule.status == "assumption":
            add(
                "RULE_ASSUMPTION",
                "warning",
                [rule.id],
                f"Rule {rule.id} is an unconfirmed assumption ({rule.provenance.reference}).",
            )
    for decision in pack.decisions:
        if decision.status == "open":
            add(
                "DECISION_OPEN",
                "warning",
                [decision.id],
                f"Open business decision: {decision.question}",
            )
    review = sorted(
        item.id
        for _, item in pack.items()
        if getattr(item, "provenance", None) is not None
        and item.provenance.verification == "needs_review"
    )
    if review:
        add(
            "NEEDS_REVIEW",
            "info",
            [str(len(review))],
            f"{len(review)} item(s) are derived and need business review, e.g. {', '.join(review[:5])}.",
        )
    entities = {entity.id: entity for entity in pack.entities}
    for entity in pack.entities:
        keys = {attr.id: attr for attr in entity.attributes}
        for key in entity.natural_keys:
            if not keys[key].required or not keys[key].unique:
                add(
                    "KEY_NOT_ENFORCEABLE",
                    "error",
                    [f"{entity.id}.{key}"],
                    f"Natural key {entity.id}.{key} must be required and unique.",
                )
    for rel in pack.relationships:
        if (
            rel.required
            and rel.cardinality in ("one_to_many", "many_to_many")
            and rel.source_id in entities
            and rel.target_id in entities
        ):
            add(
                "REQUIRED_COLLECTION",
                "warning",
                [rel.id],
                f"{rel.id} requires at least one {rel.target_id}; record creation must supply it.",
            )
    findings.sort(key=lambda item: (SEVERITY[item["severity"]], item["id"]))
    counts = {
        severity: sum(1 for item in findings if item["severity"] == severity)
        for severity in SEVERITY
    }
    provenance: dict[str, int] = {}
    for _, item in pack.items():
        kind = getattr(item, "provenance", None)
        if kind is not None:
            provenance[kind.kind] = provenance.get(kind.kind, 0) + 1
    inferred = sorted(
        {item.id for _, item in pack.items() if item.provenance.verification == "needs_review"}
        | {
            f"{entity.id}.{attr.id}"
            for entity in pack.entities
            for attr in entity.attributes
            if attr.provenance and attr.provenance.verification == "needs_review"
        }
    )
    synthetic = sorted(item.id for _, item in pack.items() if item.provenance.kind == "synthetic")
    report = {
        "blocking": [item for item in findings if item["severity"] == "error"],
        "warnings": [
            item
            for item in findings
            if item["severity"] == "warning"
            and item["code"] not in ("DECISION_OPEN", "RULE_ASSUMPTION")
        ],
        "inferred": {"count": len(inferred), "items": inferred},
        "assumptions": sorted(rule.id for rule in pack.rules if rule.status == "assumption"),
        "synthetic": {"count": len(synthetic), "items": synthetic},
        "unresolved_decisions": [
            {"id": item.id, "question": item.question, "affects": item.affects}
            for item in pack.decisions
            if item.status == "open"
        ],
    }
    return {
        "findings": findings,
        "counts": counts,
        "provenance": dict(sorted(provenance.items())),
        "report": report,
        "activatable": not report["blocking"],
    }
