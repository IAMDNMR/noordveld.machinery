"""Shared loading + helpers for the Parts Intelligence graph audit. Read-only: nothing here writes to any database."""
from __future__ import annotations

import collections
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent  # the backend/ folder

# Backend layout (see backend/README.md)
DATA = ROOT / "data"
COMPLETE = DATA / "processed" / "noordveld-complete-dataset-synthetic-demo.xlsx"
ORIGINAL = DATA / "catalogue" / "noordveld-parts-catalog.xlsx"
GRAPH = ROOT / "graph"
CYPHER = GRAPH / "cypher"
SCHEMA = GRAPH / "schema"
VALIDATION = GRAPH / "validation"
AUDITS = GRAPH / "audits"
ENV_FILE = ROOT / ".env"
DOWNLOADS = Path("C:/Users/iamdn/Downloads/Noordveld_Complete_Dataset_SYNTHETIC_DEMO.xlsx")

MISSING_TOKENS = {"NOT_STATED", "NOT_CONFIGURED"}


def load(path: Path) -> dict[str, list[dict]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb:
        data = list(ws.iter_rows(values_only=True))
        if not data:
            out[ws.title] = []
            continue
        head = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(data[0])]
        out[ws.title] = [dict(zip(head, r)) for r in data[1:] if any(c is not None for c in r)]
    return out


def blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def token_missing(v) -> bool:
    return isinstance(v, str) and v.strip() in MISSING_TOKENS


def counter(rows, col):
    return collections.Counter("<None>" if r.get(col) is None else str(r.get(col)) for r in rows)
