"""Where lifecycle facts come from. Two readers return the SAME canonical-named dictionaries:

  FileReader   the canonical dataset files (no database: tests and offline work)
  GraphReader  the Neo4j graph (read-only)

The context builder and the evaluator are identical on either; a test checks the files and the graph agree.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME
from app.graph.client import GraphClient
from app.graph.queries import lifecycle as q


class LifecycleReader(Protocol):
    def instance_ids(self) -> list[str]: ...
    def instance(self, machine_instance_id: str) -> dict[str, Any] | None: ...
    def installations(self, machine_instance_id: str) -> list[dict[str, Any]]: ...
    def installation(self, installation_id: str) -> dict[str, Any] | None: ...
    def work_order(self, work_order_id: str) -> dict[str, Any] | None: ...
    def work_order_events(self, work_order_id: str) -> list[str]: ...
    def technician(self, technician_id: str) -> dict[str, Any] | None: ...
    def dealer(self, dealer_id: str) -> dict[str, Any] | None: ...
    def part(self, part_id: str) -> dict[str, Any] | None: ...
    def fitment(self, machine_id: str, part_id: str) -> dict[str, Any] | None: ...
    def approved_sources(self, part_id: str) -> list[dict[str, Any]]: ...
    def policies(self, part_id: str) -> list[dict[str, Any]]: ...
    def claim_ids(self) -> list[str]: ...
    def claim(self, claim_id: str) -> dict[str, Any] | None: ...
    def claims(self, machine_instance_id: str) -> list[dict[str, Any]]: ...
    def replacements(self, machine_instance_id: str) -> list[dict[str, Any]]: ...
    def evidence(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]: ...


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "ingestion_timestamp"}


# ── canonical files ──────────────────────────────────────────────────────────────────────────────
class FileReader:
    def __init__(self, root: Path = CANON_DIR) -> None:
        self.root = root
        self._cache: dict[str, Any] = {}

    def _rows(self, name: str) -> list[dict[str, Any]]:
        if name not in self._cache:
            spec = BY_NAME[name]
            self._cache[name] = [_clean(spec.model.model_validate(r).model_dump()) for r in load_rows(spec, self.root)[0]]
        return self._cache[name]

    def _index(self, name: str, field: str) -> dict[str, dict[str, Any]]:
        key = f"idx:{name}:{field}"
        if key not in self._cache:
            self._cache[key] = {r[field]: r for r in self._rows(name)}
        return self._cache[key]

    def _group(self, name: str, field: str) -> dict[str, list[dict[str, Any]]]:
        key = f"grp:{name}:{field}"
        if key not in self._cache:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in self._rows(name):
                grouped[r[field]].append(r)
            self._cache[key] = grouped
        return self._cache[key]

    def instance_ids(self):
        return sorted(r["machine_instance_id"] for r in self._rows("machine_instances"))

    def instance(self, machine_instance_id):
        return self._index("machine_instances", "machine_instance_id").get(machine_instance_id)

    def installations(self, machine_instance_id):
        return sorted(self._group("installations", "machine_instance_id").get(machine_instance_id, []), key=lambda i: (i["installation_date"], i["installation_id"]))

    def installation(self, installation_id):
        return self._index("installations", "installation_id").get(installation_id)

    def work_order(self, work_order_id):
        return self._index("work_orders", "work_order_id").get(work_order_id)

    def work_order_events(self, work_order_id):
        ids = [i["installation_id"] for i in self._rows("installations") if i["work_order_id"] == work_order_id]
        ids += [r["replacement_id"] for r in self._rows("replacements") if r["work_order_id"] == work_order_id]
        return sorted(ids)

    def technician(self, technician_id):
        return self._index("technicians", "technician_id").get(technician_id)

    def dealer(self, dealer_id):
        return self._index("dealers", "dealer_id").get(dealer_id)

    def part(self, part_id):
        return self._index("parts", "part_id").get(part_id)

    def fitment(self, machine_id, part_id):
        key = "fit"
        if key not in self._cache:
            self._cache[key] = {(f["machine_id"], f["part_id"]): f for f in self._rows("fitment")}
        return self._cache[key].get((machine_id, part_id))

    def approved_sources(self, part_id):
        return sorted(self._group("approved_sources", "part_id").get(part_id, []), key=lambda s: s["approved_source_id"])

    def policies(self, part_id):
        return sorted(self._group("warranty_policies", "part_id").get(part_id, []), key=lambda p: p["warranty_policy_id"])

    def claim_ids(self):
        return sorted(r["claim_id"] for r in self._rows("warranty_claims"))

    def claim(self, claim_id):
        return self._index("warranty_claims", "claim_id").get(claim_id)

    def claims(self, machine_instance_id):
        return sorted(self._group("warranty_claims", "machine_instance_id").get(machine_instance_id, []), key=lambda c: (c["claim_date"], c["claim_id"]))

    def replacements(self, machine_instance_id):
        return sorted(self._group("replacements", "machine_instance_id").get(machine_instance_id, []), key=lambda r: (r["replacement_date"], r["replacement_id"]))

    def evidence(self, entity_type, entity_id):
        return sorted((e for e in self._rows("evidence") if e["entity_type"] == entity_type and e["entity_id"] == entity_id), key=lambda e: (e["created_at"] or "", e["evidence_id"]))


# ── the graph ────────────────────────────────────────────────────────────────────────────────────
def _prov(p: dict[str, Any]) -> dict[str, Any]:
    return {"data_status": p.get("data_status"), "source_type": p.get("source_type") or ("SYNTHETIC_DEMO" if p.get("data_status") == "SYNTHETIC_DEMO" else None),
            "source_record_id": p.get("source_record_id")}


def _list(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    return [x for x in v.split("|") if x] if isinstance(v, str) else list(v)


def _row(dataset: str, p: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """A canonical-named record from node properties: the registry's field -> property map, inverted."""
    target = BY_NAME[dataset].targets[0]
    row = {field: p.get(prop) for field, prop in target.fields.items()}
    row.update(extra)
    row.update(_prov(p))
    return row


class GraphReader:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph

    def _one(self, query: str, **params: Any) -> dict[str, Any] | None:
        rows = self._g.read(query, **params)
        return rows[0] if rows else None

    def instance_ids(self):
        return [r["id"] for r in self._g.read(q.INSTANCES)]

    def instance(self, machine_instance_id):
        r = self._one(q.INSTANCE, id=machine_instance_id)
        return _row("machine_instances", r["p"], owner_id=r["owner_id"], location_id=r["location_id"]) if r else None

    @staticmethod
    def _installation(r: dict[str, Any]) -> dict[str, Any]:
        row = _row("installations", r["p"], machine_instance_id=r["machine_instance_id"], part_id=r["part_id"], dealer_id=r["dealer_id"], technician_id=r["technician_id"],
                   work_order_id=r["work_order_id"])
        row["validation_issues"] = _list(row["validation_issues"])
        return row

    def installations(self, machine_instance_id):
        return [self._installation(r) for r in self._g.read(q.INSTALLATIONS_OF, id=machine_instance_id)]

    def installation(self, installation_id):
        r = self._one(q.INSTALLATION, id=installation_id)
        return self._installation(r) if r else None

    def work_order(self, work_order_id):
        r = self._one(q.WORK_ORDER, id=work_order_id)
        return _row("work_orders", r["p"], machine_instance_id=r["machine_instance_id"], dealer_id=r["dealer_id"], technician_id=r["technician_id"]) if r else None

    def work_order_events(self, work_order_id):
        return [r["id"] for r in self._g.read(q.WORK_ORDER_EVENTS, id=work_order_id)]

    def technician(self, technician_id):
        r = self._one(q.TECHNICIAN, id=technician_id)
        return _row("technicians", r["p"], dealer_id=r["dealer_id"]) if r else None

    def dealer(self, dealer_id):
        r = self._one(q.DEALER, id=dealer_id)
        return _row("dealers", r["p"]) if r else None

    def part(self, part_id):
        r = self._one(q.PART, id=part_id)
        return _row("parts", r["p"], status=r["status"]) if r else None

    def fitment(self, machine_id, part_id):
        r = self._one(q.FITMENT, machine=machine_id, part=part_id)
        return _row("fitment", r["p"]) if r else None

    def approved_sources(self, part_id):
        out = []
        for r in self._g.read(q.APPROVED_SOURCES, id=part_id):
            p = r["p"]
            out.append({"approved_source_id": str(p.get("rel_id", "")).removeprefix("APPROVED_SOURCE:"), "part_id": part_id, "source_id": r["source_id"],
                        "source_kind": p.get("source_kind"), "approval_status": p.get("approval_status"), **_prov(p)})
        return out

    def policies(self, part_id):
        out = []
        for r in self._g.read(q.POLICIES, id=part_id):
            row = _row("warranty_policies", r["p"], part_id=part_id)
            row["coverage_conditions"] = _list(row["coverage_conditions"])
            out.append(row)
        return out

    @staticmethod
    def _claim(r: dict[str, Any]) -> dict[str, Any]:
        return _row("warranty_claims", r["p"], machine_instance_id=r["machine_instance_id"], part_id=r["part_id"], installation_id=r["installation_id"], dealer_id=r["dealer_id"])

    def claim_ids(self):
        return [r["id"] for r in self._g.read(q.CLAIM_IDS)]

    def claim(self, claim_id):
        r = self._one(q.CLAIM, id=claim_id)
        return self._claim(r) if r else None

    def claims(self, machine_instance_id):
        return [self._claim(r) for r in self._g.read(q.CLAIMS_OF, id=machine_instance_id)]

    def replacements(self, machine_instance_id):
        return [_row("replacements", r["p"], machine_instance_id=r["machine_instance_id"], removed_installation_id=r["removed_installation_id"], new_installation_id=r["new_installation_id"],
                     removed_part_id=r["removed_part_id"], installed_part_id=r["installed_part_id"], work_order_id=r["work_order_id"])
                for r in self._g.read(q.REPLACEMENTS_OF, id=machine_instance_id)]

    def evidence(self, entity_type, entity_id):
        return [_row("evidence", r["p"]) for r in self._g.read(q.EVIDENCE, type=entity_type, id=entity_id)]
