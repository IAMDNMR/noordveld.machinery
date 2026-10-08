"""Where canonical records go: a Neo4j store for real runs and an in-memory store with the same contract for deterministic tests.

Both implement the same small interface, so the engine's planning (create / update / unchanged / verify) is identical against either.
Cypher is built only from labels, keys and relationship types that come from the registry (checked against a strict pattern); every value is a parameter.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Protocol

from neo4j import WRITE_ACCESS, unit_of_work

from app.canonical.registry import KINDS
from app.core.config import Settings
from app.graph.client import GraphClient

SAFE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CHUNK = 500
READ_CHUNK = 800
SRC_CANON = "SRC-CANON"
VOLATILE = {"ingestion_timestamp", "last_updated"}  # excluded from the canonical fingerprint


def _safe(*names: str) -> None:
    for n in names:
        if not SAFE.match(n):
            raise ValueError(f"unsafe identifier {n!r}")


class Store(Protocol):
    def fetch_nodes(self, label: str, key: str, ids: list[str]) -> dict[str, dict[str, Any]]: ...
    def resolve(self, kind: str, ids: list[str]) -> dict[str, tuple[str, str]]: ...
    def fetch_rels(self, type_: str, fl: tuple[str, str], tl: tuple[str, str], pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]: ...
    def upsert_nodes(self, label: str, key: str, rows: list[dict[str, Any]], create: bool = True, extra_labels: tuple[str, ...] = ()) -> int: ...
    def upsert_rels(self, type_: str, fl: tuple[str, str], tl: tuple[str, str], rows: list[dict[str, Any]]) -> int: ...
    def ensure_constraint(self, label: str, key: str) -> None: ...
    def fingerprint_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


class Neo4jStore:
    def __init__(self, settings: Settings, timeout: float = 120.0) -> None:
        self._s = settings
        self._g = GraphClient(settings)
        self._timeout = timeout

    def close(self) -> None:
        self._g.close()

    def _read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._g.driver.session(database=self._s.neo4j_database) as session:
            return session.execute_read(unit_of_work(timeout=self._timeout)(lambda tx: tx.run(query, params).data()))

    def _write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._g.driver.session(database=self._s.neo4j_database, default_access_mode=WRITE_ACCESS) as session:
            return session.execute_write(unit_of_work(timeout=self._timeout)(lambda tx: tx.run(query, params).data()))

    def fetch_nodes(self, label, key, ids):
        _safe(label, key)
        out: dict[str, dict[str, Any]] = {}
        for part in _chunks(sorted(set(ids)), READ_CHUNK):
            for r in self._read(f"MATCH (n:`{label}`) WHERE n.`{key}` IN $ids RETURN n.`{key}` AS id, properties(n) AS p", ids=part):
                out[r["id"]] = r["p"]
        return out

    def resolve(self, kind, ids):
        found: dict[str, tuple[str, str]] = {}
        for label, key in KINDS[kind]:
            todo = [i for i in set(ids) if i not in found]
            for part in _chunks(sorted(todo), READ_CHUNK):
                for r in self._read(f"MATCH (n:`{label}`) WHERE n.`{key}` IN $ids RETURN n.`{key}` AS id", ids=part):
                    found.setdefault(r["id"], (label, key))
        return found

    def fetch_rels(self, type_, fl, tl, pairs):
        _safe(type_, *fl, *tl)
        out: dict[tuple[str, str], dict[str, Any]] = {}
        for part in _chunks(sorted(set(pairs)), READ_CHUNK):
            rows = self._read(f"UNWIND $pairs AS pr MATCH (a:`{fl[0]}` {{`{fl[1]}`: pr[0]}})-[x:`{type_}`]->(b:`{tl[0]}` {{`{tl[1]}`: pr[1]}}) RETURN pr[0] AS f, pr[1] AS t, properties(x) AS p",
                              pairs=[list(p) for p in part])
            for r in rows:
                out[(r["f"], r["t"])] = r["p"]
        return out

    def upsert_nodes(self, label, key, rows, create=True, extra_labels=()):
        _safe(label, key, *extra_labels)
        verb = "MERGE" if create else "MATCH"
        labels = "".join(f", n:`{x}`" for x in extra_labels)
        q = (f"UNWIND $rows AS r {verb} (n:`{label}` {{`{key}`: r.id}}) " + ("ON CREATE SET n += r.create " if create else "") + f"SET n += r.props{labels} RETURN count(n) AS n")
        return sum(self._write(q, rows=part)[0]["n"] for part in _chunks(rows, CHUNK))

    def upsert_rels(self, type_, fl, tl, rows):
        _safe(type_, *fl, *tl)
        q = (f"UNWIND $rows AS r MATCH (a:`{fl[0]}` {{`{fl[1]}`: r.f}}) MATCH (b:`{tl[0]}` {{`{tl[1]}`: r.t}}) "
             f"MERGE (a)-[x:`{type_}`]->(b) ON CREATE SET x += r.create SET x += r.props RETURN count(x) AS n")
        return sum(self._write(q, rows=part)[0]["n"] for part in _chunks(rows, CHUNK))

    def ensure_constraint(self, label, key):
        _safe(label, key)
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", label).lower()
        self._write(f"CREATE CONSTRAINT {snake}_id_unique IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.`{key}` IS UNIQUE")

    def fingerprint_rows(self):
        nodes = self._read("MATCH (n) WHERE n.source_id = $s RETURN labels(n)[0] AS l, properties(n) AS p ORDER BY l, coalesce(n.source_record_id, ''), elementId(n)", s=SRC_CANON)
        rels = self._read("MATCH ()-[x]->() WHERE x.source_id = $s RETURN type(x) AS t, properties(x) AS p ORDER BY t, coalesce(x.rel_id, '')", s=SRC_CANON)
        return nodes, rels


class MemoryStore:
    """Plain dictionaries with the same contract as Neo4jStore. Nodes are unique per (label, id); a relationship per (type, from, to)."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], dict[str, Any]] = {}
        self.rels: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        self.keys: dict[str, str] = {}
        self.labels: dict[tuple[str, str], set[str]] = {}  # second labels a node was given
        self.writes = 0  # statements that changed anything: a dry run must leave it at zero

    def seed_node(self, label: str, key: str, props: dict[str, Any]) -> None:
        self.keys[label] = key
        self.nodes[(label, props[key])] = dict(props)

    def fetch_nodes(self, label, key, ids):
        self.keys.setdefault(label, key)
        return {i: copy.deepcopy(self.nodes[(label, i)]) for i in set(ids) if (label, i) in self.nodes}

    def resolve(self, kind, ids):
        out: dict[str, tuple[str, str]] = {}
        for label, key in KINDS[kind]:
            for i in ids:
                if i not in out and (label, i) in self.nodes:
                    out[i] = (label, key)
        return out

    def fetch_rels(self, type_, fl, tl, pairs):
        return {p: copy.deepcopy(self.rels[(type_, fl[0], p[0], tl[0], p[1])]) for p in set(pairs) if (type_, fl[0], p[0], tl[0], p[1]) in self.rels}

    def upsert_nodes(self, label, key, rows, create=True, extra_labels=()):
        self.keys[label] = key
        n = 0
        for r in rows:
            k = (label, r["id"])
            if k not in self.nodes:
                if not create:
                    continue
                self.nodes[k] = {key: r["id"], **r["create"]}
            self.nodes[k].update(r["props"])
            self.labels.setdefault(k, set()).update(extra_labels)
            n += 1
        self.writes += 1 if rows else 0
        return n

    def upsert_rels(self, type_, fl, tl, rows):
        n = 0
        for r in rows:
            if (fl[0], r["f"]) not in self.nodes or (tl[0], r["t"]) not in self.nodes:
                continue
            k = (type_, fl[0], r["f"], tl[0], r["t"])
            if k not in self.rels:
                self.rels[k] = dict(r["create"])
            self.rels[k].update(r["props"])
            n += 1
        self.writes += 1 if rows else 0
        return n

    def ensure_constraint(self, label, key):
        self.keys.setdefault(label, key)

    def fingerprint_rows(self):
        nodes = [{"l": lab, "p": p} for (lab, _), p in sorted(self.nodes.items(), key=lambda kv: (kv[0][0], str(kv[1].get("source_record_id", "")), kv[0][1])) if p.get("source_id") == SRC_CANON]
        rels = [{"t": k[0], "p": p} for k, p in sorted(self.rels.items(), key=lambda kv: (kv[0][0], str(kv[1].get("rel_id", "")))) if p.get("source_id") == SRC_CANON]
        return nodes, rels
