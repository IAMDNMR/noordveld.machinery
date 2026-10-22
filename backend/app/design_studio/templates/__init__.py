"""Versioned application templates and the recommendation that matches a project to them."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from app.design_studio.templates.models import Template
from app.schemas.application_definition import ApplicationDefinition

LIBRARY = Path(__file__).with_name("library")
WORD = re.compile(r"[a-z][a-z-]+")


@lru_cache(maxsize=1)
def templates() -> tuple[Template, ...]:
    """Every template in the library, validated; a broken file stops the server rather than showing a half template."""
    found = [Template.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted(LIBRARY.glob("*.json"))]
    if len({item.id for item in found}) != len(found):
        raise ValueError("Two templates share an id")
    return tuple(found)


def template(template_id: str) -> Template | None:
    return next((item for item in templates() if item.id == template_id), None)


def automatic(definition: ApplicationDefinition) -> Template | None:
    """The visual layer for a project, chosen from its blueprint: the person's own choice when there is one, otherwise the closest
    template by domain, entity roles and requirement wording. It only supplies look, density and navigation style; which screens exist
    always follows the specification, so a template can never limit what an application does."""
    if definition.template:
        return template(definition.template.template_id)
    ranked = recommend(definition, limit=1)
    return template(ranked[0]["template"]["id"]) if ranked else None


# A top bar or tab bar holds a handful of entries (the menu also carries home, tasks, reports and records); an application with many processes needs a side menu whatever the template prefers.
COMPACT_NAVIGATION = {"topbar", "bottom_tabs"}
MAX_COMPACT_ENTRIES = 3


def navigation_for(definition: ApplicationDefinition, preferred: str) -> str:
    return "sidebar" if preferred in COMPACT_NAVIGATION and len(definition.workflow_definitions) > MAX_COMPACT_ENTRIES else preferred


def visual_references(definition: ApplicationDefinition) -> list[dict]:
    """Compose visual vocabulary from compatible sources, without importing business policy,
    sample data, coverage scores or a template's fixed page inventory into the application.
    """
    domain = definition.business.brief.domain_id
    names = [_words(entity.name) for entity in definition.business.entities]
    result = []
    for item in templates():
        roles = {
            role.id for role in item.entity_roles
            if any(_has(words, match) for words in names for match in role.matches)
        }
        if domain not in item.domain_ids and not roles:
            continue
        patterns = [
            {"layout": page.layout, "purpose": page.purpose,
             "components": list(dict.fromkeys(component.type for component in page.components))}
            for page in item.pages
            if any(component.role in roles for component in page.components)
        ]
        if patterns:
            result.append({"source": item.id, "version": item.version, "patterns": patterns})
    return result


def _words(text: str) -> set[str]:
    words = set(WORD.findall(text.lower()))
    return words | {word[:-1] for word in words if word.endswith("s") and len(word) > 3}


def _has(words: set[str], phrase: str) -> bool:
    return all(part in words for part in _words(phrase)) if phrase else False


def recommend(definition: ApplicationDefinition, limit: int = 3) -> list[dict]:
    """The closest templates for a project, each with why it matches, how the project's records map to it and which
    requirements it supports, can be configured for, or does not cover."""
    business = definition.business
    requirements = [item for item in business.requirements if item.statement.strip()]
    text = " ".join([business.brief.goal, business.brief.problem, *(item.statement for item in requirements), *(e.name for e in business.entities)])
    words = _words(text)
    results = []
    for item in templates():
        reasons, score = [], 0.0
        if business.brief.domain_id and business.brief.domain_id in item.domain_ids:
            score += 6
            reasons.append("Built for this domain")
        hits = sorted({keyword for keyword in item.keywords if _has(words, keyword)})
        score += len(hits)
        if hits:
            reasons.append("Matches " + ", ".join(hits[:6]))
        mapping = []
        for role in item.entity_roles:
            entity = next((e for e in business.entities if any(_has(_words(e.name), match) for match in role.matches)), None)
            if entity:
                mapping.append({"role": role.id, "label": role.label, "entity_id": entity.id, "entity": entity.name})
                score += 1.5
        coverage = []
        own = {keyword for m in item.modules for keyword in m.keywords} | set(item.keywords)
        for requirement in requirements:
            req_words = _words(requirement.statement)
            module_hits = {m.id: sum(_has(req_words, keyword) for keyword in m.keywords) for m in item.modules}
            module = max(item.modules, key=lambda m: module_hits[m.id]) if any(module_hits.values()) else None
            # One shared word is weak evidence when another template owns the requirement's real topic ("payroll for drivers").
            foreign = any(
                _has(req_words, keyword) and keyword not in own
                for other in templates() if other.id != item.id for m in other.modules for keyword in m.keywords
            )
            if module and module_hits[module.id] == 1 and foreign:
                coverage.append({"requirement_id": requirement.id, "statement": requirement.statement, "status": "unsupported", "module": None, "note": "Another template covers this."})
            elif module:
                coverage.append({"requirement_id": requirement.id, "statement": requirement.statement, "status": module.status, "module": module.name, "note": module.note})
            elif any(_has(req_words, keyword) for keyword in item.keywords):
                coverage.append({"requirement_id": requirement.id, "statement": requirement.statement, "status": "configurable", "module": None, "note": ""})
            else:
                coverage.append({"requirement_id": requirement.id, "statement": requirement.statement, "status": "unsupported", "module": None, "note": ""})
        covered = sum(entry["status"] in ("supported", "configurable") for entry in coverage)
        if requirements:
            score += 4 * covered / len(requirements)
        results.append({"template": summary(item), "score": round(score, 2), "reasons": reasons, "entity_mapping": mapping, "coverage": coverage})
    results.sort(key=lambda entry: entry["score"], reverse=True)
    best = results[0]["score"] if results else 0
    for entry in results:
        entry["fit"] = "strong" if entry["score"] >= max(8, best * 0.8) else "partial" if entry["score"] >= best * 0.45 else "weak"
    return [entry for entry in results[:limit] if entry["score"] > 0]


def summary(item: Template) -> dict:
    """What a gallery card needs; the full definition (pages, components, sample) is fetched when a template is opened."""
    return {
        "id": item.id,
        "version": item.version,
        "name": item.name,
        "category": item.category,
        "summary": item.summary,
        "status": item.status,
        "app_type": item.app_type,
        "users": item.users,
        "theme": item.theme.model_dump(),
        "nav_style": item.nav_style,
        "pages": [{"id": page.id, "title": page.title, "icon": page.icon, "layout": page.layout} for page in item.pages],
        "modules": [module.model_dump() for module in item.modules],
        "limitations": item.limitations,
    }
