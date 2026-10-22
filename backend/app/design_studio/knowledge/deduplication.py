"""Explicit reviewed duplicate reconciliation. No semantic match is guessed here."""



def reconcile(raw, kind, keep_id, duplicate_id):
    groups = {"rule": "rules", "exception": "exceptions", "requirement": "requirements"}
    group = groups[kind]
    items = raw["business"][group]
    keep = next((item for item in items if item["id"] == keep_id), None)
    duplicate = next((item for item in items if item["id"] == duplicate_id), None)
    if keep is None or duplicate is None or keep is duplicate:
        raise ValueError("Choose two different existing items of the same kind")
    if duplicate.get("origin") and not keep.get("origin"):
        raise ValueError("Keep the sourced item so its knowledge provenance is retained")
    if (
        kind == "rule"
        and duplicate.get("execution")
        and duplicate.get("execution") != keep.get("execution")
    ):
        raise ValueError("Different executable policies cannot be merged as duplicates")
    if (
        kind == "exception"
        and duplicate.get("resolution")
        and (duplicate["resolution"], duplicate.get("resolution_state_id"))
        != (keep.get("resolution"), keep.get("resolution_state_id"))
    ):
        raise ValueError("Different exception recovery paths must be reviewed independently")
    if kind == "rule" and set(duplicate.get("outcomes", [])) != set(keep.get("outcomes", [])):
        if any(
            t["condition"].get("field") == duplicate_id
            for w in raw["workflow_definitions"]
            for t in w["transitions"]
        ):
            raise ValueError(
                "Rule outcomes differ and a process branches on them; update those routes explicitly first"
            )
    if kind == "requirement":
        existing = {item["id"] for item in keep["acceptance_criteria"]}
        keep["acceptance_criteria"].extend(
            item for item in duplicate["acceptance_criteria"] if item["id"] not in existing
        )
        priorities = ["must", "should", "could", "wont"]
        keep["priority"] = min((keep["priority"], duplicate["priority"]), key=priorities.index)
    raw["business"][group] = [item for item in items if item["id"] != duplicate_id]
    ref_keys = {
        "rule_ids",
        "exception_ids",
        "requirement_ids",
        "rule_id",
        "exception_id",
        "outputs",
        "affects",
        "field",
    }

    def rewire(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ref_keys:
                    if isinstance(child, list) and all(isinstance(item, str) for item in child):
                        value[key] = list(
                            dict.fromkeys(
                                keep_id if item == duplicate_id else item for item in child
                            )
                        )
                    elif child == duplicate_id:
                        value[key] = keep_id
                rewire(value[key])
        elif isinstance(value, list):
            for child in value:
                rewire(child)

    rewire(raw)


def _words(text):
    import re

    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _same_record(first, second):
    """Two sourced entities describe one real-world record when they carry the same name and share at least one field with the same
    type. Matching names alone is not enough (a sales order and a purchase order are both 'Order'): a field in common is the evidence."""
    if _words(first["name"]) != _words(second["name"]):
        return False
    types = {a["id"]: a["type"] for a in first["attributes"]}
    return any(a["id"] in types and types[a["id"]] == a["type"] for a in second["attributes"])


def merge_entities(raw, keep_id, duplicate_id):
    """Fold one entity into another: union of fields, every relationship and process step re-pointed, nothing else touched."""
    entities = raw["business"]["entities"]
    keep = next(e for e in entities if e["id"] == keep_id)
    duplicate = next(e for e in entities if e["id"] == duplicate_id)
    have = {a["id"]: a for a in keep["attributes"]}
    for attribute in duplicate["attributes"]:
        existing = have.get(attribute["id"])
        if existing is None:
            # A second key would make records ambiguous: the duplicate's key becomes an ordinary field.
            keep["attributes"].append({**attribute, "key": False} if attribute.get("key") and any(a.get("key") for a in keep["attributes"]) else attribute)
        elif existing["type"] != attribute["type"]:
            raise ValueError(f"{attribute['id']} has different types in {keep_id} and {duplicate_id}")
    seen = {(r["name"], r["target"]) for r in keep.get("relationships", [])}
    for relationship in duplicate.get("relationships", []):
        target = keep_id if relationship["target"] == duplicate_id else relationship["target"]
        if (relationship["name"], target) not in seen and target != keep_id:
            keep.setdefault("relationships", []).append({**relationship, "target": target})
            seen.add((relationship["name"], target))
    raw["business"]["entities"] = [e for e in entities if e["id"] != duplicate_id]
    for entity in raw["business"]["entities"]:
        for relationship in entity.get("relationships", []):
            if relationship["target"] == duplicate_id:
                relationship["target"] = keep_id
    for workflow in raw["workflow_definitions"]:
        for state in workflow["states"]:
            for key in ("reads_entity_ids", "writes_entity_ids"):
                if duplicate_id in state.get(key, []):
                    state[key] = list(dict.fromkeys(keep_id if x == duplicate_id else x for x in state[key]))
            for key in ("input_fields", "input_relationships"):
                mapping = state.get(key) or {}
                if duplicate_id in mapping:
                    mapping[keep_id] = list(dict.fromkeys([*mapping.get(keep_id, []), *mapping.pop(duplicate_id)]))
    _repoint_fields(
        {k: v for k, v in raw.items() if k != "business"} | {k: v for k, v in raw["business"].items() if k != "entities"},
        duplicate_id,
        keep_id,
    )
    for integration in raw["business"].get("integrations", []):
        integration["entity_ids"] = list(dict.fromkeys(keep_id if x == duplicate_id else x for x in integration.get("entity_ids", [])))


def _repoint_fields(value, duplicate_id, keep_id):
    """Rules, conditions, decision tables and screen traces name a field as 'entity.field' or an entity by id; follow the merge."""
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str):
                if child.startswith(duplicate_id + "."):
                    value[key] = keep_id + child[len(duplicate_id) :]
                elif child == duplicate_id and key in ("entity_id", "entity"):
                    value[key] = keep_id
            else:
                _repoint_fields(child, duplicate_id, keep_id)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, str) and child.startswith(duplicate_id + "."):
                value[index] = keep_id + child[len(duplicate_id) :]
            else:
                _repoint_fields(child, duplicate_id, keep_id)


def merge_shared_entities(raw):
    """Capabilities adopted together often each define the same master record (Item, Warehouse). Keep one, so the application has
    one list of items and one place to maintain them. Returns the (kept, merged) pairs."""
    merged = []
    entities = raw["business"]["entities"]
    for index, first in enumerate(list(entities)):
        for second in list(raw["business"]["entities"][index + 1 :]):
            if first["id"] == second["id"] or not (first.get("origin") and second.get("origin")):
                continue
            if first["origin"]["pack_id"] == second["origin"]["pack_id"] or not _same_record(first, second):
                continue
            try:
                merge_entities(raw, first["id"], second["id"])
            except ValueError:
                continue
            merged.append((first["id"], second["id"]))
    return merged
