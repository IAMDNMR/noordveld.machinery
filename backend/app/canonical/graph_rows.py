"""One way to turn graph node properties into a canonical-named record, shared by every graph reader.

A graph reader must return the SAME fields as the canonical file reader, or a files-vs-graph comparison cannot tell a missing value from a dropped field. So the record is built
from the canonical model, not from a hand-picked list:

  1. a value the reader looked up itself (a relationship end, a derived value)        -> `extra`
  2. a field the registry maps to a graph property                                      -> that property
  3. provenance (data_status, source_type, source_record_id)                            -> the properties, and source_type from data_status exactly as the exporter does
  4. every other model field (effective_from, effective_to, ...)                        -> the property of the same name
A field with no value in the graph is None (or [] for list fields): it is never left out, so "the graph has nothing" is visible as a difference whenever the file has a value.
"""
from __future__ import annotations

from typing import Any

from app.canonical.registry import BY_NAME

PROVENANCE = ("data_status", "source_type", "source_record_id")
LOCATION_KIND_BY_LABEL = {"Plant": "PLANT", "Warehouse": "DEPOT", "ShipTo": "SHIP_TO", "TransportTerminal": "TERMINAL", "Dealer": "DEALER", "Supplier": "SUPPLIER"}


def provenance(props: dict[str, Any]) -> dict[str, Any]:
    """The provenance the exporter writes into the canonical files: source_type follows data_status (OEM_MASTER for supplied data, SYNTHETIC_DEMO for synthetic)."""
    from app.canonical.export import (
        SOURCE_TYPE,  # the exporter's own map; imported here because the exporter is only needed once a graph is read
    )

    ds = props.get("data_status") or "SYNTHETIC_DEMO"
    return {"data_status": ds, "source_type": props.get("source_type") or SOURCE_TYPE.get(ds, "SYNTHETIC_DEMO"), "source_record_id": props.get("source_record_id")}


def _is_list(model_field: Any) -> bool:
    return "list" in str(model_field.annotation).lower()


def _as_list(v: Any) -> list[Any]:
    if v is None or v == "":
        return []
    return [x for x in v.split("|") if x] if isinstance(v, str) else list(v)


def graph_row(dataset: str, props: dict[str, Any], *, target: int = 0, **extra: Any) -> dict[str, Any]:
    spec = BY_NAME[dataset]
    fields = spec.targets[target].fields if spec.targets else spec.rel.fields  # a relationship dataset (route legs) maps its fields from the relationship properties
    prov = provenance(props)
    row: dict[str, Any] = {}
    for name, mf in spec.model.model_fields.items():
        if name == "ingestion_timestamp":
            continue
        if name in extra:
            value = extra[name]
        elif name in fields:
            value = props.get(fields[name])
        elif name in PROVENANCE:
            value = prov[name]
        else:
            value = props.get(name)
        row[name] = _as_list(value) if _is_list(mf) else value
    return row
