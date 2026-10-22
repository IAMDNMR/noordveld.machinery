"""Domain-pack import: parse, normalize, validate and compare as a dry run; persist only as a proposal for review.

Formats: a whole pack as JSON, or a CSV of concepts or relationships merged onto an existing version. Original source
values are kept in the report next to their normalized form. Applying is idempotent: the same content for the same
version is recognised and not stored twice, and the caller must present the fingerprint of the dry run it reviewed.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Literal

from pydantic import ValidationError

from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.packs import content_sha256
from app.domain_knowledge.store import DomainStore, VersionMissing, _sort_key, active
from app.domain_knowledge.validation import analyze

MAX_BYTES = 2_000_000
CSV_COLUMNS = {
    "concepts": (
        "id",
        "canonical_name",
        "kind",
        "domain_id",
        "definition",
        "synonyms",
        "provenance_kind",
        "provenance_reference",
        "verification",
    ),
    "relationships": (
        "id",
        "source_id",
        "type",
        "target_id",
        "cardinality",
        "meaning",
        "required",
        "provenance_kind",
        "provenance_reference",
        "verification",
    ),
}


class ImportRejected(ValueError):
    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _rows(content: str, kind: str, normalizations: list[dict]) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    expected = CSV_COLUMNS[kind]
    if tuple(reader.fieldnames or ()) != expected:
        raise ImportRejected(f"A {kind} CSV must have exactly these columns: {', '.join(expected)}")
    rows = []
    for number, raw in enumerate(reader, start=2):
        row = {}
        for key, value in raw.items():
            cleaned = _clean(value or "")
            if key == "type":
                cleaned = cleaned.upper().replace(" ", "_")
            if cleaned != (value or ""):
                normalizations.append(
                    {"row": number, "column": key, "original": value, "normalized": cleaned}
                )
            row[key] = cleaned
        rows.append(row)
    return rows


def _provenance(row: dict) -> dict:
    return {
        "kind": row["provenance_kind"],
        "reference": row["provenance_reference"],
        "verification": row["verification"] or "unverified",
    }


def parse(
    fmt: Literal["json", "csv"],
    content: str,
    store: DomainStore,
    csv_kind: str | None = None,
    pack_id: str | None = None,
    base_version: str | None = None,
    new_version: str | None = None,
) -> tuple[dict, list[dict]]:
    """Raw candidate pack (unvalidated) and the normalization log."""
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ImportRejected("The import is larger than 2 MB")
    normalizations: list[dict] = []
    if fmt == "json":
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ImportRejected(f"Not valid JSON: {exc.msg} at line {exc.lineno}") from None
        if not isinstance(raw, dict):
            raise ImportRejected("A domain pack must be a JSON object")
        return raw, normalizations
    if csv_kind not in CSV_COLUMNS or not (pack_id and base_version and new_version):
        raise ImportRejected(
            "A CSV import needs csv_kind (concepts or relationships), pack_id, base_version and new_version"
        )
    try:
        raw = store.get(pack_id, base_version).model_dump(mode="json")
    except VersionMissing:
        raise ImportRejected(f"Base version {pack_id} {base_version} does not exist") from None
    raw["version"], raw["status"] = new_version, "draft"
    existing = {item["id"]: item for item in raw[csv_kind]}
    for row in _rows(content, csv_kind, normalizations):
        if csv_kind == "concepts":
            item = {
                "id": row["id"],
                "canonical_name": row["canonical_name"],
                "kind": row["kind"],
                "domain_id": row["domain_id"],
                "definition": row["definition"],
                "synonyms": [
                    {"term": term.strip(), "domain_id": row["domain_id"], "note": ""}
                    for term in row["synonyms"].split(";")
                    if term.strip()
                ],
                "provenance": _provenance(row),
            }
        else:
            item = {
                "id": row["id"],
                "source_id": row["source_id"],
                "type": row["type"],
                "target_id": row["target_id"],
                "cardinality": row["cardinality"],
                "meaning": row["meaning"],
                "required": row["required"].lower() in ("true", "yes", "1"),
                "provenance": _provenance(row),
            }
        if row["id"] in existing:
            existing[row["id"]].update(item)
        else:
            raw[csv_kind].append(item)
            existing[row["id"]] = item
    return raw, normalizations


def compare(base: DomainPack | None, target: DomainPack) -> list[dict]:
    if base is None:
        return [
            {"group": group, "item_id": item.id, "change": "added"}
            for group, item in target.items()
        ]
    changes = []
    for group in DomainPack.GROUPS:
        old = {item.id: item.model_dump(mode="json") for item in getattr(base, group)}
        new = {item.id: item.model_dump(mode="json") for item in getattr(target, group)}
        for item_id in sorted(old.keys() | new.keys()):
            if item_id not in new:
                changes.append({"group": group, "item_id": item_id, "change": "removed"})
            elif item_id not in old:
                changes.append({"group": group, "item_id": item_id, "change": "added"})
            elif old[item_id] != new[item_id]:
                changes.append(
                    {
                        "group": group,
                        "item_id": item_id,
                        "change": "changed",
                        "fields": sorted(
                            key
                            for key in old[item_id].keys() | new[item_id].keys()
                            if old[item_id].get(key) != new[item_id].get(key)
                        ),
                    }
                )
    return changes


BREAKING_FIELDS = {
    "entities": {"attributes", "natural_keys"},
    "relationships": {"source_id", "target_id", "type", "cardinality", "required"},
    "concepts": {"kind", "domain_id"},
}


def compatibility(base: DomainPack | None, target: DomainPack, changes: list[dict]) -> dict:
    """Semantic versioning of knowledge: removals and changed structure are breaking and need a new major version."""
    if base is None:
        return {
            "level": "new",
            "breaking": [],
            "ok": True,
            "message": "First version of this pack.",
        }
    breaking = [
        item
        for item in changes
        if item["change"] == "removed"
        or (
            item["change"] == "changed"
            and set(item.get("fields", [])) & BREAKING_FIELDS.get(item["group"], set())
        )
    ]
    level = (
        "breaking"
        if breaking
        else "additive"
        if any(item["change"] == "added" for item in changes)
        else "patch"
        if changes
        else "none"
    )
    old, new = _sort_key(base.version), _sort_key(target.version)
    needed = {
        "breaking": (old[0] + 1, 0, 0),
        "additive": (old[0], old[1] + 1, 0),
        "patch": (old[0], old[1], old[2] + 1),
        "none": old,
    }[level]
    ok = new >= needed and new > old if level != "none" else True
    message = f"{level} change from {base.version}; requires at least {'.'.join(map(str, needed))}"
    return {
        "level": level,
        "breaking": [f"{item['group']}/{item['item_id']}" for item in breaking],
        "ok": ok,
        "message": message,
    }


def dry_run(raw: dict, store: DomainStore, normalizations: list[dict] | None = None) -> dict:
    """Everything an apply would do, without doing it."""
    report: dict = {
        "valid": False,
        "errors": [],
        "normalizations": normalizations or [],
        "pack_id": raw.get("id"),
        "version": raw.get("version"),
    }
    try:
        candidate = DomainPack.model_validate({**raw, "status": "draft"})
    except ValidationError as exc:
        report["errors"] = [
            {"location": "/".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors(include_url=False)
        ]
        return report
    versions = store.versions(candidate.id)
    existing = next((meta for meta in versions if meta["version"] == candidate.version), None)
    base_pack = next((pack for pack in active(store) if pack.id == candidate.id), None)
    changes = compare(base_pack, candidate)
    report.update(
        {
            "valid": True,
            "content_sha256": content_sha256(candidate),
            "base_version": base_pack.version if base_pack else None,
            "changes": changes,
            "summary": {
                kind: sum(1 for item in changes if item["change"] == kind)
                for kind in ("added", "removed", "changed")
            },
            "compatibility": compatibility(base_pack, candidate, changes),
            "analysis": analyze(candidate),
            "already_present": bool(
                existing and existing["content_sha256"] == content_sha256(candidate)
            ),
            "version_conflict": bool(
                existing and existing["content_sha256"] != content_sha256(candidate)
            ),
        }
    )
    if report["version_conflict"]:
        report["errors"].append(
            {
                "location": "version",
                "message": f"Version {candidate.version} already exists with different content. Use a new version.",
            }
        )
    if not report["compatibility"]["ok"]:
        report["errors"].append(
            {"location": "version", "message": report["compatibility"]["message"]}
        )
    for item in report["analysis"]["report"]["blocking"]:
        report["errors"].append({"location": "/".join(item["items"]), "message": item["message"]})
    report["valid"] = not report["errors"]
    return report


def apply(
    raw: dict,
    store: DomainStore,
    actor: str,
    reason: str,
    expected_sha256: str,
    normalizations: list[dict] | None = None,
) -> dict:
    """Store the candidate as a version under review. Never activates it: another person approves it separately."""
    report = dry_run(raw, store, normalizations)
    if not report["valid"]:
        raise ImportRejected("The import does not pass its dry run", report)
    if report["content_sha256"] != expected_sha256:
        raise ImportRejected(
            "The content differs from the dry run that was reviewed. Run the dry run again.", report
        )
    if not reason.strip():
        raise ImportRejected("Give a reason for the change")
    meta = store.propose(
        DomainPack.model_validate({**raw, "status": "under_review"}), actor, reason.strip()
    )
    return {"proposal": meta, "report": report}
