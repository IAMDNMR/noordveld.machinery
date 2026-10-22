"""Three-way reference upgrades: preserve local edits, reject ambiguous changes."""

from copy import deepcopy
from app.design_studio.knowledge.provider import GROUPS, PackUnavailable, apply_pack
from app.schemas.application_definition import ApplicationDefinition

MISSING = object()


class UpgradeConflict(ValueError):
    pass


def merge(base, local, incoming, path=""):
    if local == base:
        return deepcopy(incoming) if incoming is not MISSING else MISSING
    if incoming == base or local == incoming:
        return deepcopy(local) if local is not MISSING else MISSING
    if all(isinstance(value, dict) for value in (base, local, incoming)):
        result = {}
        for key in sorted(set(base) | set(local) | set(incoming)):
            value = merge(
                base.get(key, MISSING),
                local.get(key, MISSING),
                incoming.get(key, MISSING),
                f"{path}/{key}",
            )
            if value is not MISSING:
                result[key] = value
        return result
    if all(isinstance(value, list) for value in (base, local, incoming)) and all(
        all(isinstance(item, dict) and "id" in item for item in value)
        and len({item["id"] for item in value}) == len(value)
        for value in (base, local, incoming)
    ):
        indexes = [{item["id"]: item for item in value} for value in (base, local, incoming)]
        order = list(
            dict.fromkeys([item["id"] for item in local] + [item["id"] for item in incoming])
        )
        result = []
        for key in order:
            value = merge(*(index.get(key, MISSING) for index in indexes), path=f"{path}/{key}")
            if value is not MISSING:
                result.append(value)
        # Local deletion against an upstream modification must not be ignored.
        for key in set(indexes[0]) - set(order):
            merge(*(index.get(key, MISSING) for index in indexes), path=f"{path}/{key}")
        return result
    raise UpgradeConflict(
        f"Both the project and reference changed {path}. Review that conflict before updating."
    )


def update_reference(definition, pack_id, provider):
    link = next((link for link in definition.business.knowledge if link.pack_id == pack_id), None)
    if link is None:
        raise UpgradeConflict("Adopt this reference before updating it.")
    incoming = provider.pack(pack_id)
    if incoming.version == link.pack_version:
        raise UpgradeConflict("The project already uses the latest version of this reference.")
    reader = getattr(provider, "pack_version", None)
    if not reader:
        raise PackUnavailable("The original reference version must be available for a safe update.")
    original = reader(pack_id, link.pack_version)
    # Adoption brings in newly required items/dependencies, but never overwrites existing items.
    adopted, _ = apply_pack(definition, pack_id, provider)
    raw = adopted.model_dump(mode="json")
    for group in GROUPS:
        base = {item.id: item.model_dump(mode="json") for item in getattr(original.business, group)}
        target = {
            item.id: item.model_dump(mode="json") for item in getattr(incoming.business, group)
        }
        for index, current in enumerate(raw["business"][group]):
            ident = current["id"]
            if ident not in base or (current.get("origin") or {}).get("pack_id") != pack_id:
                continue
            if ident not in target:
                raise UpgradeConflict(
                    f"Reference removed {ident}; review its project dependencies before removing it."
                )
            origin = current["origin"]
            local = {k: v for k, v in current.items() if k != "origin"}
            old = {k: v for k, v in base[ident].items() if k != "origin"}
            new = {k: v for k, v in target[ident].items() if k != "origin"}
            merged = merge(old, local, new, f"{group}/{ident}")
            merged["origin"] = {**origin, "pack_version": incoming.version}
            raw["business"][group][index] = merged
    base_flows = {w.id: w.model_dump(mode="json") for w in original.workflows}
    new_flows = {w.id: w.model_dump(mode="json") for w in incoming.workflows}
    for index, workflow in enumerate(raw["workflow_definitions"]):
        ident = workflow["id"]
        if ident in base_flows:
            if ident not in new_flows:
                raise UpgradeConflict(
                    f"Reference removed process {ident}; review it before updating."
                )
            raw["workflow_definitions"][index] = merge(
                base_flows[ident], workflow, new_flows[ident], f"process/{ident}"
            )
    for entry in raw["business"]["knowledge"]:
        if entry["pack_id"] == pack_id:
            entry["pack_version"] = incoming.version
    return ApplicationDefinition.model_validate(raw)
