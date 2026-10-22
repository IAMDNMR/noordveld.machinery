"""Portable generated local application runtime; Python standard library only.

This file is copied into runtime/server.py. No imports from Design Studio are allowed.
Only the explicit --demo loopback launch is supported; production identity is not simulated.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4

from validation import normalize_record, validate_record


# Not a business role: a demo identity that enters the records an inbound integration would supply. It exists only because no
# import adapter is connected; it never performs process steps and every record it enters is audited as a manual import.
IMPORT_ROLE = "_import_stand_in"


def generated_value(attribute, record_id, existing):
    """Deterministic value of a system-generated key: the record's own identifier, or the next number for an integer key."""
    if attribute["type"] == "integer":
        return 1 + max(
            (value for value in existing if isinstance(value, int) and not isinstance(value, bool)),
            default=0,
        )
    return record_id


class Fault(Exception):
    def __init__(self, status, message, details=None):
        self.status, self.message, self.details = status, message, details


class Runtime:
    def __init__(self, schema, database):
        self.schema, self.database = schema, str(database)
        self.entities = {e["id"]: e for e in schema["entities"]}
        self.workflows = {w["id"]: w for w in schema["workflows"]}
        self.rules = {r["id"]: r for r in schema["rules"]}
        # Open business decisions and the rules that wait on them: what the application says instead of guessing.
        self.waiting = {
            target: d for d in schema.get("decisions", []) for target in d.get("affects", [])
        }
        self.roles = {r["id"]: r for r in schema["roles"]}
        self.imports = set(schema.get("imports", []))
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (tenant TEXT, entity TEXT, id TEXT, revision INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(tenant,entity,id));
                CREATE TABLE IF NOT EXISTS instances (tenant TEXT, id TEXT, workflow TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL, links TEXT NOT NULL, PRIMARY KEY(tenant,id));
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, actor TEXT NOT NULL, resource TEXT NOT NULL, action TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, tenant TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL, expires REAL NOT NULL);
            """)
            old = db.execute("SELECT value FROM metadata WHERE key='specification'").fetchone()
            if old and old[0] != schema["fingerprint"]:
                raise Fault(
                    409,
                    "This database belongs to a different specification. Use a new isolated database; migration is not automatic.",
                )
            db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('specification',?)",
                (schema["fingerprint"],),
            )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def role_names(self):
        names = {role_id: role["name"] for role_id, role in self.roles.items()}
        return (
            {**names, IMPORT_ROLE: "Data import stand-in (no integration connected)"}
            if self.imports
            else names
        )

    def users(self):
        primary_roles = {
            state.get("role_id")
            for workflow in self.workflows.values()
            for state in workflow["states"]
        }
        return [
            {
                "id": f"{tenant}:{role}",
                "name": f"{name} · {tenant}",
                "tenant": tenant,
                "role": role,
                "primary": role in primary_roles,
            }
            for tenant in ("demo_noordveld", "demo_harbor")
            for role, name in self.role_names().items()
        ]

    def login(self, user_id):
        user = next((u for u in self.users() if u["id"] == user_id), None)
        if not user:
            raise Fault(401, "Unknown local demo identity")
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (token, user["tenant"], user["id"], user["role"], time.time() + 28800),
            )
        return token

    def identity(self, token):
        with self.db() as db:
            row = db.execute(
                "SELECT tenant,actor,role FROM sessions WHERE token=? AND expires>?",
                (token, time.time()),
            ).fetchone()
        if not row:
            raise Fault(401, "Sign in to continue")
        return dict(row)

    def permits(self, user, step):
        # Roles and permissions are separate: holding a permission does not impersonate the responsible role.
        return bool(
            step.get("role_id") == user["role"]
            and step.get("permission")
            and step["permission"] in self.roles[user["role"]]["permissions"]
        )

    def entity_access(self, user, entity, write=False):
        if entity not in self.entities:
            raise Fault(404, "Entity not found")
        if user["role"] == IMPORT_ROLE:
            if entity in self.imports:
                return
            raise Fault(
                403, "The import stand-in only enters records that come from an external system"
            )
        if self.entities[entity].get("owner_role_id") == user["role"]:
            return  # the owner role maintains its own master data, whether or not a process step touches it
        for workflow in self.workflows.values():
            for step in workflow["states"]:
                fields = (
                    step.get("writes_entity_ids", [])
                    if write
                    else step.get("reads_entity_ids", []) + step.get("writes_entity_ids", [])
                )
                if entity in fields and self.permits(user, step):
                    return
        raise Fault(403, "Your application role cannot access this entity")

    @staticmethod
    def event(db, user, resource, action, data):
        db.execute(
            "INSERT INTO events(tenant,actor,resource,action,data,at) VALUES (?,?,?,?,?,?)",
            (
                user["tenant"],
                user["actor"],
                resource,
                action,
                json.dumps(data, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _record(self, db, tenant, entity, record_id):
        row = db.execute(
            "SELECT * FROM records WHERE tenant=? AND entity=? AND id=?",
            (tenant, entity, record_id),
        ).fetchone()
        if not row:
            raise Fault(404, "Record not found in this organization")
        return {"id": row["id"], "revision": row["revision"], "data": json.loads(row["data"])}

    def records(self, user, entity):
        self.entity_access(user, entity)
        with self.db() as db:
            return [
                {"id": r["id"], "revision": r["revision"], "data": json.loads(r["data"])}
                for r in db.execute(
                    "SELECT * FROM records WHERE tenant=? AND entity=? ORDER BY rowid DESC LIMIT 500",
                    (user["tenant"], entity),
                )
            ]

    def save_record(
        self,
        user,
        entity,
        data,
        record_id=None,
        expected=None,
        task_context=None,
        *,
        _connection=None,
    ):
        self.entity_access(user, entity, True)
        if not isinstance(data, dict):
            raise Fault(422, "Supply a record object")
        if expected is not None and (
            type(expected) is not int or expected < 1 or record_id is None
        ):
            raise Fault(422, "Expected revision is a positive integer for an existing record")
        model = self.entities[entity]
        if (
            record_id is None
            and model.get("owner_role_id")
            and model["owner_role_id"] != user["role"]
        ):
            raise Fault(403, "Only the entity owner role may create this record")
        links = [r for r in self.schema["references"] if r["source"] == entity]
        link_fields = {r["field"] for r in links if r["enforcement"] == "link"}
        rules = model["validation"]
        if (
            user["role"] == IMPORT_ROLE
        ):  # it supplies what the external system would: imported values, never system-generated ones
            rules = [
                {**rule, "system_managed": False} if rule["value_source"] == "imported" else rule
                for rule in rules
            ]
        managed = {rule["id"] for rule in rules if rule["system_managed"]}
        submitted = data
        with self.db() if _connection is None else nullcontext(_connection) as db:
            task_state = None
            if task_context is not None:
                if not isinstance(task_context, dict) or set(task_context) != {
                    "instance_id",
                    "expected_revision",
                }:
                    raise Fault(422, "Supply the process instance and its expected revision")
                if (
                    not isinstance(task_context["instance_id"], str)
                    or not 1 <= len(task_context["instance_id"]) <= 80
                    or type(task_context["expected_revision"]) is not int
                    or task_context["expected_revision"] < 1
                ):
                    raise Fault(422, "Invalid process instance or revision")
                instance = db.execute(
                    "SELECT * FROM instances WHERE tenant=? AND id=?",
                    (user["tenant"], task_context["instance_id"]),
                ).fetchone()
                if not instance:
                    raise Fault(404, "Process record not found in this organization")
                if instance["revision"] != task_context["expected_revision"]:
                    raise Fault(
                        409, "The process changed. Reload the task before editing its records."
                    )
                task_state = next(
                    s
                    for s in self.workflows[instance["workflow"]]["states"]
                    if s["id"] == instance["state"]
                )
                if not self.permits(user, task_state) or entity not in task_state.get(
                    "writes_entity_ids", []
                ):
                    raise Fault(403, "Your role cannot edit this record for the current task")
                bound = json.loads(instance["links"]).get(entity)
                if bound and bound != record_id:
                    raise Fault(409, "This task is linked to a different record")
                if task_state.get("input_fields") is not None:
                    allowed = set(task_state["input_fields"].get(entity, []))
                    allowed.update(
                        r["field"]
                        for r in links
                        if r["relationship_id"]
                        in (task_state.get("input_relationships") or {}).get(entity, [])
                    )
                    if set(data) - allowed:
                        raise Fault(403, "Only the fields assigned to this task may be changed")
            previous = {}
            if record_id:
                current = self._record(db, user["tenant"], entity, record_id)
                if current["revision"] != expected:
                    raise Fault(409, "Record changed. Reload it before saving.")
                for attribute in model["attributes"]:
                    if (
                        attribute["key"]
                        and attribute["id"] in data
                        and data.get(attribute["id"]) != current["data"].get(attribute["id"])
                    ):
                        raise Fault(422, "A record key cannot be changed")
                previous = current["data"]
            for attribute in model["attributes"]:
                if (
                    attribute.get("owner_role_id")
                    and attribute["owner_role_id"] != user["role"]
                    and attribute["id"] in data
                ):
                    if data[attribute["id"]] != previous.get(attribute["id"]):
                        raise Fault(403, f"{attribute['name']} is maintained by another role")
            data = {**previous, **data}
            # Values the system stored earlier are not resubmissions; a submitted system-managed value is still refused.
            fields = {
                k: v
                for k, v in data.items()
                if k not in link_fields and (k in submitted or k not in managed)
            }
            errors = validate_record(rules, fields, "create")
            if errors:
                raise Fault(422, "Correct the record fields", errors)
            data = {
                **data,
                **normalize_record(rules, {k: v for k, v in data.items() if k in fields}),
            }  # datetimes stored as canonical UTC
            for ref in links:
                value = data.get(ref["field"])
                if value in (None, ""):
                    if ref["required"]:
                        target = self.entities[ref["target"]]["name"]
                        raise Fault(
                            422,
                            "Correct the record fields",
                            [
                                {
                                    "field": ref["field"],
                                    "code": "required",
                                    "message": f"Choose the related {target} record.",
                                }
                            ],
                        )
                    continue
                found = False
                for row in db.execute(
                    "SELECT id,data FROM records WHERE tenant=? AND entity=?",
                    (user["tenant"], ref["target"]),
                ):
                    target = json.loads(row["data"])
                    if value == (
                        target.get(ref["target_key"])
                        if ref["enforcement"] == "foreign_key"
                        else row["id"]
                    ):
                        found = True
                        break
                if not found:
                    target = self.entities[ref["target"]]["name"]
                    raise Fault(
                        422,
                        "Correct the record fields",
                        [
                            {
                                "field": ref["field"],
                                "code": "reference",
                                "message": f"That {target} record does not exist in this organization.",
                            }
                        ],
                    )
                if ref["cardinality"] == "one_to_one":
                    for row in db.execute(
                        "SELECT id,data FROM records WHERE tenant=? AND entity=?",
                        (user["tenant"], entity),
                    ):
                        if (
                            row["id"] != record_id
                            and json.loads(row["data"]).get(ref["field"]) == value
                        ):
                            raise Fault(409, "That one-to-one relationship is already assigned")
            new = record_id is None
            record_id = record_id or uuid4().hex
            if new:
                for attribute in model["attributes"]:
                    if attribute["key"] and attribute["value_source"] == "system_generated":
                        existing = [
                            json.loads(row["data"]).get(attribute["id"])
                            for row in db.execute(
                                "SELECT data FROM records WHERE tenant=? AND entity=?",
                                (user["tenant"], entity),
                            )
                        ]
                        data[attribute["id"]] = generated_value(attribute, record_id, existing)
            for attribute in model["attributes"]:
                if (
                    attribute["key"] and data.get(attribute["id"]) is not None
                ):  # an absent value duplicates nothing
                    for row in db.execute(
                        "SELECT id,data FROM records WHERE tenant=? AND entity=?",
                        (user["tenant"], entity),
                    ):
                        if row["id"] != record_id and json.loads(row["data"]).get(
                            attribute["id"]
                        ) == data.get(attribute["id"]):
                            raise Fault(409, f"{attribute['name']} must be unique")
            version = expected + 1 if expected is not None else 1
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?) ON CONFLICT(tenant,entity,id) DO UPDATE SET revision=excluded.revision,data=excluded.data",
                (user["tenant"], entity, record_id, version, json.dumps(data, allow_nan=False)),
            )
            action = (
                "record.update"
                if expected
                else ("record.import" if user["role"] == IMPORT_ROLE else "record.create")
            )
            self.event(
                db,
                user,
                f"{entity}/{record_id}",
                action,
                {
                    "revision": version,
                    "changed_fields": sorted(k for k in data if previous.get(k) != data[k]),
                    **(
                        {"instance_id": task_context["instance_id"], "step_id": task_state["id"]}
                        if task_state
                        else {}
                    ),
                },
            )
            return self._record(db, user["tenant"], entity, record_id)

    def workflow_access(self, user, workflow):
        if not any(self.permits(user, step) for step in workflow["states"]):
            raise Fault(403, "Your role cannot use this process")

    def create_instance(self, user, workflow_id, links):
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise Fault(404, "Process not found")
        self.workflow_access(user, workflow)
        start = next(s for s in workflow["states"] if s["kind"] == "start")
        edges = [e for e in workflow["transitions"] if e["source"] == start["id"]]
        if len(edges) != 1 or edges[0]["condition"]["kind"] != "always":
            raise Fault(409, "This start gateway is unsupported")
        first = next(s for s in workflow["states"] if s["id"] == edges[0]["target"])
        if not self.permits(user, first):
            raise Fault(403, "Only the responsible role may start this process")
        if not isinstance(links, dict) or any(
            k not in self.entities or not isinstance(v, str) for k, v in links.items()
        ):
            raise Fault(422, "Invalid entity record links")
        with self.db() as db:
            for entity, record_id in links.items():
                self.entity_access(user, entity)
                self._record(db, user["tenant"], entity, record_id)
            instance_id = uuid4().hex
            db.execute(
                "INSERT INTO instances VALUES (?,?,?,?,?,?)",
                (user["tenant"], instance_id, workflow_id, first["id"], 1, json.dumps(links)),
            )
            self.event(
                db, user, instance_id, "process.start", {"state": first["id"], "links": links}
            )
        return self.instance(user, instance_id)

    def instance(self, user, instance_id):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM instances WHERE tenant=? AND id=?", (user["tenant"], instance_id)
            ).fetchone()
            if not row:
                raise Fault(404, "Process record not found")
            self.workflow_access(user, self.workflows[row["workflow"]])
            return self._instance_view(user, row)

    def _instance_view(self, user, row):
        result = dict(row)
        result["links"] = json.loads(result["links"])
        workflow = self.workflows[row["workflow"]]
        state = next(s for s in workflow["states"] if s["id"] == row["state"])
        result["step"] = state
        result["can_act"] = self.permits(user, state) and state["kind"] != "end"
        result["blocked"] = self.blockers(workflow, state) if state["kind"] != "end" else []
        return result

    def instances(self, user):
        allowed = {
            w["id"]
            for w in self.workflows.values()
            if any(self.permits(user, s) for s in w["states"])
        }
        with self.db() as db:
            return [
                self._instance_view(user, r)
                for r in db.execute(
                    "SELECT * FROM instances WHERE tenant=? ORDER BY rowid DESC LIMIT 500",
                    (user["tenant"],),
                )
                if r["workflow"] in allowed
            ]

    def why_not(self, rule):
        decision = self.waiting.get(rule["id"])
        if decision:
            return f"This step cannot run yet: the rule “{rule['description']}” waits on a business decision that is still open: {decision['question']} ({rule['id']})"
        return f"This step cannot run yet: the rule “{rule['description']}” has no executable logic in this application ({rule['id']})"

    def blockers(self, workflow, step):
        """Reasons the current step can never complete as designed, whatever records are linked: its own rules and the automatic
        decisions that always follow it. Shown before anyone tries, and the same reasons the server gives if they do."""
        states = {s["id"]: s for s in workflow["states"]}
        reasons, seen, queue = [], set(), [step]
        while queue:
            current = queue.pop(0)
            if current["id"] in seen:
                continue
            seen.add(current["id"])
            if current.get("preconditions") or current.get("postconditions"):
                reasons.append(
                    {
                        "rule": None,
                        "decision": None,
                        "message": f"“{current['label']}” has conditions written in prose; they need executable rules before it can run.",
                    }
                )
            for rule_id in current.get("rule_ids", []):
                rule = self.rules.get(rule_id)
                if rule and not rule.get("execution"):
                    decision = self.waiting.get(rule_id)
                    reasons.append(
                        {
                            "rule": rule_id,
                            "decision": decision["id"] if decision else None,
                            "question": decision["question"] if decision else None,
                            "message": self.why_not(rule),
                        }
                    )
            for edge in workflow["transitions"]:
                target = states.get(edge["target"])
                if (
                    edge["source"] == current["id"]
                    and edge["condition"]["kind"] == "always"
                    and target
                    and target["kind"] == "branch"
                ):
                    queue.append(target)
        return reasons

    def _evaluate(self, rule, records):
        execution = rule.get("execution")
        if not execution:
            raise Fault(409, self.why_not(rule))

        def value(ref):
            entity, attr = ref.split(".")
            if entity not in records or records[entity].get(attr) is None:
                model = self.entities.get(entity, {"name": entity, "attributes": []})
                field = next((a["name"] for a in model["attributes"] if a["id"] == attr), attr)
                raise Fault(
                    422,
                    f"The linked {model['name']} record has no {field} yet; the rule “{rule['description']}” needs it.",
                )
            return records[entity][attr]

        left = value(execution["field"])
        if execution["kind"] == "value":
            if left not in rule["outcomes"]:
                raise Fault(
                    422,
                    f"{left} is not one of the allowed answers for “{rule['description']}”: {', '.join(rule['outcomes'])}.",
                )
            return left
        right = (
            value(execution["other_field"])
            if execution.get("other_field")
            else execution.get("value")
        )
        operator = execution["operator"]
        try:
            passed = {
                "eq": lambda: type(left) is type(right) and left == right,
                "ne": lambda: type(left) is not type(right) or left != right,
                "gt": lambda: left > right,
                "gte": lambda: left >= right,
                "lt": lambda: left < right,
                "lte": lambda: left <= right,
                "present": lambda: left not in (None, ""),
            }[operator]()
        except (TypeError, KeyError):
            raise Fault(
                422, f"The values compared by “{rule['description']}” have different types."
            ) from None
        if rule["outcomes"]:
            return execution["pass_outcome"] if passed else execution["fail_outcome"]
        if not passed:
            raise Fault(422, rule["description"])
        return True

    def advance(self, user, instance_id, expected, links):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM instances WHERE tenant=? AND id=?", (user["tenant"], instance_id)
            ).fetchone()
            if not row:
                raise Fault(404, "Process record not found")
            if row["revision"] != expected:
                raise Fault(409, "Process changed. Reload before continuing.")
            workflow = self.workflows[row["workflow"]]
            states = {s["id"]: s for s in workflow["states"]}
            step = states[row["state"]]
            if not self.permits(user, step) or step["kind"] == "end":
                raise Fault(403, "Your role cannot perform this action at the current state")
            if step["kind"] == "approval":
                starter = db.execute(
                    "SELECT actor FROM events WHERE tenant=? AND resource=? AND action='process.start' ORDER BY seq LIMIT 1",
                    (user["tenant"], instance_id),
                ).fetchone()
                if starter and starter["actor"] == user["actor"]:
                    raise Fault(403, "A separate person must approve this process")
            current_links = json.loads(row["links"])
            writable = set(step.get("reads_entity_ids", []) + step.get("writes_entity_ids", []))
            if not isinstance(links, dict) or any(
                k not in writable or not isinstance(v, str) for k, v in links.items()
            ):
                raise Fault(422, "This action cannot bind those entities")
            current_links.update(links)
            records = {
                entity: self._record(db, user["tenant"], entity, record_id)["data"]
                for entity, record_id in current_links.items()
            }
            for ref in self.schema["references"]:
                if ref["source"] in records and ref["target"] in records:
                    linked_value = records[ref["source"]].get(ref["field"])
                    target_value = (
                        records[ref["target"]].get(ref["target_key"])
                        if ref["enforcement"] == "foreign_key"
                        else current_links[ref["target"]]
                    )
                    if linked_value not in (None, "") and linked_value != target_value:
                        raise Fault(422, "Process record links disagree with a stored relationship")
            for entity in writable:
                if entity not in records:
                    raise Fault(
                        422,
                        f"Link the {self.entities[entity]['name']} record before completing this step.",
                    )
            path, outputs = [], {}
            for _ in range(100):
                if step.get("preconditions") or step.get("postconditions"):
                    raise Fault(
                        409,
                        "Convert prose preconditions and postconditions into explicit executable rules before running this action",
                    )
                for rule_id in step.get("rule_ids", []):
                    outputs[rule_id] = self._evaluate(self.rules[rule_id], records)
                edges = []
                for edge in workflow["transitions"]:
                    if edge["source"] != step["id"]:
                        continue
                    condition = edge["condition"]
                    if condition["kind"] == "always":
                        edges.append(edge)
                    elif condition["field"] not in outputs:
                        raise Fault(
                            409,
                            self.why_not(self.rules[condition["field"]])
                            if condition["field"] in self.rules
                            else "This step has no executable decision for its next path.",
                        )
                    elif (outputs[condition["field"]] == condition["value"]) == (
                        condition["kind"] == "equals"
                    ):
                        edges.append(edge)
                if len(edges) != 1:
                    raise Fault(409, "The process must resolve exactly one next path")
                path.append({"source": step["id"], "target": edges[0]["target"]})
                step = states[edges[0]["target"]]
                if step["kind"] != "branch":
                    break
            else:
                raise Fault(409, "Automatic branch cycle detected")
            db.execute(
                "UPDATE instances SET state=?,revision=revision+1,links=? WHERE tenant=? AND id=?",
                (step["id"], json.dumps(current_links), user["tenant"], instance_id),
            )
            self.event(
                db,
                user,
                instance_id,
                "process.advance",
                {"path": path, "outputs": outputs, "revision": expected + 1},
            )
        return self.instance(user, instance_id)

    def history(self, user, instance_id):
        self.instance(user, instance_id)
        with self.db() as db:
            return [
                {**dict(row), "data": json.loads(row["data"])}
                for row in db.execute(
                    "SELECT actor,action,data,at FROM events WHERE tenant=? AND resource=? ORDER BY seq",
                    (user["tenant"], instance_id),
                )
            ]

    def record_history(self, user, entity, record_id):
        self.entity_access(user, entity)
        with self.db() as db:
            self._record(db, user["tenant"], entity, record_id)
            return [
                {**dict(row), "data": json.loads(row["data"])}
                for row in db.execute(
                    "SELECT actor,action,data,at FROM events WHERE tenant=? AND resource=? ORDER BY seq",
                    (user["tenant"], f"{entity}/{record_id}"),
                )
            ]

    def view(self, user):
        entities = []
        for entity in self.entities.values():
            try:
                self.entity_access(user, entity["id"])
            except Fault:
                continue
            writable = True
            try:
                self.entity_access(user, entity["id"], True)
            except Fault:
                writable = False
            if user["role"] == IMPORT_ROLE:
                entity = {
                    **entity,
                    "attributes": [
                        {**a, "writable": True} if a["value_source"] == "imported" else a
                        for a in entity["attributes"]
                    ],
                }
            entities.append(
                {
                    **entity,
                    "writable": writable,
                    "creatable": writable
                    and (
                        not entity.get("owner_role_id") or entity["owner_role_id"] == user["role"]
                    ),
                }
            )
        return {
            "name": self.schema["name"],
            "user": user,
            "entities": entities,
            "references": self.schema["references"],
            "workflows": [
                w
                for w in self.workflows.values()
                if any(self.permits(user, s) for s in w["states"])
            ],
            "unsupported": self.schema["unsupported"],
            "fingerprint": self.schema["fingerprint"],
            "roles": self.role_names(),
            "presentation": self.schema.get("presentation") or {},
            "groups": self.schema.get("groups") or [],
            "report": self.schema.get("report") or {},
            "unsupported_items": self.schema.get("unsupported_items") or [],
            "decisions": self.schema.get("decisions") or [],
        }


def handler(runtime, root, gateway=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # never log session cookies or business payloads

        def send(self, status, data, content_type="application/json", cookie=None):
            payload = (
                json.dumps(data, allow_nan=False).encode()
                if content_type == "application/json"
                else data
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",
            )
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(payload)

        def dispatch(self):
            host = self.headers.get("Host", "")
            if host not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                raise Fault(403, "Loopback host required")
            path = urlsplit(self.path).path
            body, raw = {}, b""
            if self.command == "POST":
                if (
                    self.headers.get("Origin") not in (None, f"http://{host}")
                    or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                ):
                    raise Fault(403, "Same-origin JSON request required")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 100000:
                    raise Fault(413, "Request is too large or empty")
                raw = self.rfile.read(size)
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise Fault(422, "Request must be an object")
            if self.command == "GET" and path in ("/", "/app.js", "/app.css"):
                name = "index.html" if path == "/" else path[1:]
                return self.send(
                    200,
                    (root / name).read_bytes(),
                    {
                        "index.html": "text/html; charset=utf-8",
                        "app.js": "text/javascript",
                        "app.css": "text/css",
                    }[name],
                )
            if path == "/api/demo-users" and self.command == "GET":
                return self.send(200, runtime.users())
            if path == "/api/login" and self.command == "POST":
                token = runtime.login(body.get("user_id"))
                return self.send(
                    200,
                    {"signed_in": True},
                    cookie=f"app_session={token}; HttpOnly; SameSite=Strict; Path=/",
                )
            integration_parts = path.strip("/").split("/")
            if (
                len(integration_parts) == 4
                and integration_parts[:2] == ["api", "integrations"]
                and integration_parts[3] == "records"
            ):
                if gateway is None:
                    raise Fault(404, "Integration is not configured")
                return self.send(
                    200,
                    gateway.exchange(
                        integration_parts[2], self.command, self.path, self.headers, raw
                    ),
                )
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            user = runtime.identity(
                cookies["app_session"].value if "app_session" in cookies else ""
            )
            parts = path.strip("/").split("/")
            if self.command == "GET":
                if path == "/api/application":
                    return self.send(200, runtime.view(user))
                if path == "/api/instances":
                    return self.send(200, runtime.instances(user))
                if len(parts) == 3 and parts[:2] == ["api", "records"]:
                    return self.send(200, runtime.records(user, parts[2]))
                if len(parts) == 5 and parts[:2] == ["api", "records"] and parts[4] == "history":
                    return self.send(200, runtime.record_history(user, parts[2], parts[3]))
                if len(parts) == 4 and parts[:2] == ["api", "instances"] and parts[3] == "history":
                    return self.send(200, runtime.history(user, parts[2]))
            if self.command == "POST":
                if path == "/api/instances":
                    return self.send(
                        201,
                        runtime.create_instance(
                            user, body.get("workflow_id"), body.get("links", {})
                        ),
                    )
                if len(parts) in (3, 4) and parts[:2] == ["api", "records"]:
                    return self.send(
                        200,
                        runtime.save_record(
                            user,
                            parts[2],
                            body.get("data"),
                            parts[3] if len(parts) == 4 else None,
                            body.get("expected_revision"),
                            body.get("task_context"),
                        ),
                    )
                if len(parts) == 4 and parts[:2] == ["api", "instances"] and parts[3] == "advance":
                    if set(body) - {"expected_revision", "links"}:
                        raise Fault(
                            422,
                            "Only revision and record links may be submitted; state and rule results are server-owned",
                        )
                    return self.send(
                        200,
                        runtime.advance(
                            user, parts[2], body.get("expected_revision"), body.get("links", {})
                        ),
                    )
            raise Fault(404, "Operation not found")

        def handle_request(self):
            try:
                self.dispatch()
            except Fault as exc:
                self.send(exc.status, {"error": exc.message, "details": exc.details})
            except (ValueError, TypeError, KeyError):
                self.send(422, {"error": "Invalid request data"})
            except Exception:
                self.send(
                    500,
                    {
                        "error": "Operation failed. Reload and retry; no partial transaction was saved."
                    },
                )

        do_GET = handle_request
        do_POST = handle_request

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Generated isolated local application")
    parser.add_argument(
        "--demo", action="store_true", help="Explicitly enable synthetic loopback identities"
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument(
        "--integration-config", help="Server-only JSON configuration inside the data directory"
    )
    args = parser.parse_args()
    directory = Path(args.data_dir).resolve()
    temp = Path(tempfile.gettempdir()).resolve()
    if (
        not args.demo
        or temp not in directory.parents
        or not directory.name.startswith("studio-runtime-")
    ):
        parser.error(
            "Use --demo and a dedicated studio-runtime-* directory beneath the system temporary directory"
        )
    directory.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    if not schema["approved"]:
        parser.error("This specification is not approved; runtime launch is blocked")
    runtime = Runtime(schema, directory / "application.sqlite")
    gateway = None
    if args.integration_config:
        config_path = Path(args.integration_config).resolve()
        if directory not in config_path.parents:
            parser.error("Integration configuration must be inside the isolated data directory")
        from integrations import IntegrationGateway

        gateway = IntegrationGateway(
            runtime, json.loads(config_path.read_text(encoding="utf-8")), Fault
        )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(runtime, root, gateway))
    print(f"Generated local application: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
