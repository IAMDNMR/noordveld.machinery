"""The ingestion engine: files -> parse -> validate -> normalise -> resolve references -> plan -> MERGE -> report.

Write policy (what makes a run safe on the shared graph)
  * A node that is PROTECTED (SOURCE_DERIVED, DERIVED, REAL, or USER_PROVIDED not written by the app) or APP-written (source_id APP-SESSION) is never
    modified: the record is compared with it and reported as verified / extension_pending / drift. This keeps the SOURCE/DERIVED integrity checksum and
    live orders, carts and stock reservations exactly as they are.
  * A node in a `verify` target is compared, never updated, even when unprotected (the graph owns it in this phase).
  * Otherwise the canonical values are merged; only properties that actually differ are written, so a second run writes nothing.
  * New records are stamped SRC-CANON with data_status / source_type from the record. Existing records keep their own provenance.
  * Nothing is ever deleted. Nothing is created without a unique id; relationships are unique per (type, from, to).
  * Dry-run reads the graph and writes nothing.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.canonical import SCHEMA_VERSION
from app.canonical.integrity import dataset_checksum
from app.canonical.io import CANON_DIR, DatasetFileError, load_rows
from app.canonical.models import Canon
from app.canonical.registry import (
    KINDS,
    LOCATION_KEYS,
    NEW_LABELS,
    DatasetSpec,
    NodeTarget,
    RelDef,
    order,
)
from app.canonical.store import SRC_CANON, Store

log = logging.getLogger(__name__)
PROTECTED = {"SOURCE_DERIVED", "DERIVED", "REAL"}
APP_SESSION = "APP-SESSION"
SOURCE_NAME = "Canonical ingestion (schema 1.0)"


def guard(props: dict[str, Any]) -> str | None:
    """Why an existing record must not be modified, or None when it may be."""
    if props.get("source_id") == APP_SESSION:
        return "app-written"
    if props.get("data_status") in PROTECTED or props.get("data_status") == "USER_PROVIDED":
        return "protected"
    return None


def same(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return sorted(map(str, a or [])) == sorted(map(str, b or []))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def compare(mapped: dict[str, Any], existing: dict[str, Any], casefold: set[str] = frozenset()) -> tuple[str, list[str]]:
    """verified: every canonical value equals the graph's · extension_pending: the graph lacks values canonical holds · drift: a value differs."""
    ext, conflict = [], []
    for prop, value in mapped.items():
        have = existing.get(prop)
        if have is None:
            ext.append(prop)
        elif same(value, have):
            continue
        elif prop in casefold and str(value).casefold() == str(have).casefold():
            ext.append(prop)
        else:
            conflict.append(prop)
    return ("drift" if conflict else "extension_pending" if ext else "verified"), conflict or ext


def norm_spec_name(name: str) -> str:
    n = " ".join(name.split())
    return n[:1].upper() + n[1:] if n.islower() else n


def normalise(spec: DatasetSpec, rec: Canon) -> Canon:
    """Deterministic clean-up that never changes meaning: country codes upper-case, specification names in one spelling (the original text stays in source_text)."""
    update: dict[str, Any] = {}
    if hasattr(rec, "country_code") and rec.country_code and rec.country_code != rec.country_code.upper():
        update["country_code"] = rec.country_code.upper()
    if spec.name == "specifications":
        update["name"] = norm_spec_name(rec.name)
        if rec.source_text is None and update["name"] != rec.name:
            update["source_text"] = rec.name
    return rec.model_copy(update=update) if update else rec


@dataclass
class Result:
    dataset: str
    version: str = "v1"
    records_read: int = 0
    records_valid: int = 0
    invalid: list[dict[str, Any]] = field(default_factory=list)
    status: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    nodes_to_create: int = 0
    nodes_to_update: int = 0
    rels_to_create: int = 0
    rels_to_update: int = 0
    protected_skipped: int = 0
    drift: list[dict[str, Any]] = field(default_factory=list)
    extension: int = 0
    unresolved_refs: int = 0
    checksum: str = ""
    applied: bool = False
    nodes_written: int = 0
    rels_written: int = 0
    failed: int = 0
    started_at: str = ""
    completed_at: str = ""

    def report(self, dry_run: bool) -> dict[str, Any]:
        s = self.status
        return {
            "dataset": self.dataset, "version": self.version, "canonical_schema_version": SCHEMA_VERSION, "dry_run": dry_run,
            "records_read": self.records_read, "records_valid": self.records_valid, "records_invalid": len(self.invalid),
            "nodes_to_create": self.nodes_to_create, "nodes_to_update": self.nodes_to_update,
            "relationships_to_create": self.rels_to_create, "relationships_to_update": self.rels_to_update,
            "records_skipped": len(self.invalid),
            "records_created": s["create"] if self.applied else 0, "records_updated": s["update"] if self.applied else 0,
            "records_unchanged": s["unchanged"], "records_verified": s["verified"], "records_extension_pending": s["extension_pending"],
            "records_drift": s["drift"], "records_protected_skipped": self.protected_skipped, "records_failed": self.failed,
            "relationships_created": self.rels_written if self.applied else 0, "unresolved_graph_references": self.unresolved_refs,
            "checksum": self.checksum, "started_at": self.started_at, "completed_at": self.completed_at,
            "invalid_examples": self.invalid[:5], "drift_examples": self.drift[:5],
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Engine:
    def __init__(self, store: Store | None, root: Path = CANON_DIR, clock=_now) -> None:
        self.store, self.root, self.clock = store, root, clock
        self.canon: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)  # kind -> id -> (label, key), filled as datasets are accepted
        self.cache: dict[str, dict[str, tuple[str, str] | None]] = defaultdict(dict)  # graph lookups
        self.records: dict[str, list[Canon]] = {}

    # ── public ───────────────────────────────────────────────────────────────────────────────────
    def run(self, names: list[str] | None = None, dry_run: bool = True) -> dict[str, Any]:
        started = self.clock()
        results = [self._dataset(spec, dry_run) for spec in order(names)]
        totals = defaultdict(int)
        for r in results:
            for k, v in r.report(dry_run).items():
                if isinstance(v, int) and not isinstance(v, bool):
                    totals[k] += v
        return {"canonical_schema_version": SCHEMA_VERSION, "dry_run": dry_run, "offline": self.store is None, "started_at": started, "completed_at": self.clock(),
                "totals": dict(totals), "datasets": [r.report(dry_run) for r in results]}

    # ── one dataset ──────────────────────────────────────────────────────────────────────────────
    def _dataset(self, spec: DatasetSpec, dry_run: bool) -> Result:
        res = Result(spec.name, started_at=self.clock())
        try:
            rows, meta = load_rows(spec, self.root)
        except DatasetFileError as exc:
            res.invalid.append({"row": 0, "id": None, "errors": str(exc)})
            res.completed_at = self.clock()
            self.records[spec.name] = []
            return res
        res.version = str(meta.get("dataset_version", "v1"))
        res.records_read = len(rows)
        recs = self._validate(spec, rows, res)
        recs = self._check_references(spec, recs, res)
        res.records_valid = len(recs)
        self.records[spec.name] = recs
        res.checksum = dataset_checksum(recs)
        if self.store is not None:
            recs = self._plan_and_apply(spec, recs, res, dry_run)
        # accepted records become resolvable for the datasets that depend on them
        for rec in recs:
            if spec.kind and spec.targets:
                label, key, _ = self._identity(spec.targets[0], rec)
                self.canon[spec.kind][rec.id] = (label, key)
        res.completed_at = self.clock()
        return res

    def _validate(self, spec: DatasetSpec, rows: list[dict[str, Any]], res: Result) -> list[Canon]:
        out: list[Canon] = []
        seen: set[str] = set()
        for i, row in enumerate(rows, 1):
            rid = row.get(spec.model.ID) if isinstance(row, dict) else None
            try:
                rec = spec.model.model_validate(row)
            except ValidationError as exc:
                res.invalid.append({"row": i, "id": rid, "errors": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:400]})
                continue
            if rec.id in seen:
                res.invalid.append({"row": i, "id": rec.id, "errors": "duplicate id in this dataset"})
                continue
            seen.add(rec.id)
            out.append(normalise(spec, rec))
        if spec.group_check:
            bad = spec.group_check(out)
            for rid, why in sorted(bad.items()):
                res.invalid.append({"row": None, "id": rid, "errors": why})
            out = [r for r in out if r.id not in bad]
        return sorted(out, key=lambda r: r.id)

    # ── references ───────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _needed(spec: DatasetSpec, rec: Canon) -> list[tuple[str, str, str]]:
        """(field, kind, id) for every entity this record points at."""
        need: list[tuple[str, str, str]] = []
        for f, kind in spec.refs:
            if getattr(rec, f) is not None:
                need.append((f, kind, getattr(rec, f)))
        for t in spec.targets:
            for rd in t.rels:
                v = getattr(rec, rd.field)
                if v is None:
                    continue
                kind = rd.kind or rd.kind_from[1].get(getattr(rec, rd.kind_from[0]))
                need.append((rd.field, kind or f"?{getattr(rec, rd.kind_from[0])}", v))
        if spec.rel:
            r = spec.rel
            need.append((r.from_field, r.from_kind, getattr(rec, r.from_field)))
            kind = r.to_kind or r.to_kind_from[1].get(getattr(rec, r.to_kind_from[0]))
            need.append((r.to_field, kind or f"?{getattr(rec, r.to_kind_from[0])}", getattr(rec, r.to_field)))
        return need

    def _prefetch(self, needs: set[tuple[str, str]]) -> None:
        by_kind: dict[str, list[str]] = defaultdict(list)
        for kind, i in needs:
            if kind in KINDS and i not in self.canon[kind] and i not in self.cache[kind]:
                by_kind[kind].append(i)
        for kind, ids in by_kind.items():
            found = self.store.resolve(kind, ids) if self.store is not None else {}
            for i in ids:
                self.cache[kind][i] = found.get(i)

    def _ref(self, kind: str, i: str) -> tuple[str, str] | None:
        return self.canon[kind].get(i) or self.cache[kind].get(i)

    def _check_references(self, spec: DatasetSpec, recs: list[Canon], res: Result) -> list[Canon]:
        needs = {(k, i) for r in recs for _, k, i in self._needed(spec, r)}
        self._prefetch(needs)
        ok: list[Canon] = []
        for rec in recs:
            bad = None
            for f, kind, i in self._needed(spec, rec):
                if kind not in KINDS:
                    bad = f"{f}: no entity kind for {kind.lstrip('?')!r}"
                elif self._ref(kind, i) is None:
                    if self.store is None:
                        res.unresolved_refs += 1  # offline: graph not consulted
                        continue
                    bad = f"{f}={i!r} does not exist as {kind}"
                if bad:
                    break
            if bad:
                res.invalid.append({"row": None, "id": rec.id, "errors": f"missing reference: {bad}"})
            else:
                ok.append(rec)
        return ok

    # ── identity and stamps ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _identity(target: NodeTarget, rec: Canon) -> tuple[str, str, str]:
        gid = target.id_fn(rec) if target.id_fn else rec.id
        if target.label_field:
            label = getattr(rec, target.label_field)
            return label, LOCATION_KEYS[label], gid
        return target.label, target.key, gid

    @staticmethod
    def _extra_labels(target: NodeTarget, rec: Canon) -> tuple[str, ...]:
        if not target.extra_label_field:
            return ()
        value = getattr(rec, target.extra_label_field, None)
        label = target.extra_label_map.get(value) if value else None
        return (label,) if label else ()

    def _create_stamp(self, spec: DatasetSpec, rec: Canon, now: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        s = {"source_id": SRC_CANON, "source_name": SOURCE_NAME, "source_file": f"backend/data/canonical/{spec.path}", "authoritative_flag": False, "confidence": "NOT_STATED",
             "data_status": rec.data_status, "provenance_type": rec.data_status, "source_type": rec.source_type, "source_record_id": rec.source_record_id or rec.id,
             "ingestion_timestamp": now, "last_updated": now[:10], "canonical_dataset": spec.name, "canonical_schema_version": SCHEMA_VERSION}
        if rec.effective_from:
            s["effective_from"] = rec.effective_from
        if rec.effective_to:
            s["effective_to"] = rec.effective_to
        s.update(extra or {})
        return s

    @staticmethod
    def _update_stamp(spec: DatasetSpec, now: str) -> dict[str, Any]:
        return {"ingestion_timestamp": now, "canonical_dataset": spec.name, "canonical_schema_version": SCHEMA_VERSION}

    @staticmethod
    def _mapped(target: NodeTarget, rec: Canon) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cf, gp in target.fields.items():
            v = getattr(rec, cf, None)
            if v is None or v == []:
                continue
            out[gp] = v
        return out

    # ── plan and apply ───────────────────────────────────────────────────────────────────────────
    def _plan_and_apply(self, spec: DatasetSpec, recs: list[Canon], res: Result, dry_run: bool) -> list[Canon]:
        now = self.clock()
        node_writes: dict[tuple[str, str, bool, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
        rel_writes: dict[tuple[str, tuple[str, str], tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)

        # existing nodes for every target; a target that must exist (create=False) but does not makes the record invalid
        exist: list[dict[tuple[str, str], dict[str, Any]]] = []
        for target in spec.targets:
            groups: dict[tuple[str, str], list[str]] = defaultdict(list)
            for rec in recs:
                label, key, gid = self._identity(target, rec)
                groups[(label, key)].append(gid)
            found: dict[tuple[str, str], dict[str, Any]] = {}
            for (label, key), ids in groups.items():
                for i, p in self.store.fetch_nodes(label, key, ids).items():
                    found[(label, i)] = p
            exist.append(found)
        kept: list[Canon] = []
        for rec in recs:
            missing = next((self._identity(t, rec) for ti, t in enumerate(spec.targets) if not t.create and (self._identity(t, rec)[0], self._identity(t, rec)[2]) not in exist[ti]), None)
            if missing:
                res.invalid.append({"row": None, "id": rec.id, "errors": f"target {missing[0]} {missing[2]!r} does not exist and this dataset may not create it"})
            else:
                kept.append(rec)
        res.records_valid = len(kept)

        status_of: dict[str, str] = {}
        merge_nodes: dict[str, list[tuple[NodeTarget, str, str, str]]] = defaultdict(list)  # rec id -> merge-eligible targets (for relationships)
        rank = ["unchanged", "verified", "extension_pending", "create", "update", "drift"]

        def note(rid: str, st: str) -> None:
            cur = status_of.get(rid)
            if cur is None or rank.index(st) > rank.index(cur):
                status_of[rid] = st

        for rec in kept:
            for ti, target in enumerate(spec.targets):
                label, key, gid = self._identity(target, rec)
                ex = exist[ti].get((label, gid))
                mapped = self._mapped(target, rec)
                if ex is None:
                    node_writes[(label, key, True, self._extra_labels(target, rec))].append({"id": gid, "props": mapped, "create": self._create_stamp(spec, rec, now)})
                    res.nodes_to_create += 1
                    note(rec.id, "create")
                    merge_nodes[rec.id].append((target, label, key, gid))
                    continue
                why = guard(ex)
                if why or target.mode == "verify":
                    cf = {target.fields[f] for f in target.casefold if f in target.fields}
                    st, detail = compare({p: v for p, v in mapped.items() if p != key}, ex, cf)
                    if why:
                        res.protected_skipped += 1
                    if st == "drift":
                        res.drift.append({"id": rec.id, "node": f"{label}:{gid}", "properties": detail})
                    if st == "extension_pending":
                        res.extension += 1
                    note(rec.id, st)
                    continue
                diff = {p: v for p, v in mapped.items() if p != key and not same(ex.get(p), v)}
                if diff:
                    node_writes[(label, key, target.create, self._extra_labels(target, rec))].append({"id": gid, "props": {**diff, **self._update_stamp(spec, now)}, "create": {}})
                    res.nodes_to_update += 1
                    note(rec.id, "update")
                else:
                    note(rec.id, "unchanged")
                merge_nodes[rec.id].append((target, label, key, gid))

        # relationships declared on node records (only for nodes this dataset may merge); looked up in batches per (type, from label, to label)
        pending: dict[tuple[str, tuple[str, str], tuple[str, str]], list[tuple[Canon, str, str, dict[str, Any]]]] = defaultdict(list)
        for rec in kept:
            for target, label, key, gid in merge_nodes.get(rec.id, []):
                for rd in target.rels:
                    self._collect_rel(rec, rd, (label, key, gid), pending)
        for (type_, fl, tl), items in pending.items():
            have = self.store.fetch_rels(type_, fl, tl, [(f, t) for _, f, t, _ in items])
            for rec, f, t, props in items:
                ex = have.get((f, t))
                if ex is None:
                    create = self._create_stamp(spec, rec, now, {"rel_id": f"{type_}:{f}:{t}"})
                    create.pop("source_record_id", None)
                    rel_writes[(type_, fl, tl)].append({"f": f, "t": t, "props": props, "create": create})
                    res.rels_to_create += 1
                else:
                    diff = {p: v for p, v in props.items() if not same(ex.get(p), v)}
                    if diff:
                        rel_writes[(type_, fl, tl)].append({"f": f, "t": t, "props": {**diff, **self._update_stamp(spec, now)}, "create": {}})
                        res.rels_to_update += 1

        # the record IS a relationship
        if spec.rel:
            self._plan_rel_dataset(spec, kept, res, rel_writes, now, note)

        for rec in kept:
            res.status[status_of.get(rec.id, "unchanged")] += 1

        if not dry_run:
            self._apply(spec, node_writes, rel_writes, res)
        return kept

    def _collect_rel(self, rec: Canon, rd: RelDef, this: tuple[str, str, str], pending) -> None:
        tid = getattr(rec, rd.field)
        if tid is None:
            return
        kind = rd.kind or rd.kind_from[1][getattr(rec, rd.kind_from[0])]
        other = self._ref(kind, tid)
        if other is None:  # offline or already reported invalid
            return
        (fl, fk, fid), (tl, tk, tid_) = ((other[0], other[1], tid), this) if rd.reverse else (this, (other[0], other[1], tid))
        props = {p: getattr(rec, p) for p in rd.props if getattr(rec, p) is not None}
        pending[(rd.type, (fl, fk), (tl, tk))].append((rec, fid, tid_, props))

    def _plan_rel_dataset(self, spec, recs: list[Canon], res: Result, rel_writes, now: str, note) -> None:
        r = spec.rel
        grouped: dict[tuple[tuple[str, str], tuple[str, str]], list[tuple[Canon, str, str]]] = defaultdict(list)
        for rec in recs:
            f_ref = self._ref(r.from_kind, getattr(rec, r.from_field))
            to_kind = r.to_kind or r.to_kind_from[1][getattr(rec, r.to_kind_from[0])]
            t_ref = self._ref(to_kind, getattr(rec, r.to_field))
            if f_ref is None or t_ref is None:
                continue
            grouped[(f_ref, t_ref)].append((rec, getattr(rec, r.from_field), getattr(rec, r.to_field)))
        for (fl, tl), items in grouped.items():
            have = self.store.fetch_rels(r.type, fl, tl, [(f, t) for _, f, t in items])
            for rec, f, t in items:
                props = {gp: getattr(rec, cf) for cf, gp in r.fields.items() if getattr(rec, cf) is not None and getattr(rec, cf) != []}
                ex = have.get((f, t))
                if ex is None:
                    create = self._create_stamp(spec, rec, now, {"rel_id": r.rel_id.format(id=rec.id)})
                    rel_writes[(r.type, fl, tl)].append({"f": f, "t": t, "props": props, "create": create})
                    res.rels_to_create += 1
                    note(rec.id, "create")
                    continue
                why = guard(ex)
                if why or r.mode == "verify":
                    st, detail = compare(props, ex)
                    if why:
                        res.protected_skipped += 1
                    if st == "drift":
                        res.drift.append({"id": rec.id, "relationship": f"{r.type}:{f}->{t}", "properties": detail})
                    if st == "extension_pending":
                        res.extension += 1
                    note(rec.id, st)
                    continue
                diff = {p: v for p, v in props.items() if not same(ex.get(p), v)}
                if diff:
                    rel_writes[(r.type, fl, tl)].append({"f": f, "t": t, "props": {**diff, **self._update_stamp(spec, now)}, "create": {}})
                    res.rels_to_update += 1
                    note(rec.id, "update")
                else:
                    note(rec.id, "unchanged")

    def _apply(self, spec: DatasetSpec, node_writes, rel_writes, res: Result) -> None:
        for label in spec.new_labels:
            self.store.ensure_constraint(label, NEW_LABELS[label])
        if node_writes or rel_writes:
            self.store.upsert_nodes("DataSource", "source_id", [{"id": SRC_CANON, "create": {}, "props": {
                "name": SOURCE_NAME, "layer": "canonical ingestion", "source_record_id": SRC_CANON, "source_file": "backend/data/canonical", "data_status": "SYNTHETIC_DEMO",
                "provenance_type": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO", "source_id": SRC_CANON, "source_name": SOURCE_NAME, "authoritative_flag": False, "confidence": "NOT_STATED",
                "verification": "Schema-validated records; references checked before every write",
                "limitations": "Synthetic demonstration data unless a record says otherwise. Not linked to a live ERP, PLM or MES."}}])
        for (label, key, create, extra), rows in node_writes.items():
            res.nodes_written += self.store.upsert_nodes(label, key, rows, create=create, extra_labels=extra)
        for (type_, fl, tl), rows in rel_writes.items():
            res.rels_written += self.store.upsert_rels(type_, fl, tl, rows)
        res.applied = True


def write_report(report: dict[str, Any], directory: Path, label: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report["started_at"].replace(":", "").replace("-", "")
    path = directory / f"{stamp}-{label}.json"
    path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return path
