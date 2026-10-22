"""Portable, opt-in signed record exchange. Configuration and secrets stay server-side."""

import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qs, urlsplit


class IntegrationGateway:
    def __init__(self, runtime, configurations, fault):
        self.runtime, self.fault, self.connections = runtime, fault, {}
        declared = {i["id"]: i for i in runtime.schema.get("integrations", [])}
        for config in configurations:
            if not config.get("enabled", False):
                continue
            integration = declared.get(config.get("id"))
            if not integration or config["id"] in self.connections:
                raise ValueError("Unknown or repeated integration")
            if (
                config.get("role") not in runtime.roles
                or not isinstance(config.get("tenant"), str)
                or not config["tenant"]
            ):
                raise ValueError("Integration needs a tenant and an application role")
            secret = os.environ.get(config.get("secret_env", ""), "")
            if len(secret) < 32:
                raise ValueError(
                    "Integration secret environment variable needs at least 32 characters"
                )
            mappings = config.get("entities", {})
            if not mappings or set(mappings) - set(integration["entity_ids"]):
                raise ValueError("Entity scope must be a subset of the integration contract")
            for entity, mapping in mappings.items():
                fields = {a["id"] for a in runtime.entities[entity]["attributes"]}
                fields.update(
                    r["field"] for r in runtime.schema["references"] if r["source"] == entity
                )
                if (
                    not mapping
                    or not all(
                        isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
                    )
                    or set(mapping.values()) - fields
                    or len(set(mapping.values())) != len(mapping)
                ):
                    raise ValueError("Field mapping must contain distinct declared fields")
            self.connections[config["id"]] = (config, integration, secret.encode())
        with runtime.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS integration_receipts (tenant TEXT, integration TEXT, event TEXT, digest TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(tenant,integration,event))"
            )

    @staticmethod
    def signature(secret, timestamp, method, target, raw=b""):
        message = f"{timestamp}\n{method}\n{target}\n".encode() + raw
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def exchange(self, integration_id, method, target, headers, raw=b""):
        fail = self.fault
        connection = self.connections.get(integration_id)
        if connection is None:
            raise fail(404, "Integration is not configured")
        config, contract, secret = connection
        stamp = headers.get("X-Studio-Timestamp", "")
        supplied = headers.get("X-Studio-Signature", "")
        try:
            fresh = abs(time.time() - int(stamp)) <= 300
        except (ValueError, TypeError):
            fresh = False
        if not fresh or not hmac.compare_digest(
            supplied, self.signature(secret, stamp, method, target, raw)
        ):
            raise fail(401, "Invalid or expired integration signature")
        user = {
            "tenant": config["tenant"],
            "role": config["role"],
            "actor": "integration:" + integration_id,
        }
        if method == "GET" and contract["direction"] in ("outbound", "bidirectional"):
            query = parse_qs(urlsplit(target).query, keep_blank_values=True)
            if set(query) - {"entity_id", "after"} or any(len(v) != 1 for v in query.values()):
                raise fail(422, "Supply one entity ID and an optional cursor")
            entity = query.get("entity_id", [""])[0]
            if entity not in config["entities"]:
                raise fail(403, "Entity is outside this integration mapping")
            try:
                cursor = int(query.get("after", ["0"])[0])
                if cursor < 0:
                    raise ValueError()
            except ValueError:
                raise fail(422, "Invalid export cursor") from None
            self.runtime.entity_access(user, entity)
            mapping = config["entities"][entity]
            with self.runtime.db() as db:
                rows = db.execute(
                    "SELECT rowid AS cursor,id,revision,data FROM records WHERE tenant=? AND entity=? AND rowid>? ORDER BY rowid LIMIT 100",
                    (user["tenant"], entity, cursor),
                ).fetchall()
                result = [
                    {
                        "record_id": r["id"],
                        "revision": r["revision"],
                        "data": {
                            external: json.loads(r["data"]).get(local)
                            for external, local in mapping.items()
                        },
                    }
                    for r in rows
                ]
                self.runtime.event(
                    db,
                    user,
                    entity,
                    "integration.export",
                    {"integration": integration_id, "count": len(rows)},
                )
            return {
                "records": result,
                "next_cursor": rows[-1]["cursor"] if rows else cursor,
                "note": "Snapshot pagination; restart from zero for a full refresh. This is not a change feed.",
            }
        if method != "POST" or contract["direction"] not in ("inbound", "bidirectional"):
            raise fail(405, "This integration does not accept inbound records")
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) - {
            "event_id",
            "entity_id",
            "data",
            "record_id",
            "expected_revision",
        }:
            raise fail(422, "Only event ID, entity, record data and revision may be supplied")
        event, entity, data = body.get("event_id"), body.get("entity_id"), body.get("data")
        if (
            not isinstance(event, str)
            or not 1 <= len(event) <= 200
            or entity not in config["entities"]
            or not isinstance(data, dict)
        ):
            raise fail(422, "Supply an event ID and a configured entity record")
        mapping = config["entities"][entity]
        if set(data) - set(mapping):
            raise fail(403, "Fields are outside this integration mapping")
        digest = hashlib.sha256(raw).hexdigest()
        with self.runtime.db() as db:
            previous = db.execute(
                "SELECT digest,response FROM integration_receipts WHERE tenant=? AND integration=? AND event=?",
                (user["tenant"], integration_id, event),
            ).fetchone()
            if previous:
                if previous["digest"] != digest:
                    raise fail(409, "Event ID was already used with a different payload")
                return json.loads(previous["response"])
            result = self.runtime.save_record(
                user,
                entity,
                {mapping[k]: v for k, v in data.items()},
                body.get("record_id"),
                body.get("expected_revision"),
                _connection=db,
            )
            self.runtime.event(
                db,
                user,
                f"{entity}/{result['id']}",
                "integration.receive",
                {"integration": integration_id, "event_id": event, "revision": result["revision"]},
            )
            # Responses contain receipt metadata only; they never disclose unmapped business fields.
            response = {
                "event_id": event,
                "record_id": result["id"],
                "revision": result["revision"],
            }
            db.execute(
                "INSERT INTO integration_receipts VALUES (?,?,?,?,?)",
                (user["tenant"], integration_id, event, digest, json.dumps(response)),
            )
            return response
