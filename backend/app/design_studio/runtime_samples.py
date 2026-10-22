"""Illustrative sample records and running cases for the Studio's application preview, so an application opens looking lived in
instead of showing empty lists and zeros. Made only from the specification (field types, allowed values, links between records,
the steps of each process); nothing here is business data, the preview says so, and the launched application starts empty."""

from __future__ import annotations

import re
from collections import deque
from datetime import date, datetime, timedelta, timezone

ROWS = 4
COMPANIES = ["Van Dijk Machinery", "Nordhaven Logistics", "Brouwer Services", "Tideline Supplies"]
PEOPLE = ["Anna de Vries", "Lars Jansen", "Mila Bakker", "Tom Visser"]
SENTENCES = [
    "Requested by the customer after a routine check",
    "Reported on delivery and photographed",
    "Covered by the standard agreement",
    "Waiting for confirmation from the supplier",
]
PRODUCTS = ["Hydraulic hose 25 mm", "Filter cartridge", "Drive belt", "Bearing kit"]
UNITS = ["pcs", "kg", "box", "litre"]
MACHINES = ["Wheel loader WL-350", "Excavator EX-210", "Telehandler TH-90", "Dumper DT-45"]
PRODUCT_WORDS = ("item", "part", "product", "material", "stock", "goods", "article")
MACHINE_WORDS = ("machine", "equipment", "vehicle", "asset", "fleet")
COMPANY_WORDS = ("customer", "supplier", "carrier", "dealer", "vendor", "company", "client", "partner", "warehouse", "site")
PERSON_WORDS = ("technician", "manager", "clerk", "driver", "operator", "person", "employee", "user", "owner", "contact")


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


def _prefix(name: str) -> str:
    letters = "".join(word[0] for word in name.split() if word)[:3].upper()
    return letters if len(letters) >= 2 else name[:3].upper()


def _number(attribute, n: int, step: float):
    low = attribute.minimum if attribute.minimum is not None else 1
    high = attribute.maximum if attribute.maximum is not None else low + 40
    value = low + (n * step) % max(high - low, 1)
    return int(value) if attribute.type == "integer" else round(float(value), 1)


def _text(entity, attribute, n: int) -> str:
    label = _words(attribute.id + " " + attribute.name)
    fmt = attribute.format
    if fmt == "email":
        return f"contact{n + 1}@example.com"
    if fmt == "phone":
        return f"+31 20 555 01{n:02d}"
    if fmt == "url":
        return f"https://example.com/{n + 1}"
    if fmt == "postal_code":
        return f"10{n + 1}1 AB"
    if attribute.pattern == "digits":
        return str(100200 + n)[: attribute.max_length or 6]
    if attribute.pattern == "letters":
        return "ABCDEF"[: attribute.max_length or 6]
    if attribute.pattern == "alphanumeric":
        return "A1B2C3"[: attribute.max_length or 6]
    if attribute.key or "serial" in label or re.search(r"\b(code|number|no|ref|reference|id)\b", label):
        return f"{_prefix(entity.name)}-{1000 + n * 7 + 3}"
    entity_words = _words(entity.name)
    if re.search(r"\b(unit|uom)\b", label):
        return UNITS[n % len(UNITS)]
    if re.search(r"\b(name|title)\b", label):
        if any(word in entity_words for word in MACHINE_WORDS):
            return MACHINES[n % len(MACHINES)]
        if any(word in entity_words for word in PRODUCT_WORDS):
            return PRODUCTS[n % len(PRODUCTS)]
        if any(word in entity_words for word in PERSON_WORDS):
            return PEOPLE[n % len(PEOPLE)]
        if any(word in entity_words for word in COMPANY_WORDS):
            return COMPANIES[n % len(COMPANIES)]
        return f"{entity.name} {n + 1}"
    if re.search(r"\b(description|note|notes|reason|comment|remark|issue|problem|details?)\b", label):
        return SENTENCES[n % len(SENTENCES)]
    if re.search(r"\b(address|street)\b", label):
        return f"{12 + n * 5} Harbour Street, Rotterdam"
    if re.search(r"\b(city|town)\b", label):
        return ["Rotterdam", "Utrecht", "Antwerp", "Hamburg"][n % 4]
    if re.search(r"\b(country)\b", label):
        return ["Netherlands", "Belgium", "Germany", "France"][n % 4]
    return f"{attribute.name} {n + 1}"


def _value(entity, attribute, n: int, today: date):
    if attribute.value_source == "calculated":
        return None  # nothing computes it in a preview; an honest blank beats an invented figure
    if attribute.enum:
        return attribute.enum[n % len(attribute.enum)]
    if attribute.type == "boolean":
        return attribute.default if isinstance(attribute.default, bool) else n % 2 == 0
    if attribute.type == "date":
        return (today - timedelta(days=3 + n * 9)).isoformat()
    if attribute.type == "datetime":
        stamp = datetime.combine(today - timedelta(days=1 + n * 4), datetime.min.time(), timezone.utc)
        return (stamp + timedelta(hours=9 + n)).isoformat()
    if attribute.type == "integer":
        return n + 1 if attribute.value_source == "system_generated" else _number(attribute, n, 3)
    if attribute.type == "decimal":
        return _number(attribute, n, 17.5) if attribute.format != "percentage" else float(10 * (n + 1))
    text = _text(entity, attribute, n)
    if attribute.max_length:
        text = text[: attribute.max_length]
    return text


def _records(definition, today: date) -> dict[str, list[dict]]:
    from app.design_studio.compiler import references

    ids = {e.id: [f"sample-{e.id}-{n + 1}" for n in range(ROWS)] for e in definition.business.entities}
    rows: dict[str, list[dict]] = {}
    for entity in definition.business.entities:
        rows[entity.id] = []
        for n, row_id in enumerate(ids[entity.id]):
            data = {}
            for attribute in entity.attributes:
                value = _value(entity, attribute, n, today)
                if value is not None:
                    data[attribute.id] = value
            rows[entity.id].append({"id": row_id, "revision": 1, "data": data})
    by_id = {entity_id: {row["id"]: row for row in entity_rows} for entity_id, entity_rows in rows.items()}
    for reference in references(definition)[0]:
        for n, row in enumerate(rows.get(reference.source, [])):
            target_id = ids[reference.target][n % ROWS] if reference.target in ids else None
            if target_id is None:
                continue
            if reference.enforcement == "link":
                row["data"][reference.field] = target_id
            else:
                key = by_id[reference.target][target_id]["data"].get(reference.target_key)
                if key is not None:
                    row["data"][reference.field] = key
    return rows


def _path(workflow, start: str, target: str) -> list[dict]:
    """The hops from `start` to `target` by the shortest route."""
    previous, queue = {start: None}, deque([start])
    while queue:
        current = queue.popleft()
        for edge in workflow.transitions:
            if edge.source == current and edge.target not in previous:
                previous[edge.target] = current
                queue.append(edge.target)
    hops, node = [], target
    while node in previous and previous[node] is not None:
        hops.append({"source": previous[node], "target": node})
        node = previous[node]
    return list(reversed(hops))


def _instances(definition, rows: dict[str, list[dict]], today: date) -> list[dict]:
    entity_ids = set(rows)
    role_names = {role.id: role.name for role in definition.business.roles}
    instances = []
    for workflow in definition.workflow_definitions:
        waiting = [s for s in workflow.states if s.kind not in ("start", "branch", "end", "exception")]
        end = next((s for s in workflow.states if s.kind == "end"), None)
        exception = next((s for s in workflow.states if s.kind == "exception"), None)
        if not waiting:
            continue
        picks = [waiting[0], waiting[len(waiting) // 2], waiting[-1], exception, end]
        seen = []
        for state in picks:
            if state is not None and state not in seen:
                seen.append(state)
        for n, state in enumerate(seen[:4]):
            role = next((s.role_id for s in waiting if s.role_id), None)
            actor = "demo:" + (role_names.get(role) or "Team")
            moment = datetime.combine(today - timedelta(days=n + 1), datetime.min.time(), timezone.utc) + timedelta(hours=8)
            events = [{"action": "process.start", "actor": actor, "at": moment.isoformat(), "data": {"state": waiting[0].id, "path": []}}]
            path = _path(workflow, waiting[0].id, state.id)
            if path:
                events.append(
                    {"action": "process.advance", "actor": actor, "at": (moment + timedelta(hours=3)).isoformat(), "data": {"path": path, "outputs": {}}}
                )
            links = {
                entity_id: rows[entity_id][n % ROWS]["id"]
                for entity_id in dict.fromkeys([*state.reads_entity_ids, *state.writes_entity_ids])
                if entity_id in entity_ids
            }
            instances.append({"id": f"sample-{workflow.id}-{n + 1}", "workflow": workflow.id, "state": state.id, "links": links, "events": events})
    return instances


def sample_data(definition, today: date | None = None) -> dict:
    """{"records": {entity id: rows}, "instances": [...]}: what the preview shows before anyone has entered anything."""
    today = today or date.today()
    records = _records(definition, today)
    return {"records": records, "instances": _instances(definition, records, today)}
