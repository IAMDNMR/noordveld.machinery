"""Reading and writing canonical dataset files (JSON and CSV) and the manifest that versions them."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.canonical import SCHEMA_VERSION
from app.canonical.models import Canon
from app.canonical.registry import DatasetSpec

CANON_DIR = Path(__file__).resolve().parents[2] / "data" / "canonical"
MANIFEST = "manifest.json"


class DatasetFileError(Exception):
    pass


def columns_of(spec: DatasetSpec) -> list[str]:
    """CSV column order: the id first, the record fields in model order, provenance last."""
    prov = list(Canon.model_fields)
    own = [f for f in spec.model.model_fields if f not in prov]
    return own + prov


def load_rows(spec: DatasetSpec, root: Path = CANON_DIR) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The raw records of one dataset file plus its self-description (JSON: dataset/schema versions; CSV: the header)."""
    path = root / spec.path
    if not path.exists():
        raise DatasetFileError(f"{spec.path}: file not found")
    if spec.fmt == "json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise DatasetFileError(f"{spec.path}: not valid JSON ({exc})") from exc
        if isinstance(data, list):
            return data, {}
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise DatasetFileError(f"{spec.path}: expected a list or an object with a 'records' list")
        return data["records"], {k: v for k, v in data.items() if k != "records"}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        required = [n for n, f in spec.model.model_fields.items() if f.is_required()]
        missing = [c for c in required if c not in header]
        unknown = [c for c in header if c not in spec.model.model_fields]
        if missing or unknown:
            raise DatasetFileError(f"{spec.path}: header mismatch (missing: {missing or 'none'}; unknown: {unknown or 'none'})")
        return [dict(r) for r in reader], {"columns": header}


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    return str(v)


def dump_rows(spec: DatasetSpec, records: list[dict[str, Any]], root: Path = CANON_DIR, generated_at: str = "") -> Path:
    """Write records sorted by id so a dataset file is byte-stable for the same content."""
    path = root / spec.path
    path.parent.mkdir(parents=True, exist_ok=True)
    key = spec.model.ID
    cols = columns_of(spec)
    ordered = [{c: r.get(c) for c in cols} for r in sorted(records, key=lambda r: str(r[key]))]
    if spec.fmt == "json":
        body = {"dataset": spec.name, "dataset_version": "v1", "canonical_schema_version": SCHEMA_VERSION, "generated_at": generated_at, "records": ordered}
        path.write_text(json.dumps(body, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for r in ordered:
                w.writerow([_cell(r.get(c)) for c in cols])
    return path


def read_manifest(root: Path = CANON_DIR) -> dict[str, Any]:
    p = root / MANIFEST
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_manifest(entries: dict[str, dict[str, Any]], generated_at: str, root: Path = CANON_DIR) -> Path:
    body = {"canonical_schema_version": SCHEMA_VERSION, "generated_at": generated_at, "datasets": dict(sorted(entries.items()))}
    p = root / MANIFEST
    p.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    return p
