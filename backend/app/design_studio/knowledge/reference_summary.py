"""A compact outline of a reference pack, shared by every model prompt that reads domain knowledge.

It carries the structure that makes a process complete (branches, exception handlers and their resolutions, open decisions),
so a model that builds on it does not leave an exception without an outcome or a requirement without a step.
"""


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _name(identifier: str, known: dict) -> str:
    """A record from a dependency pack is not in this pack's list: ent_core_supplier reads as "supplier"."""
    return known.get(identifier) or identifier.removeprefix("ent_").split("_", 1)[-1].replace("_", " ")


def _condition(condition: dict, rules: dict) -> str | None:
    if not condition or condition.get("kind") == "always":
        return None
    field = rules.get(condition.get("field"), condition.get("field"))
    return _clip(f"{field}: {condition.get('value', condition.get('kind'))}", 80)


def _process(workflow: dict, roles: dict, entities: dict, rules: dict, exceptions: dict) -> dict:
    """One workflow as an ordered list of steps, each with the path it takes next."""
    labels = {s["id"]: s["label"] for s in workflow.get("states", [])}
    steps = []
    for state in workflow.get("states", []):
        if state.get("kind") == "start":
            continue
        step = {
            "step": state["label"],
            "kind": state.get("kind"),
            "role": roles.get(state.get("role_id")),
            "reads": [_name(i, entities) for i in state.get("reads_entity_ids", [])],
            "writes": [_name(i, entities) for i in state.get("writes_entity_ids", [])],
            "decides_by": [rules.get(i, i) for i in state.get("rule_ids", [])],
            "handles_exception": [exceptions.get(i, i) for i in state.get("exception_ids", [])],
            "next": [
                {"to": labels.get(t["target"], t["target"]), "when": _condition(t.get("condition"), rules)}
                for t in workflow.get("transitions", [])
                if t["source"] == state["id"]
            ],
        }
        steps.append({k: v for k, v in step.items() if v not in (None, [], "")})
    return {"name": workflow.get("name"), "steps": steps}


def reference_summary(document: dict) -> dict:
    """Roles, records, the full process with its exception handling, typical rules and the decisions the business still owes."""
    business = document.get("business") or {}
    roles = {r["id"]: r["name"] for r in business.get("roles", [])}
    entities = {e["id"]: e["name"] for e in business.get("entities", [])}
    rules = {r["id"]: _clip(r.get("description", ""), 90) for r in business.get("rules", [])}
    exceptions = {e["id"]: e["name"] for e in business.get("exceptions", [])}
    labels = {s["id"]: s["label"] for w in document.get("workflows") or [] for s in w.get("states", [])}
    return {
        "id": document.get("id"),
        "title": document.get("title"),
        "status": document.get("status"),
        "provenance": document.get("provenance"),
        "roles": list(roles.values())[:10],
        "records": [
            {
                "name": e.get("name"),
                "fields": [
                    f"{a.get('name')}{'*' if a.get('required') else ''}" for a in e.get("attributes", [])
                ][:12],
            }
            for e in business.get("entities", [])[:10]
        ],
        "requirements": [_clip(r.get("statement", ""), 110) for r in business.get("requirements", [])][:8],
        "processes": [
            _process(w, roles, entities, rules, exceptions) for w in (document.get("workflows") or [])[:3]
        ],
        "exceptions": [
            {
                "name": e.get("name"),
                "trigger": _clip(e.get("trigger", ""), 100),
                "resolution": e.get("resolution"),
                "resolves_to_step": labels.get(e.get("resolution_state_id")),
                "recovery": _clip(e.get("recovery", ""), 100),
            }
            for e in business.get("exceptions", [])[:6]
        ],
        "typical_rules": [
            {"rule": _clip(r.get("description", ""), 100), "status": r.get("status")}
            for r in business.get("rules", [])[:6]
        ],
        "open_decisions": [_clip(d.get("question", ""), 120) for d in business.get("decisions", []) if d.get("status") == "open"][:4],
    }
