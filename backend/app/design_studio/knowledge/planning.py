"""Requirements to knowledge: which domains, capabilities and packs a request needs, and what is still unknown. Deterministic and traceable.

No model is involved. Every choice names the words that caused it, so the Studio can show why a pack was proposed, and a person can
override it. Company-specific knowledge (a pack that carries a `company`) is considered only when the request names that company:
generic knowledge is the default, so one company's definitions never leak into another's design.
"""

from __future__ import annotations

import re

from app.design_studio.knowledge.models import ReferencePack
from app.design_studio.knowledge.provider import KnowledgeProvider, adoption_order

# These describe actors or common application features, not an additional business
# domain. In particular an employee placing a purchase order does not request HR
# leave management or an e-commerce checkout.
CROSS_CUTTING_WORDS = frozenset(
    {
        "employee",
        "employees",
        "manager",
        "managers",
        "approval",
        "approvals",
        "order",
        "orders",
        "request",
        "requests",
        "task",
        "tasks",
        "tracking",
        "management",
        "workflow",
        "process",
        "business",
        "application",
        "system",
    }
)


def names_company(pack: ReferencePack, text: str) -> bool:
    if pack.company is None:
        return False
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return pack.company.id.lower() in words or pack.company.name.split()[0].lower() in words


def eligible(pack: ReferencePack, text: str) -> bool:
    """A pack that may be proposed for this request: released for use, and either general or about a company the request names."""
    return (
        pack.usage == "blueprint"
        and pack.layer in ("business", "company")
        and pack.verified
        and (pack.company is None or names_company(pack, text))
    )


def reference_domains(primary: str | None, matches: list[dict]) -> list[str]:
    """The domains whose verified knowledge a project may use: its own domain first, then every other matched domain with packs that
    covers part of the request on its own words (a WMS also needs stock control), by the same test plan_application uses."""
    domains = [primary] if primary else []
    for m in matches:
        if not m["pack_ids"] or m["domain_id"] in domains:
            continue
        if not domains or (
            m["score"] >= 2 and any(word not in CROSS_CUTTING_WORDS for word in m["matched_keywords"])
        ):
            domains.append(m["domain_id"])
    return domains


def plan_application(text: str, provider: KnowledgeProvider) -> dict:
    """The knowledge plan for a request: domains (with the words that matched), the packs to adopt in order, the capabilities they use and
    how far the generator provides each, and the questions only the business can answer."""
    from app.design_studio.knowledge.provider import identify_domains

    matches = identify_domains(text, provider)
    with_packs = [m for m in matches if m["pack_ids"]]
    scoped = [
        m
        for m in with_packs
        if any(provider.pack(pack_id).company is not None for pack_id in m["pack_ids"])
    ]
    if scoped:  # the request names a company that has its own knowledge: that wins where it covers the same ground as generic knowledge
        covered = {
            word
            for m in scoped
            for domain in provider.domains()
            if domain.id == m["domain_id"]
            for word in domain.keywords
        }
        with_packs = scoped + [
            m
            for m in with_packs
            if m not in scoped and any(word not in covered for word in m["matched_keywords"])
        ]
    chosen: list[dict] = []
    if with_packs:
        chosen = [
            m
            for m in with_packs
            if m is with_packs[0]
            or (
                m["score"] >= 2
                and any(word not in CROSS_CUTTING_WORDS for word in m["matched_keywords"])
            )
        ]
    roots: list[str] = []
    for match in chosen:
        for pack_id in match["pack_ids"]:
            if pack_id not in roots and not roots_overlap(provider.pack(pack_id), roots, provider):
                roots.append(pack_id)
    ordered, full = adoption_order(roots, provider) if roots else ([], set())
    registry = {item.id: item for item in getattr(provider, "capabilities", lambda: [])()}
    used = sorted(
        {capability for pack in ordered if pack.id in full for capability in pack.uses_capabilities}
    )
    capabilities = [
        {"id": c, "name": registry[c].name, "level": registry[c].level, "note": registry[c].note}
        for c in used
        if c in registry
    ]
    questions = []
    for pack in ordered:
        if pack.id not in full:
            continue
        for decision in pack.business.decisions:
            if decision.status == "open":
                questions.append(
                    {
                        "kind": "decision",
                        "pack_id": pack.id,
                        "id": decision.id,
                        "text": decision.question,
                    }
                )
    for capability in capabilities:
        if capability["level"] != "implemented":
            questions.append(
                {
                    "kind": "capability_limit",
                    "pack_id": None,
                    "id": capability["id"],
                    "text": f"{capability['name']} is {capability['level']} in generated applications: {capability['note']}",
                }
            )
    skipped = [
        {"domain_id": m["domain_id"], "reason": "no reference knowledge covers this domain yet"}
        for m in matches
        if not m["pack_ids"] and m["score"] >= 2
    ]
    return {
        "domains": [
            {
                "domain_id": m["domain_id"],
                "name": m["name"],
                "score": m["score"],
                "matched": m["matched_keywords"],
                "packs": m["pack_ids"],
            }
            for m in chosen
        ],
        "packs": [pack.id for pack in ordered],
        "adopt": roots,
        "full_content": sorted(full),
        "capabilities": capabilities,
        "questions": questions,
        "uncovered": skipped,
        "trace": [f"{m['name']}: matched {', '.join(m['matched_keywords'])}" for m in chosen],
    }


def roots_overlap(pack: ReferencePack, roots: list[str], provider: KnowledgeProvider) -> bool:
    """A pack already brought in completely by a root adds nothing as a root of its own."""
    if not roots:
        return False
    _, full = adoption_order(roots, provider)
    return pack.id in full
