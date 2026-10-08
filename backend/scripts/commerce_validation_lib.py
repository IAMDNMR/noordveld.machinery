"""Building blocks of scripts/commerce_live_validate.py: a read-only graph guard, connectivity, graph sources (live Neo4j and an in-memory twin of the canonical files),
the field-level canonical <-> graph comparison driven by the dataset registry, the entity inventory, and the snapshot.

READ-ONLY. Nothing in this module can write to the graph: the only graph handle it uses is `ReadOnlyGraph`, which exposes `read` alone and refuses any query that contains a
write keyword. A static test (tests/test_commerce_validator.py) also checks the sources of both validator files.

The comparison uses the SAME mapping the ingestion uses (app/canonical/registry.py: canonical field -> graph property, canonical relationships) so a difference is a real difference
between what the canonical files say and what the graph holds, never a difference in how the two were read.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "eu_foundation"))

from app.canonical.engine import Engine  # noqa: E402  (only its static helpers are used; no store is created)
from app.canonical.export import FITMENT_MAP  # noqa: E402
from app.canonical.io import CANON_DIR, load_rows  # noqa: E402
from app.canonical.registry import BY_NAME, KINDS, SPECS, DatasetSpec  # noqa: E402

APP = "APP-SESSION"
SRC_CANON = "SRC-CANON"
BOOKKEEPING = ("ingestion_timestamp", "last_updated", "canonical_dataset", "canonical_schema_version", "source_file", "source_name", "enrichment_batch")
PROTECTED_STATUSES = ("SOURCE_DERIVED", "DERIVED", "REAL")
PROTECTED_CYPHER = "(x.data_status IN ['SOURCE_DERIVED','DERIVED','REAL'] OR (x.data_status = 'USER_PROVIDED' AND coalesce(x.source_id, '') <> $app))"
# The datasets that are the supplied, protected catalogue: compared with no tolerance beyond the three listed rules.
PROTECTED_DATASETS = ("machines", "parts", "categories", "specifications", "plants", "legacy_part_mappings", "assemblies")
PROTECTED_ALLOWED_RULES = ("LIST_ORDER", "NUMERIC_TYPE", "NUMERIC_TOLERANCE", "SPEC_NAME_CASEFOLD")

# ── the approved normalisation rules. Nothing else is ever treated as harmless. ─────────────────
RULES: dict[str, str] = {
    "IGNORED_BOOKKEEPING": "Import bookkeeping stamped by the ingestion (ingestion_timestamp, last_updated, canonical_dataset, canonical_schema_version, source_file, source_name, enrichment_batch). Never business data; never compared.",
    "LIST_ORDER": "A list holds the same members in a different order (lists are sets of values: aliases, regions, conditions).",
    "NUMERIC_TYPE": "An integer and a float with the same value (5 and 5.0).",
    "NUMERIC_TOLERANCE": "Two floats within 1e-9 (binary representation).",
    "EMPTY_EQUIVALENT": "Canonical models turn blank cells into null / empty list; the graph may omit the property. Null, empty string and empty list are one 'no value'. Not allowed for protected datasets.",
    "DATE_REPRESENTATION": "The same calendar date written as YYYY-MM-DD in one place and as a midnight timestamp in the other. Not allowed for protected datasets.",
    "TIMESTAMP_FORMAT": "The same instant written in two ISO formats ('T' or space separator, 'Z' or +00:00). Not allowed for protected datasets.",
    "COUNTRY_CODE_CASE": "Country codes differ only in letter case (the ingestion stores upper case). Not allowed for protected datasets.",
    "SPEC_NAME_CASEFOLD": "A specification name differs only in case/spacing; the canonical name is a normalisation and the original text is kept in source_text (registry: casefold=('name',)).",
    "FITMENT_ENUM_MAP": "The supplied FITS relationship says CONFIRMED where the canonical vocabulary says APPROVED (app.canonical.export.FITMENT_MAP).",
    "SUPPLIER_ACTIVE_MAP": "The supplied SUPPLIED_BY relationship says ACTIVE* where the canonical vocabulary says APPROVED (app.canonical.export approved_sources).",
}

MATCH, NORMALIZATION_ONLY, VALUE_MISMATCH, TYPE_MISMATCH, MISSING_IN_GRAPH, MISSING_IN_CANONICAL, IGNORED_BOOKKEEPING = (
    "MATCH", "NORMALIZATION_ONLY", "VALUE_MISMATCH", "TYPE_MISMATCH", "MISSING_IN_GRAPH", "MISSING_IN_CANONICAL", "IGNORED_BOOKKEEPING")
FAILING = (VALUE_MISMATCH, TYPE_MISMATCH, MISSING_IN_GRAPH, MISSING_IN_CANONICAL)


# ═══ read-only guard ═══════════════════════════════════════════════════════════════════════════════
class WriteAttempt(Exception):
    """A query that could change the graph was handed to the validator's graph handle."""


_WRITE = re.compile(r"\b(create|merge|delete|detach|set|remove|drop|foreach|load|call)\b", re.IGNORECASE)


def assert_read_only(query: str) -> None:
    stripped = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", "", query)
    m = _WRITE.search(stripped)
    if m:
        raise WriteAttempt(f"query contains the write keyword {m.group(1).upper()!r}: {query[:80]!r}")


class ReadOnlyGraph:
    """The only graph handle the validator uses. `read` runs through GraphClient.read (READ_ACCESS sessions) after the keyword guard; there is no write method, so
    passing it to code that tries to write fails with AttributeError, and a write-looking query raises WriteAttempt before it is sent. Every query is counted."""

    def __init__(self, graph: Any) -> None:
        self._g = graph
        self.queries = 0
        self.blocked: list[str] = []

    def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        try:
            assert_read_only(query)
        except WriteAttempt as exc:
            self.blocked.append(str(exc))
            raise
        self.queries += 1
        return self._g.read(query, **params)

    def close(self) -> None:
        self._g.close()


# ═══ connectivity ══════════════════════════════════════════════════════════════════════════════════
def connectivity(settings: Any, graph_factory: Any = None) -> dict[str, Any]:
    """host / port / DNS / TCP / authentication / database, in that order; each later step is 'not_tested' when an earlier one failed. No secret is read into the report."""
    out: dict[str, Any] = {"host": None, "port": 7687, "scheme": None, "configured": bool(settings.graph_configured), "dns_resolved": False, "tcp_reachable": False,
                           "authentication": "not_tested", "database_reachable": False, "error_class": None}
    if not settings.graph_configured:
        out["error_class"] = "NotConfigured"
        return out
    u = urlparse(settings.neo4j_uri)
    out["host"], out["scheme"] = u.hostname, u.scheme
    try:
        socket.gethostbyname(u.hostname or "")
        out["dns_resolved"] = True
    except OSError as exc:
        out["error_class"] = type(exc).__name__
        return out
    try:
        socket.create_connection((u.hostname, out["port"]), timeout=6).close()
        out["tcp_reachable"] = True
    except OSError as exc:
        out["error_class"] = type(exc).__name__
        return out
    from app.core.exceptions import GraphUnavailableError
    from app.graph.client import GraphClient

    g = graph_factory() if graph_factory else GraphClient(settings)
    try:
        g.read("RETURN 1 AS ok")
        out["authentication"], out["database_reachable"] = "ok", True
    except GraphUnavailableError as exc:
        name = str(exc)
        out["error_class"] = name
        out["authentication"] = "failed" if name == "AuthError" else "not_tested"
        out["database_reachable"] = False
    finally:
        g.close()
    return out


# ═══ graph sources ═════════════════════════════════════════════════════════════════════════════════
def _safe(*names: str) -> None:
    for n in names:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n or ""):
            raise ValueError(f"unsafe identifier {n!r}")


class GraphSource(Protocol):
    def nodes(self, label: str, key: str, ids: list[str]) -> dict[str, dict[str, Any]]: ...
    def rels(self, type_: str, fl: tuple[str, str], tl: tuple[str, str], pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]: ...
    def resolve(self, kind: str, ids: list[str]) -> dict[str, tuple[str, str]]: ...
    def node_ids(self, label: str, key: str, dataset: str | None = None, exclude_app: bool = False, require_property: str | None = None) -> set[str]: ...
    def app_written(self, label: str) -> int: ...
    def rel_ids(self, type_: str, dataset: str | None = None) -> set[str]: ...
    def part_aliases(self) -> dict[str, list[str]]: ...
    def part_categories(self) -> dict[str, tuple[str | None, str | None]]: ...
    def fits(self) -> list[dict[str, Any]]: ...
    def supplied_by(self) -> list[dict[str, Any]]: ...
    def snapshot(self) -> dict[str, Any]: ...


CHUNK = 400


def _chunks(items: list, n: int = CHUNK):
    for i in range(0, len(items), n):
        yield items[i:i + n]


class CypherSource:
    """The live Neo4j graph, through ReadOnlyGraph."""

    def __init__(self, graph: ReadOnlyGraph) -> None:
        self.g = graph

    def nodes(self, label, key, ids):
        _safe(label, key)
        out: dict[str, dict[str, Any]] = {}
        for part in _chunks(sorted(set(ids))):
            for r in self.g.read(f"MATCH (n:`{label}`) WHERE n.`{key}` IN $ids RETURN n.`{key}` AS id, properties(n) AS p", ids=part):
                out[r["id"]] = r["p"]
        return out

    def rels(self, type_, fl, tl, pairs):
        _safe(type_, *fl, *tl)
        out: dict[tuple[str, str], dict[str, Any]] = {}
        for part in _chunks(sorted(set(pairs))):
            rows = self.g.read(f"UNWIND $pairs AS pr MATCH (a:`{fl[0]}` {{`{fl[1]}`: pr[0]}})-[x:`{type_}`]->(b:`{tl[0]}` {{`{tl[1]}`: pr[1]}}) RETURN pr[0] AS f, pr[1] AS t, properties(x) AS p",
                               pairs=[list(p) for p in part])
            for r in rows:
                out[(r["f"], r["t"])] = r["p"]
        return out

    def resolve(self, kind, ids):
        found: dict[str, tuple[str, str]] = {}
        for label, key in KINDS[kind]:
            todo = [i for i in set(ids) if i not in found]
            for part in _chunks(sorted(todo)):
                for r in self.g.read(f"MATCH (n:`{label}`) WHERE n.`{key}` IN $ids RETURN n.`{key}` AS id", ids=part):
                    found.setdefault(r["id"], (label, key))
        return found

    def node_ids(self, label, key, dataset=None, exclude_app=False, require_property=None):
        _safe(label, key)
        need = ""
        if require_property:
            _safe(require_property)
            need = f" AND n.`{require_property}` IS NOT NULL"
        rows = self.g.read(f"MATCH (n:`{label}`) WHERE ($ds IS NULL OR n.canonical_dataset = $ds) AND (NOT $excl OR coalesce(n.source_id, '') <> $app){need} RETURN n.`{key}` AS id",
                           ds=dataset, excl=exclude_app, app=APP)
        return {r["id"] for r in rows if r["id"] is not None}

    def app_written(self, label):
        _safe(label)
        return self.g.read(f"MATCH (n:`{label}`) WHERE n.source_id = $app RETURN count(n) AS n", app=APP)[0]["n"]

    def rel_ids(self, type_, dataset=None):
        _safe(type_)
        rows = self.g.read(f"MATCH ()-[r:`{type_}`]->() WHERE ($ds IS NULL OR r.canonical_dataset = $ds) AND coalesce(r.source_id, '') <> $app RETURN r.rel_id AS id", ds=dataset, app=APP)
        return {r["id"] for r in rows if r["id"] is not None}

    def part_aliases(self):
        rows = self.g.read("MATCH (p:Part) OPTIONAL MATCH (p)-[:HAS_ALIAS]->(a:SearchAlias) RETURN p.part_id AS id, collect(a.alias) AS aliases")
        return {r["id"]: sorted({a for a in r["aliases"] if a}) for r in rows}

    def part_categories(self):
        rows = self.g.read("MATCH (p:Part) OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category) OPTIONAL MATCH (p)-[:IN_SUBCATEGORY]->(s:Category) "
                           "RETURN p.part_id AS id, c.category_id AS cat, s.category_id AS sub")
        return {r["id"]: (r["cat"], r["sub"]) for r in rows}

    def fits(self):
        return [{"part": r["part"], "machine": r["machine"], "props": r["p"]} for r in
                self.g.read("MATCH (p:Part)-[f:FITS]->(m:Machine) RETURN p.part_id AS part, m.machine_id AS machine, properties(f) AS p")]

    def supplied_by(self):
        return [{"part": r["part"], "supplier": r["sup"], "props": r["p"]} for r in
                self.g.read("MATCH (p:Part)-[x:SUPPLIED_BY]->(s:Supplier) RETURN p.part_id AS part, s.supplier_id AS sup, properties(x) AS p")]

    def snapshot(self):
        from audit_before import NODE_QUERY, REL_QUERY, fingerprint

        one = lambda q, **p: self.g.read(q, **p)[0]["n"]  # noqa: E731
        nodes = self.g.read(NODE_QUERY, app=APP)
        rels = self.g.read(REL_QUERY, app=APP)
        canon_nodes = self.g.read("MATCH (n) WHERE n.source_id = $s RETURN labels(n)[0] AS l, properties(n) AS p ORDER BY l, coalesce(n.source_record_id, ''), elementId(n)", s=SRC_CANON)
        canon_rels = self.g.read("MATCH ()-[x]->() WHERE x.source_id = $s RETURN type(x) AS t, properties(x) AS p ORDER BY t, coalesce(x.rel_id, '')", s=SRC_CANON)
        return {"source": "NEO4J", "node_count": one("MATCH (n) RETURN count(n) AS n"), "relationship_count": one("MATCH ()-[r]->() RETURN count(r) AS n"),
                "protected_node_count": len(nodes), "protected_relationship_count": len(rels), "integrity_checksum": fingerprint(nodes, rels),
                "src_canon_graph_fingerprint": canon_fingerprint(canon_nodes, canon_rels),
                "label_counts": {r["l"]: r["n"] for r in self.g.read("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n ORDER BY l")},
                "relationship_type_counts": {r["t"]: r["n"] for r in self.g.read("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY t")}}


VOLATILE = ("ingestion_timestamp", "last_updated")


def canon_fingerprint(nodes: list[dict[str, Any]], rels: list[dict[str, Any]]) -> str:
    """Same recipe as app.canonical.integrity.graph_fingerprint, over rows already read (so no Store object, and no write-capable handle, is involved)."""
    h = hashlib.sha256()
    for r in nodes:
        h.update(json.dumps({"l": r["l"], "p": {k: v for k, v in r["p"].items() if k not in VOLATILE}}, sort_keys=True, default=str).encode())
    for r in rels:
        h.update(json.dumps({"t": r["t"], "p": {k: v for k, v in r["p"].items() if k not in VOLATILE}}, sort_keys=True, default=str).encode())
    return h.hexdigest()


# ── an in-memory twin of the canonical files, shaped like the graph ──────────────────────────────
class MemorySource:
    """What a perfectly synchronised graph would hold for the canonical files, built from the registry mapping. Used by OFFLINE mode and by the validator's own tests (which then
    damage it on purpose to prove that a difference is reported). It is NOT Neo4j and nothing compared against it is ever reported as live-verified."""

    def __init__(self) -> None:
        self.n: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)  # (label, key) -> id -> props
        self.r: dict[tuple[str, str, str], dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)  # (type, from label, to label) -> (f, t) -> props
        self.aliases: dict[str, list[str]] = {}
        self.categories: dict[str, tuple[str | None, str | None]] = {}
        self.fits_: list[dict[str, Any]] = []
        self.supplied_: list[dict[str, Any]] = []
        self._ids: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
        self.app_nodes: Counter = Counter()

    @classmethod
    def from_files(cls, root: Path = CANON_DIR) -> MemorySource:
        m = cls()
        recs = {s.name: _records(s, root)[0] for s in SPECS}
        # pass 1: nodes
        for spec in SPECS:
            for rec in recs[spec.name]:
                for t in spec.targets:
                    label, key, gid = Engine._identity(t, rec)
                    props = {gp: v for cf, gp in t.fields.items() if (v := getattr(rec, cf, None)) not in (None, [])}
                    props.update({"data_status": rec.data_status, "source_record_id": rec.source_record_id or rec.id, "canonical_dataset": spec.name, "source_id": SRC_CANON, key: gid,
                                  "ingestion_timestamp": "2026-01-01T00:00:00Z"})
                    m.n[(label, key)].setdefault(gid, {}).update(props)  # the ingestion SETs n += props: several datasets can describe one node
                    for kind, cands in KINDS.items():
                        if (label, key) in cands:
                            m._ids[kind][gid] = (label, key)
        m._add_referenced_only(recs)
        # pass 2: relationships (record-level and RelDef edges)
        for spec in SPECS:
            for rec in recs[spec.name]:
                if spec.rel:
                    rt = spec.rel
                    fl = m._ids[rt.from_kind].get(getattr(rec, rt.from_field))
                    to_kind = rt.to_kind or rt.to_kind_from[1][getattr(rec, rt.to_kind_from[0])]
                    tl = m._ids[to_kind].get(getattr(rec, rt.to_field))
                    if fl and tl:
                        props = {gp: v for cf, gp in rt.fields.items() if (v := getattr(rec, cf, None)) not in (None, [])}
                        props.update({"rel_id": rt.rel_id.format(id=rec.id), "data_status": rec.data_status, "source_record_id": rec.source_record_id or rec.id, "canonical_dataset": spec.name,
                                      "source_id": SRC_CANON})
                        m.r[(rt.type, fl[0], tl[0])][(getattr(rec, rt.from_field), getattr(rec, rt.to_field))] = props
                for t in spec.targets:
                    this = Engine._identity(t, rec)
                    for rd in t.rels:
                        val = getattr(rec, rd.field, None)
                        if val is None:
                            continue
                        kind = rd.kind or rd.kind_from[1][getattr(rec, rd.kind_from[0])]
                        other = m._ids[kind].get(val)
                        if not other:
                            continue
                        f, tt = ((other, (this[0], this[2])) if rd.reverse else ((this[0], this[2]), other))
                        fl, tl = (f[0], tt[0]) if rd.reverse else (this[0], other[0])
                        pair = (val, this[2]) if rd.reverse else (this[2], val)
                        props = {"rel_id": f"{rd.type}:{this[2]}:{val}", "data_status": rec.data_status, "canonical_dataset": spec.name, "source_id": SRC_CANON}
                        props.update({p: getattr(rec, p) for p in rd.props if getattr(rec, p, None) is not None})
                        m.r[(rd.type, fl, tl)][pair] = props
        # the supplied catalogue relationships the registry does not own
        for p in recs["parts"]:
            m.aliases[p.part_id] = sorted(set(p.aliases))
            m.categories[p.part_id] = (p.category_id, p.subcategory_id)
        inverse = {v: k for k, v in FITMENT_MAP.items()}
        for f in recs["fitment"]:
            m.fits_.append({"part": f.part_id, "machine": f.machine_id, "props": {"rel_id": f.fitment_id, "fitment_status": inverse.get(f.fitment_status, f.fitment_status), "fitment_type": f.fitment_rule,
                                                                                    "data_status": f.data_status, "source_record_id": f.source_record_id}})
        for a in recs["approved_sources"]:
            if a.source_kind == "SUPPLIER":
                m.supplied_.append({"part": a.part_id, "supplier": a.source_id, "props": {"relationship_status": "ACTIVE_DEMO", "rel_id": f"SUPPLIED_BY:{a.part_id}>{a.source_id}"}})
        return m

    def _add_referenced_only(self, recs: dict[str, list[Any]]) -> None:
        """Entities the registry only REFERENCES (legs, assemblies, legacy references, variants, carriers ...): the supplied graph already holds them, so the twin holds a bare node each."""
        wanted: list[tuple[str, str]] = []
        for spec in SPECS:
            for rec in recs[spec.name]:
                if spec.rel:
                    rt = spec.rel
                    wanted.append((rt.from_kind, getattr(rec, rt.from_field)))
                    wanted.append((rt.to_kind or rt.to_kind_from[1][getattr(rec, rt.to_kind_from[0])], getattr(rec, rt.to_field)))
                for t in spec.targets:
                    for rd in t.rels:
                        val = getattr(rec, rd.field, None)
                        if val is not None:
                            wanted.append((rd.kind or rd.kind_from[1][getattr(rec, rd.kind_from[0])], val))
        for kind, gid in wanted:
            if gid not in self._ids[kind]:
                label, key = KINDS[kind][0]
                self.n[(label, key)].setdefault(gid, {key: gid, "data_status": "SYNTHETIC_DEMO"})
                self._ids[kind][gid] = (label, key)

    # ── GraphSource ──
    def nodes(self, label, key, ids):
        return {i: p for i in set(ids) if (p := self.n.get((label, key), {}).get(i)) is not None}

    def rels(self, type_, fl, tl, pairs):
        store = self.r.get((type_, fl[0], tl[0]), {})
        return {p: store[p] for p in set(pairs) if p in store}

    def resolve(self, kind, ids):
        return {i: self._ids[kind][i] for i in set(ids) if i in self._ids[kind]}

    def node_ids(self, label, key, dataset=None, exclude_app=False, require_property=None):
        return {i for i, p in self.n.get((label, key), {}).items() if (dataset is None or p.get("canonical_dataset") == dataset) and (require_property is None or p.get(require_property) is not None)}

    def app_written(self, label):
        return self.app_nodes[label]

    def rel_ids(self, type_, dataset=None):
        out = {f["props"]["rel_id"] for f in self.fits_} if type_ == "FITS" and dataset is None else set()
        for (t, _, _), d in self.r.items():
            if t == type_:
                out |= {p["rel_id"] for p in d.values() if dataset is None or p.get("canonical_dataset") == dataset}
        return out

    def part_aliases(self):
        return dict(self.aliases)

    def part_categories(self):
        return dict(self.categories)

    def fits(self):
        return list(self.fits_)

    def supplied_by(self):
        return list(self.supplied_)

    def snapshot(self):
        nodes = [{"l": lab, "p": p} for (lab, _), d in sorted(self.n.items()) for _, p in sorted(d.items()) if p.get("data_status") in PROTECTED_STATUSES]
        rels = [{"t": t, "p": p} for (t, _, _), d in sorted(self.r.items()) for _, p in sorted(d.items(), key=lambda kv: str(kv[1].get("rel_id"))) if p.get("data_status") in PROTECTED_STATUSES]
        cn = [{"l": lab, "p": p} for (lab, _), d in sorted(self.n.items()) for _, p in sorted(d.items())]
        cr = [{"t": t, "p": p} for (t, _, _), d in sorted(self.r.items()) for _, p in sorted(d.items(), key=lambda kv: str(kv[1].get("rel_id")))]
        h = hashlib.sha256()
        for x in nodes:
            h.update(json.dumps(x, sort_keys=True, default=str).encode())
        for x in rels:
            h.update(json.dumps(x, sort_keys=True, default=str).encode())
        labels: Counter = Counter()
        for (lab, _), d in self.n.items():
            labels[lab] += len(d)
        types: Counter = Counter()
        for (t, _, _), d in self.r.items():
            types[t] += len(d)
        return {"source": "MEMORY_TWIN", "node_count": sum(labels.values()), "relationship_count": sum(types.values()), "protected_node_count": len(nodes), "protected_relationship_count": len(rels),
                "integrity_checksum": h.hexdigest(), "src_canon_graph_fingerprint": canon_fingerprint(cn, cr), "label_counts": dict(sorted(labels.items())),
                "relationship_type_counts": dict(sorted(types.items()))}


def _records(spec: DatasetSpec, root: Path) -> tuple[list[Any], int]:
    """(validated canonical records, number of rows that failed validation)."""
    ok, bad = [], 0
    rows, _ = load_rows(spec, root)
    for r in rows:
        try:
            ok.append(spec.model.model_validate(r))
        except Exception:  # noqa: BLE001
            bad += 1
    return ok, bad


# ═══ value comparison ══════════════════════════════════════════════════════════════════════════════
def _empty(v: Any) -> bool:
    return v is None or v == "" or v == []


def _ts(v: Any) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify(canonical: Any, graph: Any, field_name: str = "", *, casefold: bool = False, protected: bool = False) -> tuple[str, str | None]:
    """(difference type, rule applied). A rule that is not approved for the dataset is NOT applied: the difference stays a mismatch."""
    allowed = (lambda rule: rule in PROTECTED_ALLOWED_RULES) if protected else (lambda rule: True)
    if _empty(canonical) and _empty(graph):
        if canonical is None and graph is None or canonical == graph:
            return MATCH, None
        return (NORMALIZATION_ONLY, "EMPTY_EQUIVALENT") if allowed("EMPTY_EQUIVALENT") else (VALUE_MISMATCH, None)
    if _empty(graph):
        return MISSING_IN_GRAPH, None
    if _empty(canonical):
        return MISSING_IN_CANONICAL, None
    if isinstance(canonical, list) or isinstance(graph, list):
        if not (isinstance(canonical, list) and isinstance(graph, list)):
            return TYPE_MISMATCH, None
        if canonical == graph:
            return MATCH, None
        return (NORMALIZATION_ONLY, "LIST_ORDER") if sorted(map(str, canonical)) == sorted(map(str, graph)) else (VALUE_MISMATCH, None)
    if isinstance(canonical, bool) or isinstance(graph, bool):
        return (MATCH, None) if canonical is graph else (TYPE_MISMATCH if type(canonical) is not type(graph) else VALUE_MISMATCH, None)
    if isinstance(canonical, (int, float)) and isinstance(graph, (int, float)):
        if canonical == graph:
            return (MATCH, None) if type(canonical) is type(graph) else (NORMALIZATION_ONLY, "NUMERIC_TYPE")
        return (NORMALIZATION_ONLY, "NUMERIC_TOLERANCE") if abs(float(canonical) - float(graph)) < 1e-9 else (VALUE_MISMATCH, None)
    if type(canonical) is not type(graph):
        return TYPE_MISMATCH, None
    if canonical == graph:
        return MATCH, None
    if isinstance(canonical, str):
        if field_name == "country_code" and canonical.upper() == graph.upper():
            return (NORMALIZATION_ONLY, "COUNTRY_CODE_CASE") if allowed("COUNTRY_CODE_CASE") else (VALUE_MISMATCH, None)
        if casefold and " ".join(canonical.split()).casefold() == " ".join(graph.split()).casefold():
            return NORMALIZATION_ONLY, "SPEC_NAME_CASEFOLD"
        date_only = re.compile(r"\d{4}-\d{2}-\d{2}")
        a, b = _ts(canonical), _ts(graph)
        if a and b and a == b and len(canonical) > 10 and len(graph) > 10:
            return (NORMALIZATION_ONLY, "TIMESTAMP_FORMAT") if allowed("TIMESTAMP_FORMAT") else (VALUE_MISMATCH, None)
        for plain, other in ((canonical, graph), (graph, canonical)):
            t = _ts(other)
            if date_only.fullmatch(plain) and t and len(other) > 10 and t.date().isoformat() == plain and t.hour == t.minute == t.second == 0:
                return (NORMALIZATION_ONLY, "DATE_REPRESENTATION") if allowed("DATE_REPRESENTATION") else (VALUE_MISMATCH, None)
    return VALUE_MISMATCH, None


@dataclass
class DatasetResult:
    dataset: str
    protected: bool = False
    records: int = 0
    invalid: int = 0
    records_with_difference: set = field(default_factory=set)
    missing_in_graph: int = 0
    missing_in_canonical: int = 0
    field_mismatches: int = 0
    normalization_only: int = 0
    ignored_bookkeeping: int = 0
    fields_compared: int = 0
    unexplained: int = 0
    rules: Counter = field(default_factory=Counter)
    differences: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    detail: list[dict[str, Any]] = field(default_factory=list)

    def add(self, record_id: str, fld: str, canonical: Any, graph: Any, dtype: str, rule: str | None, keep_detail: bool) -> None:
        self.fields_compared += 1
        row = {"dataset": self.dataset, "record_id": record_id, "field": fld, "canonical_value": _show(canonical), "graph_value": _show(graph), "difference_type": dtype}
        if rule:
            row["normalization_rule"] = rule
        if keep_detail:
            self.detail.append({**row, "result": "MATCH" if dtype == MATCH else dtype})
        if dtype == MATCH:
            if not self.samples or (record_id == self.samples[0]["record_id"] and len(self.samples) < 12):
                self.samples.append({**row, "result": "MATCH"})  # the first record's fields, as a readable example of a match
            return
        if dtype == NORMALIZATION_ONLY:
            self.normalization_only += 1
            self.rules[rule] += 1
        elif dtype in FAILING:
            self.records_with_difference.add(record_id)
            if dtype == MISSING_IN_GRAPH and fld == "<record>":
                self.missing_in_graph += 1
            elif dtype == MISSING_IN_CANONICAL and fld == "<record>":
                self.missing_in_canonical += 1
            else:
                self.field_mismatches += 1
                if dtype == MISSING_IN_GRAPH:
                    self.missing_in_graph += 1
                if dtype == MISSING_IN_CANONICAL:
                    self.missing_in_canonical += 1
            self.unexplained += 1
        self.differences.append(row)

    def bookkeeping(self, n: int) -> None:
        if n:
            self.ignored_bookkeeping += n
            self.rules["IGNORED_BOOKKEEPING"] += n

    def status(self) -> str:
        return "PASS" if self.unexplained == 0 and self.invalid == 0 else "FAIL"

    def summary(self) -> dict[str, Any]:
        bad = len(self.records_with_difference)
        return {"dataset": self.dataset, "protected": self.protected, "records_checked": self.records, "valid": self.records - bad, "invalid": self.invalid + bad,
                "invalid_canonical_rows": self.invalid, "records_with_differences": bad, "missing_in_graph": self.missing_in_graph, "missing_in_canonical": self.missing_in_canonical,
                "field_mismatches": self.field_mismatches, "normalization_only": self.normalization_only, "ignored_bookkeeping": self.ignored_bookkeeping,
                "fields_compared": self.fields_compared, "rules_applied": dict(sorted(self.rules.items())), "status": self.status()}


def _show(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return json.loads(json.dumps(v, default=str))


# ═══ dataset comparison (driven by the registry) ═══════════════════════════════════════════════════
def compare_datasets(src: GraphSource, root: Path = CANON_DIR, names: list[str] | None = None, keep_detail: bool = False) -> list[DatasetResult]:
    results = []
    for spec in SPECS:
        if names and spec.name not in names:
            continue
        results.append(_compare_one(src, spec, root, keep_detail))
    return results


def _compare_one(src: GraphSource, spec: DatasetSpec, root: Path, keep: bool) -> DatasetResult:
    recs, bad = _records(spec, root)
    res = DatasetResult(spec.name, protected=spec.name in PROTECTED_DATASETS, records=len(recs), invalid=bad)
    # nodes ---------------------------------------------------------------------------------------
    for t in spec.targets:
        protected = res.protected and t.mode == "verify"  # the supplied node itself, not the synthetic profile hung on it
        ids_by_label: dict[tuple[str, str], list[str]] = defaultdict(list)
        ident = {}
        for rec in recs:
            label, key, gid = Engine._identity(t, rec)
            ids_by_label[(label, key)].append(gid)
            ident[rec.id] = (label, key, gid)
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for (label, key), ids in ids_by_label.items():
            for i, p in src.nodes(label, key, ids).items():
                found[(label, i)] = p
        for rec in recs:
            label, key, gid = ident[rec.id]
            node = found.get((label, gid))
            if node is None:
                res.add(rec.id, "<record>", gid, None, MISSING_IN_GRAPH, None, keep)
                continue
            res.bookkeeping(sum(1 for b in BOOKKEEPING if b in node))
            for cf, gp in t.fields.items():
                dtype, rule = classify(getattr(rec, cf, None), node.get(gp), cf, casefold=cf in t.casefold, protected=protected)
                res.add(rec.id, f"{label}.{gp}", getattr(rec, cf, None), node.get(gp), dtype, rule, keep)
            # provenance: the data_status the record claims must be the one the graph holds; source ids are compared when the canonical record states one
            d, r = classify(rec.data_status, node.get("data_status"), "data_status", protected=protected)
            res.add(rec.id, f"{label}.data_status", rec.data_status, node.get("data_status"), d, r, keep)
            if rec.source_record_id is not None and node.get("source_record_id") is not None:
                d, r = classify(rec.source_record_id, node.get("source_record_id"), "source_record_id", protected=protected)
                res.add(rec.id, f"{label}.source_record_id", rec.source_record_id, node.get("source_record_id"), d, r, keep)
        _graph_only_nodes(src, spec, t, recs, res, keep)
        _edges(src, spec, t, recs, ident, res, keep)
    # relationship datasets ---------------------------------------------------------------------------
    if spec.rel:
        _rel_dataset(src, spec, recs, res, keep)
    return res


def _graph_only_nodes(src: GraphSource, spec: DatasetSpec, t: Any, recs: list[Any], res: DatasetResult, keep: bool) -> None:
    """Nodes the graph holds for this dataset (stamped with its name by the ingestion) that no canonical record names."""
    if t.label_field or not t.label:
        return
    have = src.node_ids(t.label, t.key, dataset=spec.name)
    want = {Engine._identity(t, r)[2] for r in recs}
    for gid in sorted(have - want):
        res.add(gid, "<record>", None, gid, MISSING_IN_CANONICAL, None, keep)


def _edges(src: GraphSource, spec: DatasetSpec, t: Any, recs: list[Any], ident: dict[str, tuple[str, str, str]], res: DatasetResult, keep: bool) -> None:
    for rd in t.rels:
        targets: dict[str, list[tuple[Any, str]]] = defaultdict(list)
        for rec in recs:
            val = getattr(rec, rd.field, None)
            if val is None:
                continue
            kind = rd.kind or rd.kind_from[1][getattr(rec, rd.kind_from[0])]
            targets[kind].append((rec, val))
        for kind, items in targets.items():
            resolved = src.resolve(kind, [v for _, v in items])
            groups: dict[tuple[tuple[str, str], tuple[str, str]], list[tuple[Any, str, str]]] = defaultdict(list)
            for rec, val in items:
                this = ident[rec.id]
                other = resolved.get(val)
                if other is None:
                    res.add(rec.id, f"edge:{rd.type}", val, None, MISSING_IN_GRAPH, None, keep)  # the referenced entity itself is not in the graph
                    continue
                if rd.reverse:
                    groups[(other, (this[0], this[1]))].append((rec, val, this[2]))
                else:
                    groups[((this[0], this[1]), other)].append((rec, this[2], val))
            for (fl, tl), rows in groups.items():
                have = src.rels(rd.type, fl, tl, [(f, tt) for _, f, tt in rows])
                for rec, f, tt in rows:
                    ok = (f, tt) in have
                    res.add(rec.id, f"edge:{rd.type}", getattr(rec, rd.field), getattr(rec, rd.field) if ok else None, MATCH if ok else MISSING_IN_GRAPH, None, keep)


def _rel_dataset(src: GraphSource, spec: DatasetSpec, recs: list[Any], res: DatasetResult, keep: bool) -> None:
    rt = spec.rel
    assert rt is not None
    need: dict[str, set[str]] = defaultdict(set)
    for rec in recs:
        need[rt.from_kind].add(getattr(rec, rt.from_field))
        need[rt.to_kind or rt.to_kind_from[1][getattr(rec, rt.to_kind_from[0])]].add(getattr(rec, rt.to_field))
    resolved = {k: src.resolve(k, sorted(v)) for k, v in need.items()}
    groups: dict[tuple[tuple[str, str], tuple[str, str]], list[Any]] = defaultdict(list)
    for rec in recs:
        to_kind = rt.to_kind or rt.to_kind_from[1][getattr(rec, rt.to_kind_from[0])]
        fl, tl = resolved[rt.from_kind].get(getattr(rec, rt.from_field)), resolved[to_kind].get(getattr(rec, rt.to_field))
        if fl is None or tl is None:
            res.add(rec.id, f"{rt.type}.endpoints", f"{getattr(rec, rt.from_field)}->{getattr(rec, rt.to_field)}", None, MISSING_IN_GRAPH, None, keep)
            continue
        groups[(fl, tl)].append(rec)
    for (fl, tl), rows in groups.items():
        have = src.rels(rt.type, fl, tl, [(getattr(r, rt.from_field), getattr(r, rt.to_field)) for r in rows])
        for rec in rows:
            rel = have.get((getattr(rec, rt.from_field), getattr(rec, rt.to_field)))
            if rel is None:
                res.add(rec.id, f"{rt.type}", f"{getattr(rec, rt.from_field)}->{getattr(rec, rt.to_field)}", None, MISSING_IN_GRAPH, None, keep)
                continue
            res.bookkeeping(sum(1 for b in BOOKKEEPING if b in rel))
            for cf, gp in rt.fields.items():
                d, r = classify(getattr(rec, cf, None), rel.get(gp), cf, protected=res.protected and rt.mode == "verify")
                res.add(rec.id, f"{rt.type}.{gp}", getattr(rec, cf, None), rel.get(gp), d, r, keep)
            d, r = classify(rec.data_status, rel.get("data_status"), "data_status", protected=res.protected and rt.mode == "verify")
            res.add(rec.id, f"{rt.type}.data_status", rec.data_status, rel.get("data_status"), d, r, keep)
    have_ids = src.rel_ids(rt.type, dataset=spec.name)
    want_ids = {rt.rel_id.format(id=r.id) for r in recs}
    for rid in sorted(have_ids - want_ids):
        res.add(rid, "<record>", None, rid, MISSING_IN_CANONICAL, None, keep)


def compare_supplied_relationships(src: GraphSource, root: Path = CANON_DIR, keep_detail: bool = False) -> list[DatasetResult]:
    """The protected catalogue relationships the registry does not own: FITS (part->machine), SUPPLIED_BY (part->supplier), IN_CATEGORY / IN_SUBCATEGORY, and the search aliases that
    the discovery vocabulary is read from. Compared against the canonical fitment, approved-source and part records."""
    out = []
    fit = DatasetResult("protected:FITS_relationship", protected=True)
    recs, fit.invalid = _records(BY_NAME["fitment"], root)
    fit.records = len(recs)
    have = {(f["part"], f["machine"]): f["props"] for f in src.fits()}
    for r in recs:
        p = have.get((r.part_id, r.machine_id))
        if p is None:
            fit.add(r.id, "FITS", f"{r.part_id}->{r.machine_id}", None, MISSING_IN_GRAPH, None, keep_detail)
            continue
        fit.add(r.id, "FITS.rel_id", r.fitment_id, p.get("rel_id"), *classify(r.fitment_id, p.get("rel_id"), protected=True), keep_detail)
        graph_status = p.get("fitment_status")
        mapped = FITMENT_MAP.get(graph_status)
        if mapped == r.fitment_status and graph_status != r.fitment_status:
            fit.add(r.id, "FITS.fitment_status", r.fitment_status, graph_status, NORMALIZATION_ONLY, "FITMENT_ENUM_MAP", keep_detail)
        else:
            d, rule = classify(r.fitment_status, graph_status, protected=True)
            fit.add(r.id, "FITS.fitment_status", r.fitment_status, graph_status, d, rule, keep_detail)
        d, rule = classify(r.fitment_rule, p.get("fitment_type"), protected=True)
        fit.add(r.id, "FITS.fitment_type", r.fitment_rule, p.get("fitment_type"), d, rule, keep_detail)
    for key in sorted(set(have) - {(r.part_id, r.machine_id) for r in recs}):
        fit.add(f"{key[0]}->{key[1]}", "<record>", None, "FITS", MISSING_IN_CANONICAL, None, keep_detail)
    out.append(fit)

    sup = DatasetResult("protected:SUPPLIED_BY_relationship", protected=True)
    arecs, sup.invalid = _records(BY_NAME["approved_sources"], root)
    suppliers = [r for r in arecs if r.source_kind == "SUPPLIER"]
    sup.records = len(suppliers)
    have_s = {(x["part"], x["supplier"]): x["props"] for x in src.supplied_by()}
    for r in suppliers:
        p = have_s.get((r.part_id, r.source_id))
        if p is None:
            sup.add(r.id, "SUPPLIED_BY", f"{r.part_id}->{r.source_id}", None, MISSING_IN_GRAPH, None, keep_detail)
            continue
        status = p.get("relationship_status", "")
        if str(status).startswith("ACTIVE") and r.approval_status == "APPROVED":
            sup.add(r.id, "SUPPLIED_BY.relationship_status", r.approval_status, status, NORMALIZATION_ONLY, "SUPPLIER_ACTIVE_MAP", keep_detail)
        else:
            sup.add(r.id, "SUPPLIED_BY.relationship_status", r.approval_status, status, VALUE_MISMATCH, None, keep_detail)
    for key in sorted(set(have_s) - {(r.part_id, r.source_id) for r in suppliers}):
        sup.add(f"{key[0]}->{key[1]}", "<record>", None, "SUPPLIED_BY", MISSING_IN_CANONICAL, None, keep_detail)
    out.append(sup)

    cat = DatasetResult("protected:part_category_links", protected=True)
    precs, cat.invalid = _records(BY_NAME["parts"], root)
    cat.records = len(precs)
    links = src.part_categories()
    for p in precs:
        have_c = links.get(p.part_id, (None, None))
        cat.add(p.part_id, "IN_CATEGORY", p.category_id, have_c[0], *classify(p.category_id, have_c[0], protected=True), keep_detail)
        cat.add(p.part_id, "IN_SUBCATEGORY", p.subcategory_id, have_c[1], *classify(p.subcategory_id, have_c[1], protected=True), keep_detail)
    out.append(cat)

    al = DatasetResult("protected:part_search_aliases", protected=True)
    al.records = len(precs)
    have_a = src.part_aliases()
    for p in precs:
        al.add(p.part_id, "aliases", sorted(p.aliases), have_a.get(p.part_id, []), *classify(sorted(p.aliases), have_a.get(p.part_id, []), protected=True), keep_detail)
    out.append(al)
    return out


# ═══ entity inventory ══════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Entity:
    name: str
    datasets: tuple[str, ...]
    labels: tuple[tuple[str, str], ...] = ()  # (graph label, key) pairs; ids are united
    rel_type: str | None = None
    id_fn: Any = None  # canonical record -> id as the graph stores it
    place_labels: tuple[str, ...] = ()  # labels whose nodes count only when they are used as places (they carry logistics_type)
    note: str = ""


def _leg(r: Any) -> str:
    return r.leg_id


def _prefixed(prefix: str):
    return lambda r: f"{prefix}:{r.id}"


ENTITIES: tuple[Entity, ...] = (
    Entity("Part", ("parts",), (("Part", "part_id"),)), Entity("Machine", ("machines",), (("Machine", "machine_id"),)),
    Entity("MachineInstance", ("machine_instances",), (("MachineInstance", "machine_instance_id"),)), Entity("Category", ("categories",), (("Category", "category_id"),)),
    Entity("PartSpecification", ("specifications",), (("PartSpecification", "specification_id"),)),
    Entity("Fitment (FITS relationship)", ("fitment",), rel_type="FITS", note="graph FITS relationships are identified by rel_id = canonical fitment_id"),
    Entity("FitmentContext", ("fitment",), (("FitmentContext", "fitment_id"),)),
    Entity("ApprovedSource (APPROVED_SOURCE relationship)", ("approved_sources",), rel_type="APPROVED_SOURCE", id_fn=_prefixed("APPROVED_SOURCE")),
    Entity("Supplier", ("suppliers", "network_suppliers"), (("Supplier", "supplier_id"),)), Entity("Dealer", ("dealers", "network_dealers"), (("Dealer", "dealer_id"),)),
    Entity("Plant", ("plants",), (("Plant", "plant_id"),)),
    Entity("Location", ("locations", "network_locations"), (("Warehouse", "warehouse_id"), ("ShipTo", "shipto_id"), ("Plant", "plant_id"), ("Location", "location_id"),
                                                           ("TransportTerminal", "terminal_id"), ("Dealer", "dealer_id"), ("Supplier", "supplier_id")),
           place_labels=("Dealer", "Supplier"), note="one id space spread over seven graph labels; a Dealer or Supplier node counts as a location only when it carries logistics_type"),
    Entity("Customer", ("customers",), (("Customer", "customer_id"),)), Entity("Order", ("orders", "network_orders"), (("Order", "order_id"),)),
    Entity("OrderLine", ("order_lines", "network_order_lines"), (("OrderLine", "order_line_id"),)),
    Entity("Inventory (AVAILABLE_AT relationship)", ("inventory",), rel_type="AVAILABLE_AT", id_fn=_prefixed("AVAILABLE_AT"), note="inventory is a relationship Part->Warehouse in the graph"),
    Entity("Pricing (Price)", ("pricing",), (("Price", "price_id"),)),
    Entity("Route (TransportRoute)", ("routes", "network_routes"), (("TransportRoute", "route_id"),)),
    Entity("RouteLeg (TransportLeg)", ("route_legs", "network_route_legs"), (("TransportLeg", "leg_id"),), id_fn=_leg),
    Entity("Shipment", ("shipments", "network_shipments"), (("Shipment", "shipment_id"),)), Entity("TrackingEvent", ("tracking_events", "network_tracking_events"), (("TrackingEvent", "tracking_event_id"),)),
    Entity("Technician", ("technicians",), (("Technician", "technician_id"),)), Entity("WorkOrder", ("work_orders",), (("WorkOrder", "work_order_id"),)),
    Entity("InstallationEvent", ("installations",), (("InstallationEvent", "installation_id"),)), Entity("ReplacementEvent", ("replacements",), (("ReplacementEvent", "replacement_id"),)),
    Entity("WarrantyPolicy", ("warranty_policies",), (("WarrantyPolicy", "warranty_policy_id"),)), Entity("WarrantyClaim", ("warranty_claims",), (("WarrantyClaim", "claim_id"),)),
    Entity("Evidence", ("evidence",), (("Evidence", "evidence_id"),)), Entity("FeaturedScenario", ("scenarios_discovery", "scenarios_logistics", "scenarios_warranty"), (("FeaturedScenario", "scenario_id"),)),
)


def entity_counts(src: GraphSource, root: Path = CANON_DIR) -> list[dict[str, Any]]:
    """canonical_count, graph_count, difference and status for every required entity. Graph records written by the running app (source_id APP-SESSION: live orders, shipments,
    carts) are operational, not canonical: they are counted separately in graph_app_written and never hide a mismatch of canonical records. The id sets are compared, not only
    the totals, so a swapped record is not masked by an equal count."""
    out = []
    cache: dict[str, list[Any]] = {}
    for e in ENTITIES:
        want: set[str] = set()
        for ds in e.datasets:
            cache.setdefault(ds, _records(BY_NAME[ds], root)[0])
            want |= {e.id_fn(r) if e.id_fn else r.id for r in cache[ds]}
        if e.rel_type:
            have = src.rel_ids(e.rel_type)
            app = 0
        else:
            have = set()
            for label, key in e.labels:
                have |= src.node_ids(label, key, exclude_app=True, require_property="logistics_type" if label in e.place_labels else None)
            app = sum(src.app_written(label) for label, _ in e.labels)
        missing_graph, missing_canon = sorted(want - have), sorted(have - want)
        ok = not missing_graph and not missing_canon
        out.append({"entity": e.name, "canonical_count": len(want), "graph_count": len(have), "difference": len(have) - len(want), "status": "PASS" if ok else "FAIL",
                    "missing_in_graph": missing_graph[:25], "missing_in_canonical": missing_canon[:25], "graph_app_written": app,
                    "note": e.note or ("graph_app_written counts operational records written by the running app (source_id APP-SESSION); they are outside the canonical datasets" if app else "")})
    return out


def normalization_report(results: list[DatasetResult]) -> dict[str, Any]:
    applied: dict[str, dict[str, Any]] = {}
    for r in results:
        for rule, n in r.rules.items():
            a = applied.setdefault(rule, {"rule": rule, "description": RULES.get(rule, ""), "count": 0, "datasets": {}})
            a["count"] += n
            a["datasets"][r.dataset] = a["datasets"].get(r.dataset, 0) + n
    return {"rules_defined": RULES, "normalization_rules_applied": sorted(applied.values(), key=lambda a: a["rule"]),
            "ignored_difference_count": sum(a["count"] for a in applied.values()),
            "not_ignored": "Every VALUE_MISMATCH, TYPE_MISMATCH, MISSING_IN_GRAPH and MISSING_IN_CANONICAL is reported and fails the dataset. There is no catch-all bucket."}


def json_safe(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=lambda o: sorted(o) if isinstance(o, set) else str(o)))
