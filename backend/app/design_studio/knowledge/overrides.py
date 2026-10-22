"""Company overrides of shared knowledge: applied explicitly, field by field, with the reason on record.

A company layer reuses shared definitions and may change or extend them. Each change names the item and says why; an unknown item or
a field that does not exist is an error, never ignored. The result is validated by the same models as any project.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

GROUPS = (
    "requirements",
    "roles",
    "entities",
    "rules",
    "exceptions",
    "decisions",
    "integrations",
    "terms",
)


class OverrideError(ValueError):
    pass


def apply_overrides(business: dict[str, Any], overrides: list) -> dict[str, Any]:
    """A copy of `business` (a dict as produced by model_dump) with every override applied."""
    result = deepcopy(business)
    for override in overrides:
        found = next(
            (item for group in GROUPS for item in result[group] if item["id"] == override.item_id),
            None,
        )
        if found is None:
            raise OverrideError(
                f"Override {override.item_id}: no such item in the shared knowledge this company reuses"
            )
        for field, value in override.patch.items():
            if field in ("id", "origin"):
                raise OverrideError(f"Override {override.item_id}: {field} cannot be overridden")
            if field not in found:
                raise OverrideError(f"Override {override.item_id}: the item has no field {field}")
            found[field] = deepcopy(value)
        if override.add_attributes:
            if "attributes" not in found:
                raise OverrideError(f"Override {override.item_id}: only entities have attributes")
            taken = {attribute["id"] for attribute in found["attributes"]}
            for attribute in override.add_attributes:
                if attribute.get("id") in taken:
                    raise OverrideError(
                        f"Override {override.item_id}: attribute {attribute.get('id')} already exists; patch it instead"
                    )
                found["attributes"].append(deepcopy(attribute))
        if override.add_permissions:
            if "permissions" not in found:
                raise OverrideError(f"Override {override.item_id}: only roles have permissions")
            found["permissions"] = list(
                dict.fromkeys([*found["permissions"], *override.add_permissions])
            )
    return result
