"""Explicit repair of previously overmatched blueprint domains.

The caller reviews/applies this as a new revision. No project or global knowledge
is changed automatically. Custom items survive unless they exactly repeat an
out-of-scope blueprint item. Original revisions remain available for recovery.
"""

import re

from app.design_studio.discovery import blank_definition
from app.design_studio.guided import stage_digest
from app.design_studio.knowledge.provider import GROUPS, adoption_order, apply_pack
from app.schemas.application_definition import ApplicationDefinition, StudioFlow


def normalized(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def repair_scope(definition, roots, provider):
    desired = blank_definition()
    for root in roots:
        desired, _ = apply_pack(desired, root, provider)
    ordered, _ = adoption_order(roots, provider)
    allowed = {pack.id for pack in ordered}
    known = {pack.id: pack for pack in provider.packs()}
    excluded = {
        link.pack_id
        for link in definition.business.knowledge
        if link.pack_id in known and link.pack_id not in allowed
    }
    raw = definition.model_dump(mode="json")
    removed = {}
    for group in GROUPS:
        desired_ids = {item.id for item in getattr(desired.business, group)}
        excluded_text = {
            normalized(
                getattr(item, "statement", None)
                or getattr(item, "description", None)
                or getattr(item, "question", "")
            )
            for pack_id in excluded
            for item in getattr(known[pack_id].business, group)
        } - {""}
        allowed_text = {
            normalized(
                getattr(item, "statement", None)
                or getattr(item, "description", None)
                or getattr(item, "question", "")
            )
            for item in getattr(desired.business, group)
        }
        kept = []
        for item in raw["business"][group]:
            origin = (item.get("origin") or {}).get("pack_id")
            text = normalized(
                item.get("statement") or item.get("description") or item.get("question") or ""
            )
            if item["id"] not in desired_ids and (
                origin in excluded or (not origin and text in excluded_text - allowed_text)
            ):
                removed.setdefault(group, []).append(item["id"])
            else:
                kept.append(item)
        raw["business"][group] = kept
    foreign_workflows = {w.id for pack_id in excluded for w in known[pack_id].workflows}
    raw["workflow_definitions"] = [
        w for w in raw["workflow_definitions"] if w["id"] not in foreign_workflows
    ]
    valid_workflows = {w["id"] for w in raw["workflow_definitions"]}
    raw["workflows"] = [w for w in raw["workflows"] if w in valid_workflows]
    raw["screens"] = [
        screen
        for screen in raw["screens"]
        if (
            not (screen.get("trace") or {}).get("workflow_id")
            or screen["trace"]["workflow_id"] in valid_workflows
        )
        and not (screen["title"] == "New screen" and not screen["components"])
    ]
    valid_screens = {screen["id"] for screen in raw["screens"]}
    raw["navigation"] = [item for item in raw["navigation"] if item["screen_id"] in valid_screens]
    raw["business"]["knowledge"] = [
        link for link in raw["business"]["knowledge"] if link["pack_id"] not in excluded
    ]
    candidate = ApplicationDefinition.model_validate(raw)
    for root in roots:
        candidate, _ = apply_pack(candidate, root, provider)
    # Scope changed materially: the process and all later stages require review.
    # The user-authorized scope repair itself preserves the brief/knowledge reviews.
    reviewed = [
        key
        for key in ("brief", "knowledge")
        if definition.studio_flow and key in definition.studio_flow.reviewed
    ]
    if definition.studio_flow:
        candidate.studio_flow = StudioFlow(
            reviewed=reviewed,
            reviewed_digests={key: stage_digest(candidate, key) for key in reviewed},
        )
    return candidate, {
        "removed_packs": sorted(excluded),
        "removed_items": removed,
        "removed_workflows": sorted(foreign_workflows),
    }
