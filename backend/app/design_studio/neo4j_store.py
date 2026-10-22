"""Explicitly selected Neo4j persistence. Never connects or migrates on import.

All writes are additive or scoped to the supplied Studio namespace. The workspace
node serializes revision checks and writes in one transaction. Immutable revision
documents and domain projections are committed together, never mirrored to SQLite.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from neo4j import READ_ACCESS
from app.design_studio.projects import OPERATIONS, preserve_lifecycle
from app.design_studio.store import DraftForbidden, DraftMissing, RevisionConflict, StorageCorrupt
from app.schemas.application_definition import ApplicationDefinition
from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.packs import content_sha256
from app.domain_knowledge.store import (
    VersionMissing,
    VersionConflict,
    check_transition,
    _meta,
    _sort_key,
)
from app.domain_knowledge.graph import write_plan


def now():
    return datetime.now(timezone.utc).isoformat()


class Neo4jDocuments:
    def __init__(self, driver, database, namespace):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{2,79}", namespace):
            raise ValueError("A fixed Studio namespace is required")
        self.driver, self.database, self.namespace = driver, database, namespace

    def read(self, work):
        with self.driver.session(
            database=self.database, default_access_mode=READ_ACCESS
        ) as session:
            return session.execute_read(work)

    def write(self, work):
        def locked(tx):
            row = tx.run(
                "MATCH (w:DSWorkspace {namespace:$ns}) SET w.lock=coalesce(w.lock,0)+1 RETURN w.schema AS schema",
                ns=self.namespace,
            ).single()
            if not row or row["schema"] != "studio-neo4j-v1":
                raise StorageCorrupt(
                    "Studio namespace is not initialized; no migration was attempted"
                )
            return work(tx)

        with self.driver.session(database=self.database) as session:
            return session.execute_write(locked)

    def get(self, tx, kind, identifier):
        row = tx.run(
            "MATCH (n:DSDocument {namespace:$ns,kind:$kind,document_id:$id}) RETURN n.payload AS payload",
            ns=self.namespace,
            kind=kind,
            id=identifier,
        ).single()
        return json.loads(row["payload"]) if row else None

    def items(self, tx, kind):
        return [
            json.loads(row["payload"])
            for row in tx.run(
                "MATCH (n:DSDocument {namespace:$ns,kind:$kind}) RETURN n.payload AS payload ORDER BY n.document_id",
                ns=self.namespace,
                kind=kind,
            )
        ]

    def put(self, tx, kind, identifier, value, immutable=False):
        if immutable and self.get(tx, kind, identifier) is not None:
            raise RevisionConflict("Immutable version already exists")
        tx.run(
            "MATCH (w:DSWorkspace {namespace:$ns}) MERGE (n:DSDocument {key:$key}) "
            "SET n.namespace=$ns,n.kind=$kind,n.document_id=$id,n.payload=$payload "
            "MERGE (w)-[:DS_HAS_DOCUMENT]->(n)",
            ns=self.namespace,
            key=f"{self.namespace}/{kind}/{identifier}",
            kind=kind,
            id=identifier,
            payload=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        ).consume()

    def project_domain(self, tx, pack):
        # Namespace every generated graph key; never attach to operational labels.
        def scoped(value):
            if isinstance(value, list):
                return [scoped(v) for v in value]
            if isinstance(value, dict):
                return {
                    k: (
                        self.namespace + "|" + v
                        if k in ("dk_key", "pack_key", "entity_key", "source", "target")
                        and isinstance(v, str)
                        else scoped(v)
                    )
                    for k, v in value.items()
                }
            return value

        for statement in write_plan(pack):
            params = scoped(statement["params"])
            if "props" in params:
                params["props"]["namespace"] = self.namespace
            for row in params.get("rows", []):
                if "props" in row:
                    row["props"]["namespace"] = self.namespace
            tx.run(statement["cypher"], params).consume()


class Neo4jProjectStore:
    def __init__(self, documents):
        self.docs = documents

    def _head(self, tx, owner, project_id):
        head = self.docs.get(tx, "project", project_id)
        if not head:
            raise DraftMissing()
        if head["owner"] != owner:
            raise DraftForbidden()
        return head

    def _revision(self, tx, project_id, revision):
        stored = self.docs.get(tx, "revision", f"{project_id}/{revision}")
        if not stored:
            raise StorageCorrupt("Missing immutable revision")
        result = ApplicationDefinition.model_validate(stored["definition"])
        if result.id != project_id or result.revision != revision:
            raise StorageCorrupt("Revision metadata mismatch")
        return result

    def list(self, owner):
        return self.docs.read(
            lambda tx: [
                self._revision(tx, p["id"], p["revision"])
                for p in self.docs.items(tx, "project")
                if p["owner"] == owner
            ]
        )

    def create(self, owner, definition):
        first = ApplicationDefinition.model_validate(
            {**definition.model_dump(mode="json"), "revision": 1}
        )

        def work(tx):
            if self.docs.get(tx, "project", first.id):
                raise RevisionConflict()
            self._save(tx, owner, first, "create", owner)
            return first

        return self.docs.write(work)

    def _save(self, tx, owner, definition, operation, actor):
        self.docs.put(
            tx,
            "revision",
            f"{definition.id}/{definition.revision}",
            {
                "definition": definition.model_dump(mode="json"),
                "revision": definition.revision,
                "actor": actor,
                "operation": operation,
                "at": now(),
            },
            immutable=True,
        )
        self.docs.put(
            tx,
            "project",
            definition.id,
            {"id": definition.id, "owner": owner, "revision": definition.revision},
        )
        tx.run(
            "MATCH (p:DSDocument {key:$p}),(r:DSDocument {key:$r}) MERGE (p)-[:DS_HAS_REVISION]->(r)",
            p=f"{self.docs.namespace}/project/{definition.id}",
            r=f"{self.docs.namespace}/revision/{definition.id}/{definition.revision}",
        ).consume()

    def current(self, owner, project_id):
        return self.docs.read(
            lambda tx: self._revision(tx, project_id, self._head(tx, owner, project_id)["revision"])
        )

    def update(
        self, owner, project_id, expected_revision, definition, operation="update", actor_id=None
    ):
        if operation not in OPERATIONS:
            raise ValueError("Unknown revision operation")

        def work(tx):
            head = self._head(tx, owner, project_id)
            if head["revision"] != expected_revision or definition.id != project_id:
                raise RevisionConflict()
            candidate = preserve_lifecycle(
                self._revision(tx, project_id, expected_revision), definition, operation
            )
            updated = ApplicationDefinition.model_validate(
                {**candidate.model_dump(mode="json"), "revision": expected_revision + 1}
            )
            self._save(tx, owner, updated, operation, actor_id or owner)
            return updated

        return self.docs.write(work)

    def history(self, owner, project_id):
        return self.docs.read(
            lambda tx: [
                self._revision(tx, project_id, r)
                for r in range(1, self._head(tx, owner, project_id)["revision"] + 1)
            ]
        )

    def audit_trail(self, owner, project_id):
        def work(tx):
            head = self._head(tx, owner, project_id)
            return [
                {
                    k: v
                    for k, v in self.docs.get(tx, "revision", f"{project_id}/{r}").items()
                    if k != "definition"
                }
                for r in range(1, head["revision"] + 1)
            ]

        return self.docs.read(work)


class Neo4jDomainStore:
    def __init__(self, documents):
        self.docs = documents

    def versions(self, pack_id=None):
        return self.docs.read(
            lambda tx: sorted(
                [
                    p["meta"]
                    for p in self.docs.items(tx, "domain")
                    if pack_id in (None, p["meta"]["pack_id"])
                ],
                key=lambda p: (p["pack_id"], _sort_key(p["version"])),
            )
        )

    def get(self, pack_id, version):
        row = self.docs.read(lambda tx: self.docs.get(tx, "domain", f"{pack_id}/{version}"))
        if not row:
            raise VersionMissing(f"{pack_id} {version}")
        return DomainPack.model_validate(row["content"]).model_copy(
            update={"status": row["meta"]["status"]}
        )

    def seed(self, pack):
        return self._insert(
            pack, "repository", "Versioned reference shipped with Studio", pack.status, "seed"
        )

    def propose(self, pack, actor, reason):
        return self._insert(pack, actor, reason, "under_review", "propose")

    def _insert(self, pack, actor, reason, status, action):
        pack = DomainPack.model_validate(pack.model_dump(mode="json"))

        def work(tx):
            identifier = f"{pack.id}/{pack.version}"
            existing = self.docs.get(tx, "domain", identifier)
            if existing:
                if existing["meta"]["content_sha256"] != content_sha256(pack):
                    raise VersionConflict("Use a new domain version for changed content")
                return {**existing["meta"], "idempotent": True}
            at = now()
            meta = _meta(pack, status, actor, reason, at)
            stored = pack.model_copy(update={"status": status})
            self.docs.put(
                tx,
                "domain",
                identifier,
                {"meta": meta, "content": stored.model_dump(mode="json")},
                immutable=True,
            )
            self.docs.project_domain(tx, stored)
            self.docs.put(
                tx,
                "domain_event",
                str(uuid4()),
                {
                    "pack_id": pack.id,
                    "version": pack.version,
                    "action": action,
                    "status": status,
                    "actor": actor,
                    "reason": reason,
                    "at": at,
                },
                immutable=True,
            )
            return {**meta, "idempotent": False}

        return self.docs.write(work)

    def transition(self, pack_id, version, to, actor, reason):
        def work(tx):
            identifier = f"{pack_id}/{version}"
            stored = self.docs.get(tx, "domain", identifier)
            if not stored:
                raise VersionMissing(identifier)
            check_transition(stored["meta"], to, actor)
            stored["meta"]["status"] = to
            self.docs.put(tx, "domain", identifier, stored)
            tx.run(
                "MATCH (p:DKPackVersion {dk_key:$key}) SET p.status=$status",
                key=f"{self.docs.namespace}|{pack_id}|{version}",
                status=to,
            ).consume()
            self.docs.put(
                tx,
                "domain_event",
                str(uuid4()),
                {
                    "pack_id": pack_id,
                    "version": version,
                    "action": "transition",
                    "status": to,
                    "actor": actor,
                    "reason": reason,
                    "at": now(),
                },
                immutable=True,
            )
            return stored["meta"]

        return self.docs.write(work)

    def audit(self, pack_id):
        return self.docs.read(
            lambda tx: sorted(
                [p for p in self.docs.items(tx, "domain_event") if p["pack_id"] == pack_id],
                key=lambda p: p["at"],
            )
        )
