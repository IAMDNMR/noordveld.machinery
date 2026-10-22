"""Authoritative store of domain-pack versions, their lifecycle and audit trail.

Lifecycle: draft -> under_review -> approved -> deprecated (under_review may return to draft). A version's content never
changes once stored: a change is a new version. Approval must come from someone other than the proposer. Shipped packs
are seeded as approved versions by the repository itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Callable, Protocol

from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.packs import canonical_bytes, content_sha256, shipped_packs

SEED_ACTOR = "repository"
TRANSITIONS = {
    ("draft", "under_review"),
    ("under_review", "approved"),
    ("under_review", "draft"),
    ("approved", "deprecated"),
}


class StoreUnavailable(RuntimeError):
    """Writes need a configured store; none is approved for deployed environments."""


class VersionMissing(LookupError):
    pass


class VersionConflict(ValueError):
    pass


class GovernanceError(PermissionError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meta(pack: DomainPack, status: str, actor: str, reason: str, at: str) -> dict:
    return {
        "pack_id": pack.id,
        "version": pack.version,
        "status": status,
        "content_sha256": content_sha256(pack),
        "proposed_by": actor,
        "reason": reason,
        "created_at": at,
        "title": pack.title,
        "synthetic": pack.synthetic,
    }


def _sort_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class DomainStore(Protocol):
    def versions(self, pack_id: str | None = None) -> list[dict]: ...
    def get(self, pack_id: str, version: str) -> DomainPack: ...
    def propose(self, pack: DomainPack, actor: str, reason: str) -> dict: ...
    def transition(self, pack_id: str, version: str, to: str, actor: str, reason: str) -> dict: ...
    def audit(self, pack_id: str) -> list[dict]: ...


def check_transition(meta: dict, to: str, actor: str) -> None:
    if (meta["status"], to) not in TRANSITIONS:
        raise GovernanceError(f"Cannot move a {meta['status']} version to {to}")
    if to == "approved" and actor == meta["proposed_by"]:
        raise GovernanceError(
            "The proposer cannot approve their own change; another person must review it"
        )


def active(store: DomainStore) -> list[DomainPack]:
    """The latest approved version of each pack: what discovery and the explorer use."""
    latest: dict[str, dict] = {}
    for meta in store.versions():
        if meta["status"] == "approved" and (
            meta["pack_id"] not in latest
            or _sort_key(meta["version"]) > _sort_key(latest[meta["pack_id"]]["version"])
        ):
            latest[meta["pack_id"]] = meta
    return [store.get(meta["pack_id"], meta["version"]) for _, meta in sorted(latest.items())]


def active_version(store: DomainStore, pack_id: str) -> str | None:
    return next((pack.version for pack in active(store) if pack.id == pack_id), None)


class ReadOnlyDomainStore:
    """Default: the shipped packs only. No persistent store is approved for deployment, so every write is refused."""

    def __init__(self, packs: tuple[DomainPack, ...] | None = None):
        self._packs = {
            (pack.id, pack.version): pack
            for pack in (packs if packs is not None else shipped_packs())
        }

    def versions(self, pack_id: str | None = None) -> list[dict]:
        return [
            _meta(pack, pack.status, SEED_ACTOR, "Shipped with the application", "")
            for key, pack in sorted(self._packs.items())
            if pack_id in (None, key[0])
        ]

    def get(self, pack_id: str, version: str) -> DomainPack:
        if (pack_id, version) not in self._packs:
            raise VersionMissing(f"{pack_id} {version}")
        return self._packs[(pack_id, version)].model_copy(deep=True)

    def propose(self, pack: DomainPack, actor: str, reason: str) -> dict:
        raise StoreUnavailable("Domain knowledge changes need a configured store")

    def transition(self, pack_id: str, version: str, to: str, actor: str, reason: str) -> dict:
        raise StoreUnavailable("Domain knowledge changes need a configured store")

    def audit(self, pack_id: str) -> list[dict]:
        return [
            {
                "pack_id": meta["pack_id"],
                "version": meta["version"],
                "action": "seed",
                "status": meta["status"],
                "actor": SEED_ACTOR,
                "reason": meta["reason"],
                "at": "",
            }
            for meta in self.versions(pack_id)
        ]


class SqliteDomainStore:
    """Local, isolated store: one transaction per change; versions are insert-only."""

    SCHEMA_ID = "noordveld-domain-knowledge-v1"

    def __init__(self, path: Path, seed: tuple[DomainPack, ...] | None = None):
        self.path = Path(path)
        if not self.path.exists():
            setup = sqlite3.connect(self.path, isolation_level=None)
            try:
                setup.executescript("""
                    BEGIN;
                    CREATE TABLE dk_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE dk_versions (pack_id TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL, content_sha256 TEXT NOT NULL,
                        content TEXT NOT NULL, proposed_by TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(pack_id, version));
                    CREATE TABLE dk_audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, pack_id TEXT NOT NULL, version TEXT NOT NULL, action TEXT NOT NULL,
                        status TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL);
                    COMMIT;
                """)
            finally:
                setup.close()
            with self._db() as db:
                db.execute("INSERT INTO dk_meta VALUES ('schema_id', ?)", (self.SCHEMA_ID,))
                for pack in seed if seed is not None else shipped_packs():
                    self._insert(
                        db, pack, pack.status, SEED_ACTOR, "Shipped with the application", "seed"
                    )
        else:
            with self._db() as db:
                row = db.execute("SELECT value FROM dk_meta WHERE key='schema_id'").fetchone()
            if row is None or row[0] != self.SCHEMA_ID:
                raise StoreUnavailable(
                    "Unknown domain knowledge database; no migration was attempted"
                )

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _insert(
        self, db, pack: DomainPack, status: str, actor: str, reason: str, action: str
    ) -> dict:
        at = _now()
        stored = pack.model_copy(update={"status": status})
        db.execute(
            "INSERT INTO dk_versions VALUES (?,?,?,?,?,?,?,?)",
            (
                pack.id,
                pack.version,
                status,
                content_sha256(pack),
                canonical_bytes(stored).decode("utf-8"),
                actor,
                reason,
                at,
            ),
        )
        db.execute(
            "INSERT INTO dk_audit (pack_id, version, action, status, actor, reason, at) VALUES (?,?,?,?,?,?,?)",
            (pack.id, pack.version, action, status, actor, reason, at),
        )
        return _meta(pack, status, actor, reason, at)

    @staticmethod
    def _row(row) -> dict:
        pack = DomainPack.model_validate_json(row[4])
        return {
            "pack_id": row[0],
            "version": row[1],
            "status": row[2],
            "content_sha256": row[3],
            "proposed_by": row[5],
            "reason": row[6],
            "created_at": row[7],
            "title": pack.title,
            "synthetic": pack.synthetic,
        }

    def versions(self, pack_id: str | None = None) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM dk_versions WHERE ? IS NULL OR pack_id = ? ORDER BY pack_id, created_at",
                (pack_id, pack_id),
            ).fetchall()
        return sorted(
            (self._row(row) for row in rows),
            key=lambda meta: (meta["pack_id"], _sort_key(meta["version"])),
        )

    def get(self, pack_id: str, version: str) -> DomainPack:
        with self._db() as db:
            row = db.execute(
                "SELECT content, status FROM dk_versions WHERE pack_id=? AND version=?",
                (pack_id, version),
            ).fetchone()
        if row is None:
            raise VersionMissing(f"{pack_id} {version}")
        return DomainPack.model_validate_json(row[0]).model_copy(update={"status": row[1]})

    def propose(self, pack: DomainPack, actor: str, reason: str) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM dk_versions WHERE pack_id=? AND version=?", (pack.id, pack.version)
            ).fetchone()
            if row is not None:
                if row[3] == content_sha256(pack):
                    return {**self._row(row), "idempotent": True}
                raise VersionConflict(
                    f"{pack.id} {pack.version} already exists with different content; propose a new version"
                )
            return {
                **self._insert(db, pack, "under_review", actor, reason, "propose"),
                "idempotent": False,
            }

    def transition(self, pack_id: str, version: str, to: str, actor: str, reason: str) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM dk_versions WHERE pack_id=? AND version=?", (pack_id, version)
            ).fetchone()
            if row is None:
                raise VersionMissing(f"{pack_id} {version}")
            meta = self._row(row)
            check_transition(meta, to, actor)
            if (
                to == "deprecated"
                and not db.execute(
                    "SELECT 1 FROM dk_versions WHERE pack_id=? AND version<>? AND status='approved'",
                    (pack_id, version),
                ).fetchone()
            ):
                raise GovernanceError(
                    "This is the only approved version; approve a replacement before deprecating it"
                )
            db.execute(
                "UPDATE dk_versions SET status=? WHERE pack_id=? AND version=? AND status=?",
                (to, pack_id, version, meta["status"]),
            )
            db.execute(
                "INSERT INTO dk_audit (pack_id, version, action, status, actor, reason, at) VALUES (?,?,?,?,?,?,?)",
                (pack_id, version, f"transition:{to}", to, actor, reason, _now()),
            )
        return {**meta, "status": to}

    def audit(self, pack_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT pack_id, version, action, status, actor, reason, at FROM dk_audit WHERE pack_id=? ORDER BY seq",
                (pack_id,),
            ).fetchall()
        return [
            dict(zip(("pack_id", "version", "action", "status", "actor", "reason", "at"), row))
            for row in rows
        ]


# ── Dependencies and server-side domain permissions ──
# No identity provider distinguishes domain administrators yet. By default nobody holds a domain permission (and the
# default store is read-only anyway). The isolated local app grants them to its demo users explicitly.
PROPOSE, REVIEW, APPROVE, ADMINISTER = (
    "domain.propose",
    "domain.review",
    "domain.approve",
    "domain.administer",
)
TRANSITION_PERMISSION = {
    "under_review": PROPOSE,
    "draft": REVIEW,
    "approved": APPROVE,
    "deprecated": ADMINISTER,
}
DomainAccess = Callable[[str], frozenset[str]]


def get_domain_store() -> DomainStore:
    import os

    if os.environ.get("DESIGN_KNOWLEDGE_SOURCE", "local") == "neo4j":
        from app.knowledge_graph.neo4j import domain_store

        return domain_store()
    return ReadOnlyDomainStore()


def get_domain_access() -> DomainAccess:
    return lambda user_id: frozenset()
