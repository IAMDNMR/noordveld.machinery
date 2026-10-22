"""Deterministic mockup starter, templates and inert ZIP export."""

from __future__ import annotations

from html import escape
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas.design_studio import ScreenSpec

TEMPLATES = (
    (
        "supplier-onboarding",
        "Supplier onboarding",
        "Supplier",
        ["Company name", "Contact email", "Country"],
    ),
    ("spare-parts", "Spare-parts data entry", "Part", ["Part number", "Description", "Quantity"]),
    (
        "import-mapping",
        "CSV/Excel import mapping",
        "Import",
        ["Source column", "Target field", "Mapping notes"],
    ),
    (
        "machine-specification",
        "Machine specification",
        "Machine",
        ["Model", "Capacity", "Manufacturer"],
    ),
    ("service-request", "Service request", "Request", ["Machine ID", "Issue", "Contact email"]),
    ("inventory-table", "Inventory table", "Inventory", ["Search", "Warehouse"]),
)


def requirement_plan(message: str) -> dict:
    """Transparent starter analysis, not an AI model response."""
    cleaned = re.sub(r"\s+", " ", message).strip()
    lower = cleaned.lower()
    matches = [
        item[1]
        for item in TEMPLATES
        if any(token in lower for token in item[0].split("-") if len(token) > 3)
    ]
    questions = []
    if not any(word in lower for word in ("user", "role", "staff", "admin", "customer")):
        questions.append("Who will use this screen, and which actions should each role see?")
    if not any(word in lower for word in ("required", "validate", "rule")):
        questions.append("Which fields are required, and what validation rules apply?")
    if not any(word in lower for word in ("approve", "review", "exception", "reject")):
        questions.append("Does this process need approval or an exception path?")
    return {
        "mode": "deterministic_starter",
        "summary": cleaned[:500],
        "suggested_templates": matches,
        "questions": questions,
    }


def template(template_id: str) -> ScreenSpec | None:
    found = next((item for item in TEMPLATES if item[0] == template_id), None)
    if not found:
        return None
    _, name, section, labels = found
    fields = [
        {
            "id": re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_"),
            "type": "email"
            if "email" in label.lower()
            else "number"
            if label == "Quantity"
            else "text",
            "label": label,
        }
        for label in labels
    ]
    tables = (
        [
            {
                "id": "inventory",
                "title": "Inventory",
                "columns": ["Part", "Warehouse", "Quantity"],
                "searchable": True,
                "filters": ["Warehouse"],
            }
        ]
        if template_id == "inventory-table"
        else []
    )
    return ScreenSpec.model_validate(
        {
            "name": name,
            "description": "Safe mockup starter. No live business data.",
            "sections": [{"id": "main", "title": section, "fields": fields}],
            "tables": tables,
        }
    )


def starter_from_request(message: str, current: ScreenSpec | None) -> ScreenSpec:
    """Explicit non-AI starter. Never imply that a model inferred business requirements."""
    if current:
        return current.model_copy(deep=True)
    words = re.sub(r"\s+", " ", message).strip()
    name = words[:100] or "New screen"
    lower = words.lower()
    match = next(
        (
            item
            for item in TEMPLATES
            if any(token in lower for token in item[0].split("-") if len(token) > 3)
        ),
        None,
    )
    if match:
        return template(match[0])  # type: ignore[return-value]
    return ScreenSpec.model_validate(
        {
            "name": name,
            "description": "Starter mockup — review fields and validation before use.",
            "sections": [
                {
                    "id": "main",
                    "title": "Details",
                    "fields": [{"id": "name", "type": "text", "label": "Name"}],
                }
            ],
        }
    )


def export_zip(spec: ScreenSpec) -> bytes:
    """Fixed allowlisted archive entries; no project files, scripts or network actions."""
    validated = ScreenSpec.model_validate(spec.model_dump())
    html = [
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>',
        escape(validated.name),
        "</title><main><p>MOCKUP ONLY — no business actions</p><h1>",
        escape(validated.name),
        "</h1>",
    ]
    for section in validated.sections:
        html.extend(["<section><h2>", escape(section.title), "</h2>"])
        for field in section.fields:
            html.extend(["<p>", escape(field.label), "</p>"])
        html.append("</section>")
    html.append("</main></html>")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("definition.json", validated.model_dump_json(indent=2))
        archive.writestr("index.html", "".join(html))
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "generator": "noordveld-mockup-1",
                    "artifacts": ["definition.json", "index.html"],
                },
                sort_keys=True,
            ),
        )
    return output.getvalue()
