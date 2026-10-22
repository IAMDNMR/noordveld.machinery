"""A compact, deterministic way to write reference packs. The output is ordinary `ReferencePack` JSON; nothing here is executed at runtime.

Conventions every catalog pack follows (the builder checks them):
* ids carry the pack's short prefix (`ent_wms_pick_list`, `rule_pro_limit`) so packs can be adopted together without colliding;
* every entity gets a system-generated integer key named `<entity>_no` (distinct per entity, so relationships are links, never foreign keys on the key itself), so records have a readable reference without a value provider;
* every executable rule is an *assumption* (`synthetic_assumption`): it makes the demonstration run and is never presented as policy;
* genuine business policy questions are `decisions` and stay open; nothing is decided for the business owner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "app/design_studio/knowledge/packs"
FIXTURES = ROOT / "app/design_studio/knowledge/fixtures"
VERSION = "2026.10.1"
ASSUMED = {"kind": "synthetic_assumption", "reference": "Catalog design assumption: the business has not stated this rule. It lets the demonstration run and is not company policy."}
PROVENANCE = {"kind": "synthetic", "reference": "Authored for the reference catalog from common industry practice; no company or customer source.", "verification": "unverified"}


def A(id: str, name: str, type: str = "string", req: bool = False, enum: list[str] | None = None, min: float | None = None, max: float | None = None,
      fmt: str | None = None, desc: str = "", owner: str | None = None, maxlen: int | None = None, default: Any = None, sens: str = "internal") -> dict:
    item: dict[str, Any] = {"id": id, "name": name, "type": type, "required": req, "sensitivity": sens}
    if enum:
        item["enum"] = enum
    for key, value in (("minimum", min), ("maximum", max), ("format", fmt), ("description", desc), ("owner_role_id", owner), ("max_length", maxlen), ("default", default)):
        if value is not None and value != "":
            item[key] = value
    return item


class Pack:
    def __init__(self, id: str, prefix: str, title: str, description: str, layer: str = "business", deps: tuple[str, ...] = (), caps: tuple[str, ...] = (),
                 domain: dict | None = None, domain_id: str | None = None, capability: str | None = None, includes: tuple[str, ...] = (), company: dict | None = None):
        self.id, self.p, self.title, self.description, self.layer = id, prefix, title, description, layer
        self.deps, self.caps, self.domain, self.domain_id, self.capability = list(deps), list(caps), domain, domain_id, capability
        self.includes, self.company = list(includes), company
        self.roles: dict[str, dict] = {}
        self.entities: dict[str, dict] = {}
        self.rules: dict[str, dict] = {}
        self.requirements: list[dict] = []
        self.exceptions: list[dict] = []
        self.decisions: list[dict] = []
        self.integrations: list[dict] = []
        self.terms: list[dict] = []
        self.glossary: list[dict] = []
        self.workflows: list[dict] = []
        self.overrides: list[dict] = []
        self.fixture: dict[str, Any] = {"pack": id, "records": [], "flows": []}

    # ── ids ──
    def eid(self, key: str) -> str:
        return key if key.startswith("ent_") else f"ent_{self.p}_{key}"

    def rid(self, key: str) -> str:
        return key if key.startswith("role_") else f"role_{self.p}_{key}"

    def rule_id(self, key: str) -> str:
        return key if key.startswith("rule_") else f"rule_{self.p}_{key}"

    def ref(self, text: str) -> str:
        """`entity.attribute` with short or full entity ids."""
        entity, attribute = text.split(".")
        return f"{self.eid(entity)}.{attribute}"

    # ── content ──
    def role(self, key: str, name: str, perms: list[str], resp: list[str] | None = None, approve: list[str] | None = None) -> str:
        self.roles[key] = {"id": self.rid(key), "name": name, "responsibilities": resp or [], "permissions": list(perms), "approval_authority": approve or []}
        return self.rid(key)

    def entity(self, key: str, name: str, desc: str, attrs: list[dict], rels: list[tuple] | None = None, number_name: str = "Number", owner: str | None = None) -> str:
        number = {"id": f"{key}_no", "name": number_name, "type": "integer", "required": True, "key": True, "value_source": "system_generated", "writable": False, "sensitivity": "internal"}
        relationships = [{"id": f"rel_{self.p}_{key}_{rel[0]}", "name": rel[1], "target": self.eid(rel[2]), "cardinality": rel[3] if len(rel) > 3 else "many_to_one",
                          "required": bool(rel[4]) if len(rel) > 4 else False} for rel in (rels or [])]
        self.entities[key] = {"id": self.eid(key), "name": name, "description": desc, "attributes": [number, *attrs], "relationships": relationships}
        if owner:
            self.entities[key]["owner_role_id"] = self.rid(owner)  # the owner role maintains this master data
        return self.eid(key)

    def rule(self, key: str, desc: str, field: str, op: str = "present", value: Any = None, other: str | None = None, outcomes: list[str] | None = None,
             kind: str = "compare", condition: str = "") -> str:
        execution = {"kind": kind, "field": self.ref(field), "operator": op, "value": value, "other_field": self.ref(other) if other else None,
                     "pass_outcome": outcomes[0] if outcomes and kind == "compare" else None, "fail_outcome": outcomes[1] if outcomes and kind == "compare" else None}
        self.rules[key] = {"id": self.rule_id(key), "description": desc, "type": "decision" if outcomes else "validation", "status": "assumption", "source": ASSUMED,
                           "condition": condition, "outcomes": outcomes or [], "execution": execution}
        return self.rule_id(key)

    def req(self, key: str, statement: str, criteria: list[str], priority: str = "must") -> str:
        rid = f"req_{self.p}_{key}"
        self.requirements.append({"id": rid, "statement": statement, "kind": "functional", "priority": priority, "status": "agreed",
                                  "acceptance_criteria": [{"id": f"ac_{self.p}_{key}_{n + 1}", "statement": text} for n, text in enumerate(criteria)]})
        return rid

    def exc(self, key: str, name: str, trigger: str, recovery: str, to: tuple[str, str]) -> str:
        """`to` is (workflow key, step key): where the work resumes once the exception is resolved."""
        self.exceptions.append({"id": f"exc_{self.p}_{key}", "name": name, "trigger": trigger, "recovery": recovery, "resolution": "recover",
                                "resolution_state_id": f"st_{self.p}_{to[0]}_{to[1]}"})
        return f"exc_{self.p}_{key}"

    def dec(self, key: str, question: str, affects: list[str]) -> str:
        did = f"dec_{self.p}_{key}"
        self.decisions.append({"id": did, "question": question, "status": "open", "answer": "", "deferral_reason": "", "affects": affects})
        return did

    def integration(self, key: str, name: str, system: str, direction: str, events: list[str], entities: list[str], failure: str = "") -> str:
        iid = f"int_{self.p}_{key}"
        self.integrations.append({"id": iid, "name": name, "system": system, "direction": direction, "events": events, "entity_ids": [self.eid(e) for e in entities],
                                  "failure_handling": failure, "contract_status": "deferred"})
        return iid

    def term(self, key: str, term: str, definition: str, synonyms: list[str], refers_to: str | None = None):
        self.terms.append({"id": f"term_{self.p}_{key}", "term": term, "definition": definition})
        self.glossary.append({"term": term, "definition": definition, "synonyms": synonyms, **({"refers_to": refers_to} if refers_to else {})})

    def override(self, item_id: str, reason: str, patch: dict | None = None, add_attributes: list[dict] | None = None, add_permissions: list[str] | None = None):
        self.overrides.append({"item_id": item_id, "reason": reason, "patch": patch or {}, "add_attributes": add_attributes or [], "add_permissions": add_permissions or []})

    # ── workflow ──
    def flow(self, key: str, name: str, steps: list[dict], edges: list[tuple], serves: list[str]) -> str:
        wid = f"wf_{self.p}_{key}"
        serves = [item["id"] for item in self.requirements if item["kind"] == "functional"]  # every step serves the functional requirements it belongs to
        sid = lambda s: f"st_{self.p}_{key}_{s}"  # noqa: E731
        by_key = {step["key"]: step for step in steps}
        states, role_of = [], {}
        for step in steps:
            role = self.rid(step["role"]) if step.get("role") else None
            role_of[step["key"]] = role
        incoming = {}
        for edge in edges:
            incoming.setdefault(edge[1], edge[0])
        for step in steps:
            role = role_of[step["key"]]
            if step["kind"] == "branch" and role is None:
                role = role_of.get(incoming.get(step["key"], ""))
            permission = None
            if step["kind"] not in ("start", "end", "branch"):
                permission = step.get("perm") or f"{self.p}.{key}_{step['key']}"
                holder = next(r for r in self.roles.values() if r["id"] == role)
                if permission not in holder["permissions"]:
                    holder["permissions"].append(permission)
            human = step["kind"] not in ("start", "end")
            states.append({"id": sid(step["key"]), "label": step["label"], "kind": step["kind"], "outputs": [self.rule_id(r) for r in step.get("out", [])],
                           "outcome": step.get("outcome"), "role_id": role if human else None, "permission": permission,
                           "requirement_ids": serves if human else [], "reads_entity_ids": [self.eid(e) for e in step.get("reads", [])],
                           "writes_entity_ids": [self.eid(e) for e in step.get("writes", [])], "rule_ids": [self.rule_id(r) for r in step.get("rules", [])],
                           "exception_ids": [f"exc_{self.p}_{e}" for e in step.get("exc", [])], "preconditions": [], "postconditions": []})
        transitions = []
        for number, edge in enumerate(edges, 1):
            condition = {"kind": "equals", "field": self.rule_id(edge[2]), "value": edge[3]} if len(edge) > 2 else {"kind": "always"}
            transitions.append({"id": f"tr_{self.p}_{key}_{number}", "source": sid(edge[0]), "target": sid(edge[1]), "condition": condition})
        self.workflows.append({"version": 1, "id": wid, "name": name, "states": states, "transitions": transitions})
        return wid

    def scenario(self, **parts: Any):
        self.fixture.update(parts)

    # ── output ──
    def document(self) -> dict:
        def listing(d: dict) -> list:
            return list(d.values())
        if self.layer != "reusable" and not any(item["kind"] == "non_functional" for item in self.requirements):
            self.requirements.append({"id": f"req_{self.p}_audit", "statement": "Every change to a record and every process step is recorded with who did it and when.", "kind": "non_functional",
                                      "category": "auditability", "priority": "must", "status": "agreed",
                                      "acceptance_criteria": [{"id": f"ac_{self.p}_audit_1", "statement": "The history of a process shows each step with its actor and time."}]})
        for workflow in self.workflows:  # the auditability requirement is served by every step a person performs: the runtime records each one
            for state in workflow["states"]:
                if state["requirement_ids"] and any(item["kind"] == "non_functional" for item in self.requirements):
                    state["requirement_ids"] = list(dict.fromkeys([*state["requirement_ids"], *[item["id"] for item in self.requirements if item["kind"] == "non_functional"]]))
        document = {"id": self.id, "version": getattr(self, "version", VERSION), "layer": self.layer, "title": self.title, "description": self.description, "synthetic": True,
                    "status": "in_review", "provenance": PROVENANCE, "depends_on": self.deps, "uses_capabilities": self.caps,
                    "dependency_mode": "data_model", "includes": self.includes,
                    "business": {"requirements": self.requirements, "roles": listing(self.roles), "entities": listing(self.entities), "rules": listing(self.rules),
                                 "exceptions": self.exceptions, "decisions": self.decisions, "integrations": self.integrations, "terms": self.terms},
                    "workflows": self.workflows, "glossary": self.glossary, "overrides": self.overrides}
        if self.domain:
            document["domains"] = [self.domain]
        if self.domain_id:
            document["domain_id"] = self.domain_id
        if self.capability:
            document["capability"] = {"id": self.domain_id or self.id, "name": self.capability}
        if self.company:
            document["company"] = self.company
        from task_contracts import apply_contracts, CONTRACTS, VERSION as TASK_VERSION
        if any(s['id'] in CONTRACTS for w in document['workflows'] for s in w['states']):
            apply_contracts(document, {e['id']: e for e in document['business']['entities']})
            document['version'] = TASK_VERSION
        return document

    def write(self):
        PACKS.mkdir(parents=True, exist_ok=True)
        (PACKS / f"{self.id}.json").write_text(json.dumps(self.document(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / f"{self.id}.json").write_text(json.dumps(self.fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def S(key: str, label: str, kind: str, role: str | None = None, reads: list[str] | None = None, writes: list[str] | None = None, rules: list[str] | None = None,
      out: list[str] | None = None, outcome: str | None = None, exc: list[str] | None = None, perm: str | None = None) -> dict:
    return {"key": key, "label": label, "kind": kind, "role": role, "reads": reads or [], "writes": writes or [], "rules": rules or [], "out": out or [],
            "outcome": outcome, "exc": exc or [], "perm": perm}


def rec(name: str, entity: str, role: str, values: dict, refs: dict | None = None, shared: bool = False) -> dict:
    """A synthetic record for a scenario. `refs` maps a target entity id to the name of another scenario record. `shared` marks master data
    other domains use (customers, items, stock, orders): it is created even when this pack only supplies its data model."""
    return {"name": name, "entity": entity, "role": role, "values": values, "refs": refs or {}, "shared": shared}


def run(flow: str, bind: dict, set: dict | None = None, ends: str = "done") -> dict:
    """A scenario run of one workflow: which records each step works on, record changes made just before a step, and the expected end."""
    return {"flow": flow, "bind": bind, "set": set or {}, "ends": ends}
