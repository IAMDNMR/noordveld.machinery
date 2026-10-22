"""Record validation derived from attribute metadata: the authoritative server-side counterpart of the generated
`validation.ts`. Both read the same rule data (`entity_rules`), and the generated test suite runs the same cases.

Only fixed, linear-time pattern classes and formats are used; nothing from the specification becomes a regular
expression or code.
"""

from __future__ import annotations

from datetime import date as _date, datetime as _datetime, timezone as _timezone
import re
from typing import Any

from app.schemas.application_definition import BusinessEntity, EntityAttribute

# Kept identical to the regular expressions in the generated validation.ts template (see codegen.VALIDATION_SOURCE).
FORMATS = {
    "email": r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$",
    "phone": r"^\+?[0-9][0-9 ()./-]{5,29}$",
    "url": r"^https?://[^\s]+$",
    "postal_code": r"^[A-Za-z0-9][A-Za-z0-9 -]{1,9}$",
    "currency_amount": r"^-?[0-9]+(\.[0-9]{1,2})?$",
    "percentage": r"^[0-9]+(\.[0-9]+)?$",
}
PATTERNS = {"digits": r"^[0-9]+$", "letters": r"^[A-Za-z]+$", "alphanumeric": r"^[A-Za-z0-9]+$"}
DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
DATETIME = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$"

WALL_CLOCK = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?$"  # a datetime missing only its offset

# Time convention, the same in every generated application:
#   date      a calendar date, YYYY-MM-DD. It has no time and no time zone and is never converted.
#   datetime  an instant. It must carry an explicit offset (Z or +hh:mm); a wall-clock time without one is ambiguous and refused.
#             It is stored in one canonical form, UTC with a Z suffix, and clients show it in the viewer's own time zone.


def _calendar_date(value: str) -> _date | None:
    try:
        return _date.fromisoformat(value) if re.fullmatch(DATE, value) else None
    except ValueError:
        return None


def _instant(value: str) -> _datetime | None:
    if not re.fullmatch(DATETIME, value):
        return None
    try:
        return _datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def canonical_instant(value: str) -> str:
    """A valid datetime as UTC: 2026-10-21T08:00:00Z (milliseconds kept when present)."""
    moment = _instant(value).astimezone(_timezone.utc)
    return moment.isoformat(timespec="milliseconds" if moment.microsecond else "seconds").replace(
        "+00:00", "Z"
    )


def normalize_record(rules: list[dict], record: dict[str, Any]) -> dict[str, Any]:
    """The record as it is stored: datetimes in canonical UTC. Call only after `validate_record` found no errors."""
    kinds = {rule["id"]: rule["type"] for rule in rules}
    return {
        key: canonical_instant(value)
        if kinds.get(key) == "datetime" and isinstance(value, str) and value
        else value
        for key, value in record.items()
    }


def attribute_rule(attribute: EntityAttribute) -> dict:
    return {
        "id": attribute.id,
        "name": attribute.name,
        "type": attribute.type,
        "required": attribute.required,
        "allow_unknown": attribute.allow_unknown,
        "system_managed": attribute.system_managed or not attribute.writable,
        "value_source": attribute.value_source,
        "format": attribute.format,
        "minimum": attribute.minimum,
        "maximum": attribute.maximum,
        "min_length": attribute.min_length,
        "max_length": attribute.max_length,
        "pattern": attribute.pattern,
        "enum": list(attribute.enum),
    }


def entity_rules(entity: BusinessEntity) -> list[dict]:
    return [attribute_rule(attribute) for attribute in entity.attributes]


def validate_record(rules: list[dict], record: dict[str, Any], mode: str = "create") -> list[dict]:
    """Errors for a record a person submits. `mode` is "create" or "update"; system-managed fields are never accepted."""
    errors: list[dict] = []
    known = {rule["id"]: rule for rule in rules}
    for key in sorted(record):
        if key not in known:
            errors.append(
                {
                    "field": key,
                    "code": "unknown_field",
                    "message": f"{key} is not part of this record.",
                }
            )
        elif known[key]["system_managed"]:
            errors.append(
                {
                    "field": key,
                    "code": "system_managed",
                    "message": f"{known[key]['name']} is set by the system and cannot be submitted.",
                }
            )
    for rule in rules:
        if rule["system_managed"]:
            continue
        field, name = rule["id"], rule["name"]
        value = record.get(field)
        if value is None or value == "":
            if rule["required"] and mode == "create" and not rule["allow_unknown"]:
                errors.append(
                    {"field": field, "code": "required", "message": f"{name} is required."}
                )
            continue
        kind = rule["type"]
        if kind == "boolean":
            if not isinstance(value, bool):
                errors.append(
                    {"field": field, "code": "type", "message": f"{name} must be true or false."}
                )
            continue
        if kind in ("integer", "decimal"):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (kind == "integer" and not float(value).is_integer())
            ):
                errors.append(
                    {
                        "field": field,
                        "code": "type",
                        "message": f"{name} must be {'a whole number' if kind == 'integer' else 'a number'}.",
                    }
                )
                continue
            if rule["minimum"] is not None and value < rule["minimum"]:
                errors.append(
                    {
                        "field": field,
                        "code": "minimum",
                        "message": f"{name} is at least {rule['minimum']:g}.",
                    }
                )
            if rule["maximum"] is not None and value > rule["maximum"]:
                errors.append(
                    {
                        "field": field,
                        "code": "maximum",
                        "message": f"{name} is at most {rule['maximum']:g}.",
                    }
                )
            continue
        if not isinstance(value, str):
            errors.append({"field": field, "code": "type", "message": f"{name} must be text."})
            continue
        if kind == "date" and _calendar_date(value) is None:
            errors.append(
                {
                    "field": field,
                    "code": "format",
                    "message": f"{name} must be a real calendar date written YYYY-MM-DD, for example 2026-10-21.",
                }
            )
        if kind == "datetime" and _instant(value) is None:
            wall_clock = re.fullmatch(WALL_CLOCK, value)
            errors.append(
                {
                    "field": field,
                    "code": "format",
                    "message": (
                        f"{name} needs a time zone, for example 2026-10-21T08:00:00Z or 2026-10-21T10:00:00+02:00."
                        if wall_clock
                        else f"{name} must be a real date and time with a time zone, for example 2026-10-21T08:00:00Z."
                    ),
                }
            )
        if kind != "string":
            continue
        if rule["min_length"] is not None and len(value) < rule["min_length"]:
            errors.append(
                {
                    "field": field,
                    "code": "min_length",
                    "message": f"{name} has at least {rule['min_length']} characters.",
                }
            )
        if rule["max_length"] is not None and len(value) > rule["max_length"]:
            errors.append(
                {
                    "field": field,
                    "code": "max_length",
                    "message": f"{name} has at most {rule['max_length']} characters.",
                }
            )
        if rule["format"] and not re.fullmatch(FORMATS[rule["format"]], value):
            errors.append(
                {
                    "field": field,
                    "code": "format",
                    "message": f"{name} must be a valid {rule['format'].replace('_', ' ')}.",
                }
            )
        if rule["pattern"] and not re.fullmatch(PATTERNS[rule["pattern"]], value):
            errors.append(
                {
                    "field": field,
                    "code": "pattern",
                    "message": f"{name} may contain {rule['pattern']} only.",
                }
            )
        if rule["enum"] and value not in rule["enum"]:
            errors.append(
                {
                    "field": field,
                    "code": "enum",
                    "message": f"{name} must be one of: {', '.join(rule['enum'])}.",
                }
            )
    return errors


def sample_value(rule: dict) -> Any:
    """A deterministic valid value for a rule, used by the generated tests."""
    if rule["enum"]:
        return rule["enum"][0]
    kind = rule["type"]
    if kind == "boolean":
        return True
    if kind in ("integer", "decimal"):
        if rule["minimum"] is not None:
            return (
                int(rule["minimum"])
                if kind == "integer" and float(rule["minimum"]).is_integer()
                else rule["minimum"]
            )
        if rule["maximum"] is not None:
            return (
                int(rule["maximum"])
                if kind == "integer" and float(rule["maximum"]).is_integer()
                else rule["maximum"]
            )
        return 1
    if kind == "date":
        return "2026-01-01"
    if kind == "datetime":
        return "2026-01-01T00:00:00Z"
    base = {
        "email": "person@example.invalid",
        "phone": "+31 20 123 4567",
        "url": "https://example.invalid",
        "postal_code": "1234 AB",
        "currency_amount": "12.50",
        "percentage": "5",
    }.get(rule["format"] or "")
    if base is None:
        base = {"digits": "123", "letters": "abc", "alphanumeric": "abc123"}.get(
            rule["pattern"] or "", "Example"
        )
    filler = {"digits": "1", "letters": "a", "alphanumeric": "a"}.get(rule["pattern"] or "", "x")
    if rule["min_length"] is not None and len(base) < rule["min_length"]:
        base += filler * (rule["min_length"] - len(base))
    if rule["max_length"] is not None:
        base = base[: rule["max_length"]]
    return base


def sample_record(rules: list[dict]) -> dict[str, Any]:
    return {rule["id"]: sample_value(rule) for rule in rules if not rule["system_managed"]}
