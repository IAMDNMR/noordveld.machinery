"""Catalog governance: is the set of packs coherent, and would a proposed pack fit in without duplicating or colliding with what exists?

Findings are plain data (severity, code, message, items) so the Studio can list them and tests can assert on them.
error: the catalog is wrong (a broken reference, an impossible combination). warning: worth a person's attention (two packs that
cannot be adopted together, a concept defined twice). info: context.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.design_studio.knowledge.models import BUSINESS_GROUPS, ReferencePack
from app.design_studio.knowledge.provider import KnowledgeProvider


def _closure(
    pack_id: str, by_id: dict[str, ReferencePack], seen: set[str] | None = None
) -> set[str]:
    seen = seen if seen is not None else set()
    for dep in by_id[pack_id].depends_on if pack_id in by_id else []:
        if dep not in seen:
            seen.add(dep)
            _closure(dep, by_id, seen)
    return seen


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _ids(pack: ReferencePack) -> dict[str, str]:
    return {
        item.id: group for group in BUSINESS_GROUPS for item in getattr(pack.business, group)
    } | {w.id: "workflow" for w in pack.workflows}


def _finding(severity: str, code: str, message: str, items: list[str]) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "items": items}


def compare_pack(
    pack: ReferencePack, others: list[ReferencePack], by_id: dict[str, ReferencePack]
) -> list[dict]:
    """How one pack relates to the others: id collisions with packs it could be adopted alongside, and concepts that look defined twice."""
    findings = []
    own = _ids(pack)
    related = _closure(pack.id, by_id)
    for other in others:
        if other.id == pack.id:
            continue
        linked = other.id in related or pack.id in _closure(other.id, by_id)
        shared = sorted(set(own) & set(_ids(other)))
        if shared and not linked:
            findings.append(
                _finding(
                    "warning",
                    "ID_COLLISION",
                    f"{pack.id} and {other.id} define the same ids, so they cannot be adopted into one project together.",
                    shared[:12],
                )
            )
        if linked:
            continue
        mine = {_norm(e.name): e for e in pack.business.entities}
        for entity in other.business.entities:
            twin = mine.get(_norm(entity.name))
            if twin is not None:
                findings.append(
                    _finding(
                        "warning",
                        "NEAR_DUPLICATE_ENTITY",
                        f"“{twin.name}” is defined in {pack.id} and in {other.id}. Consider reusing one definition through a dependency.",
                        [twin.id, entity.id],
                    )
                )
    return findings


def validate_catalog(provider: KnowledgeProvider) -> list[dict]:
    packs = provider.packs()
    by_id = {pack.id: pack for pack in packs}
    domains = {domain.id: domain for domain in provider.domains()}
    findings: list[dict] = []
    for pack in packs:
        if pack.domain_id and pack.domain_id not in domains:
            findings.append(
                _finding(
                    "error",
                    "PACK_DOMAIN_UNKNOWN",
                    f"{pack.id} belongs to domain {pack.domain_id}, which is not registered.",
                    [pack.id],
                )
            )
        for dep in pack.depends_on:
            if by_id[dep].status in ("draft", "in_review") and pack.status == "approved":
                findings.append(
                    _finding(
                        "warning",
                        "DEPENDS_ON_UNREVIEWED",
                        f"{pack.id} is approved but depends on {dep}, which is {by_id[dep].status}.",
                        [pack.id, dep],
                    )
                )
            if by_id[dep].status == "deprecated":
                findings.append(
                    _finding(
                        "error",
                        "DEPENDS_ON_DEPRECATED",
                        f"{pack.id} depends on the deprecated pack {dep}.",
                        [pack.id, dep],
                    )
                )
        if pack.layer == "business" and not pack.workflows and pack.domain_id:
            findings.append(
                _finding(
                    "info",
                    "DOMAIN_PACK_WITHOUT_PROCESS",
                    f"{pack.id} has no process, so it can only supply a data model.",
                    [pack.id],
                )
            )
        findings += compare_pack(pack, packs, by_id)
    seen_pairs: set[tuple] = set()
    unique = []
    for item in findings:  # a pair is reported once, whichever pack was compared first
        key = (item["code"], tuple(sorted(item["items"])))
        if key not in seen_pairs:
            seen_pairs.add(key)
            unique.append(item)
    findings = unique
    covered = {pack.domain_id for pack in packs if pack.domain_id}
    for domain_id in sorted(set(domains) - covered):
        findings.append(
            _finding(
                "info",
                "DOMAIN_WITHOUT_PACK",
                f"Domain {domain_id} is registered but no pack covers it yet.",
                [domain_id],
            )
        )
    owners: dict[str, list[str]] = {}
    for domain in domains.values():
        for keyword in domain.keywords:
            owners.setdefault(keyword, []).append(domain.id)
    for keyword, domain_ids in sorted(owners.items()):
        if len(domain_ids) > 1:
            findings.append(
                _finding(
                    "info",
                    "KEYWORD_OVERLAP",
                    f"“{keyword}” identifies several domains: {', '.join(sorted(domain_ids))}.",
                    sorted(domain_ids),
                )
            )
    capabilities = {item.id: item for item in getattr(provider, "capabilities", lambda: [])()}
    for capability in capabilities.values():
        if capability.provided_by != "runtime" and capability.provided_by not in by_id:
            findings.append(
                _finding(
                    "error",
                    "CAPABILITY_PROVIDER_UNKNOWN",
                    f"Capability {capability.id} is provided by {capability.provided_by}, which does not exist.",
                    [capability.id],
                )
            )
    used = {c for pack in packs for c in pack.uses_capabilities}
    for capability_id in sorted(set(capabilities) - used):
        findings.append(
            _finding(
                "info",
                "CAPABILITY_UNUSED",
                f"No pack declares that it uses {capability_id}.",
                [capability_id],
            )
        )
    return findings


def validate_candidate(document: dict, provider: KnowledgeProvider) -> dict:
    """Would this proposed pack be accepted? Checks the document against the models together with its dependencies, then compares it with
    the catalog for id collisions and duplicate concepts. Nothing is stored."""
    packs = {pack.id: pack for pack in provider.packs()}
    try:
        candidate = ReferencePack.model_validate(document, context={"dependencies": packs})
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": [
                {"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
                for item in exc.errors()[:20]
            ],
            "findings": [],
        }
    except ValueError as exc:
        return {"valid": False, "errors": [{"path": "", "message": str(exc)}], "findings": []}
    findings = []
    missing = [dep for dep in candidate.depends_on if dep not in packs]
    if missing:
        return {
            "valid": False,
            "errors": [{"path": "depends_on", "message": f"Unknown pack {missing[0]}"}],
            "findings": [],
        }
    if candidate.id in packs:
        existing = packs[candidate.id]
        findings.append(
            _finding(
                "info" if existing.version != candidate.version else "error",
                "VERSION_EXISTS" if existing.version == candidate.version else "NEW_VERSION",
                f"{candidate.id} {candidate.version} already exists."
                if existing.version == candidate.version
                else f"New version {candidate.version} of {candidate.id} (current {existing.version}).",
                [candidate.id],
            )
        )
    by_id = dict(packs) | {candidate.id: candidate}
    findings += compare_pack(candidate, [p for p in packs.values() if p.id != candidate.id], by_id)
    return {
        "valid": not any(f["severity"] == "error" for f in findings),
        "errors": [],
        "findings": findings,
    }
