"""Industry/region discovery backed by a versioned catalog, independent of model calls."""

from copy import deepcopy
import json
from pathlib import Path
import re


def validate_catalog(document):
    if not isinstance(document, dict) or not document.get("version"):
        raise ValueError("System context requires a version")
    for group in ("industries", "regions", "systems"):
        rows = document.get(group)
        if (
            not isinstance(rows, list)
            or not rows
            or any(not isinstance(r, dict) or not r.get("id") or not r.get("name") for r in rows)
        ):
            raise ValueError(f"Invalid context catalog {group}")
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError(f"Duplicate context {group} ID")
    industries = {r["id"] for r in document["industries"]}
    regions = {r["id"] for r in document["regions"]}
    for system in document["systems"]:
        if set(system["industry_ids"]) - industries or set(system["regions"]) - regions:
            raise ValueError("Unknown industry or region in system context")
        if (
            not system.get("blueprint_id")
            or not system.get("blueprint_version")
            or not system.get("processes")
            or not system.get("source")
        ):
            raise ValueError("A system profile needs a versioned blueprint, process and provenance")
    return deepcopy(document)


def load_catalog():
    return validate_catalog(
        json.loads(Path(__file__).with_name("system_context.json").read_text(encoding="utf-8"))
    )


def catalog_for(provider, version=None):
    reader = getattr(provider, "context_catalog", None)
    return reader(version) if reader else None


def matching_systems(catalog, definition):
    if not catalog:
        return []
    brief = definition.business.brief
    text = " ".join((brief.goal, brief.purpose, definition.metadata.name)).lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    ranked = []
    for system in catalog["systems"]:
        score = sum(1 for k in system["keywords"] if (k in words if " " not in k else k in text))
        if brief.domain_id and system["domain_id"] == brief.domain_id:
            score += 100
        if score:
            ranked.append((score, system))
    return [deepcopy(s) for _, s in sorted(ranked, key=lambda item: (-item[0], item[1]["id"]))[:3]]


def discovery_context(provider, definition):
    intake = definition.business.brief.intake
    catalog = catalog_for(provider, intake.catalog_version if intake else None)
    if not catalog:
        return None
    selected = (
        intake.model_dump(mode="json")
        if intake
        else {
            "region": None,
            "industry_id": None,
            "skipped": [],
            "catalog_version": catalog["version"],
        }
    )
    questions = []
    if not selected["region"] and "region" not in selected["skipped"]:
        questions.append(
            {
                "id": "region",
                "text": "Where will the business operate?",
                "optional": True,
                "options": [{"id": r["id"], "name": r["name"]} for r in catalog["regions"]],
            }
        )
    if not selected["industry_id"] and "industry" not in selected["skipped"]:
        questions.append(
            {
                "id": "industry",
                "text": "Which industry should the draft fit?",
                "optional": True,
                "options": catalog["industries"],
            }
        )
    region = next((r for r in catalog["regions"] if r["id"] == selected["region"]), None)
    return {
        "catalog_version": catalog["version"],
        "selected": selected,
        "questions": questions[:2],
        "systems": matching_systems(catalog, definition),
        "regional_guidance": region,
        "coverage": {
            "systems": len(catalog["systems"]),
            "industries": len(catalog["industries"]),
            "regions": len(catalog["regions"]),
        },
        "note": catalog.get("note", ""),
    }


def region_in_text(text):
    eu = bool(re.search(r"\b(eu|european union|netherlands|germany|france)\b", text, re.I))
    india = bool(re.search(r"\b(india|indian)\b", text, re.I))
    return ("eu" if eu else "india") if eu != india else None
