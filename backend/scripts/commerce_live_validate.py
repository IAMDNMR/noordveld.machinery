"""Live validation of the Commerce Context Engine against the real Neo4j graph. READ-ONLY.

Usage (from backend/):  python scripts/commerce_live_validate.py [--out path.json]

  1. snapshot the graph:  node_count, relationship_count, protected_node_count, protected_relationship_count, the source integrity checksum and the SRC-CANON graph fingerprint
  2. run every scenario twice: on the canonical files and on the live graph, and compare the complete structured results (everything but generated_at)
  3. check the golden outcomes, authorization (real ownership data) and the evidence paths on the live results
  4. run the four /api/v1/commerce routes through the real app on the live graph
  5. snapshot again and require the two snapshots to be identical

Nothing is written to the graph: every call is a MATCH/RETURN through GraphClient.read. Exit code 0 only when every check passes; 2 when the graph cannot be reached.
The same functions back tests/test_commerce_live.py.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "eu_foundation"))

from app.canonical.io import CANON_DIR  # noqa: E402
from app.commerce.access import AccessDenied, CommerceRole, Principal  # noqa: E402
from app.commerce.engine import CommerceContextEngine  # noqa: E402
from app.core.config import get_settings  # noqa: E402

AS_OF = date(2026, 10, 7)
APP = "APP-SESSION"
PROTECTED = "(x.data_status IN ['SOURCE_DERIVED','DERIVED','REAL'] OR (x.data_status = 'USER_PROVIDED' AND coalesce(x.source_id, '') <> $app))"
GOLDEN_WARRANTY = {"CLM-G001": "ELIGIBLE", "CLM-G002": "NOT_ELIGIBLE", "CLM-G003": "NOT_ELIGIBLE", "CLM-G004-2": "REQUIRES_REVIEW", "CLM-G005": "REQUIRES_REVIEW",
                   "CLM-G006": "INSUFFICIENT_DATA", "CLM-G007": "NOT_ELIGIBLE", "CLM-G008": "NOT_ELIGIBLE"}
DISCOVERY = [
    ("I need a hydraulic pump for my KFT-600.", "NO_AVAILABLE_RECOMMENDATION"), ("I need a hydraulic pump for my KFT-200.", "RECOMMEND"), ("I need a hydraulic pump for my NV-2100", "NO_VALID_RECOMMENDATION"),
    ("I need a hydraulic filter for my X200.", "REQUIRES_CLARIFICATION"), ("I need a hydraulic pump", "REQUIRES_CLARIFICATION"), ("NVM-1060-HY for my KFT-600", "NO_AVAILABLE_RECOMMENDATION"),
    ("hydraulic filter for KFT-600", None), ("water pump for my NV-4500", None),
]


def P(role: str, **kw: Any) -> Principal:
    return Principal(CommerceRole(role), user_id="live-check", **kw)


def reachable() -> tuple[bool, str]:
    s = get_settings()
    if not s.graph_configured:
        return False, "Neo4j is not configured"
    host = urlparse(s.neo4j_uri).hostname or ""
    try:
        socket.create_connection((host, 7687), timeout=5).close()
        return True, host
    except OSError as exc:
        return False, f"cannot reach {host}:7687 ({exc})"


# ── snapshot ─────────────────────────────────────────────────────────────────────────────────────
def snapshot(graph: Any) -> dict[str, Any]:
    from audit_before import source_checksum

    from app.canonical.integrity import graph_fingerprint
    from app.canonical.store import Neo4jStore

    one = lambda q, **p: graph.read(q, **p)[0]["n"]  # noqa: E731
    store = Neo4jStore(get_settings())
    try:
        fp = graph_fingerprint(store)
    finally:
        getattr(store, "close", lambda: None)()
    return {"node_count": one("MATCH (n) RETURN count(n) AS n"), "relationship_count": one("MATCH ()-[r]->() RETURN count(r) AS n"),
            "protected_node_count": one(f"MATCH (x) WHERE {PROTECTED} RETURN count(x) AS n", app=APP),
            "protected_relationship_count": one(f"MATCH ()-[x]->() WHERE {PROTECTED} RETURN count(x) AS n", app=APP),
            "integrity_checksum": source_checksum(), "src_canon_graph_fingerprint": fp}


# ── comparison ───────────────────────────────────────────────────────────────────────────────────
def diffs(a: Any, b: Any, path: str = "") -> list[str]:
    """Every place two JSON-able structures differ, as 'path: files=... graph=...'. Empty when identical."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            out += diffs(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}" if path else k)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: files has {len(a)} items, graph has {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diffs(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: files={json.dumps(a, default=str)[:90]} graph={json.dumps(b, default=str)[:90]}"]


def norm(ctx: Any) -> dict[str, Any]:
    d = json.loads(json.dumps(ctx.to_dict(), default=str))
    d.pop("generated_at", None)
    return d


def scenarios(files: CommerceContextEngine) -> list[tuple[str, str, dict[str, Any]]]:
    """(name, kind, kwargs): every scenario the engine is checked on. Shipment and claim lists come from the canonical files, so the graph is compared on all of them."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for text, _ in DISCOVERY:
        out.append((f"discovery: {text}", "discovery", {"request": text}))
    out.append(("discovery: dest NL", "discovery", {"request": "hydraulic pump for my KFT-200", "destination_country": "NL"}))
    ships = sorted(s for s in ["SHP-NET-0001", "SHP-NET-0002", "SHP-NET-0003", "SHP-NET-0004", *[f"SHP-{n:04d}" for n in range(1, 12)]])
    out += [(f"logistics: {s}", "logistics", {"shipment_id": s}) for s in ships]
    out += [("logistics: order two shipments", "logistics", {"order_id": "ORD-NET-0001"}), ("logistics: unknown shipment", "logistics", {"shipment_id": "SHP-NOPE"})]
    out += [(f"warranty: {c}", "warranty", {"claim_id": c}) for c in files.lifecycle.claim_ids()]
    out.append(("warranty: machine+part", "warranty", {"machine_instance_id": "MI-G001", "part_id": "PRT-007"}))
    return out


def run(engine: CommerceContextEngine, kind: str, kw: dict[str, Any], principal: Principal | None = None) -> Any:
    fn = {"discovery": engine.build_discovery_context, "logistics": engine.build_logistics_context, "warranty": engine.build_warranty_context}[kind]
    args = (kw["request"],) if kind == "discovery" else ()
    return fn(*args, principal=principal, **{k: v for k, v in kw.items() if k != "request"})


def compare_engines(files: CommerceContextEngine, live: CommerceContextEngine) -> dict[str, Any]:
    report: dict[str, Any] = {"scenarios": 0, "identical": 0, "different": {}}
    for name, kind, kw in scenarios(files):
        report["scenarios"] += 1
        d = diffs(norm(run(files, kind, kw)), norm(run(live, kind, kw)))
        if d:
            report["different"][name] = d[:25]
        else:
            report["identical"] += 1
    return report


def authorization_checks(files: CommerceContextEngine, live: CommerceContextEngine) -> list[dict[str, Any]]:
    """The same ownership matrix on both engines; each row records what happened on each and whether they agree."""
    cases: list[tuple[str, str, Principal, dict[str, Any], bool]] = [
        ("customer owns shipment", "logistics", P("END_CUSTOMER", customer_id="CUS-009"), {"shipment_id": "SHP-NET-0001"}, True),
        ("other customer denied shipment", "logistics", P("END_CUSTOMER", customer_id="CUS-010"), {"shipment_id": "SHP-NET-0001"}, False),
        ("other customer denied order", "logistics", P("END_CUSTOMER", customer_id="CUS-010"), {"order_id": "ORD-NET-0001"}, False),
        ("unknown shipment denied to customer", "logistics", P("END_CUSTOMER", customer_id="CUS-010"), {"shipment_id": "SHP-NOPE"}, False),
        ("dealer owns order", "logistics", P("DEALER", dealer_id="DLR-004"), {"shipment_id": "SHP-NET-0001"}, True),
        ("other dealer denied", "logistics", P("DEALER", dealer_id="DLR-097"), {"shipment_id": "SHP-NET-0001"}, False),
        ("OEM sees all", "logistics", P("OEM"), {"shipment_id": "SHP-NET-0001"}, True),
        ("customer owns machine claim", "warranty", P("END_CUSTOMER", customer_id="CUS-001"), {"claim_id": "CLM-G001"}, True),
        ("other customer denied claim", "warranty", P("END_CUSTOMER", customer_id="CUS-004"), {"claim_id": "CLM-G001"}, False),
        ("installing dealer sees claim", "warranty", P("DEALER", dealer_id="DLR-004"), {"claim_id": "CLM-G001"}, True),
        ("other dealer denied claim", "warranty", P("DEALER", dealer_id="DLR-002"), {"claim_id": "CLM-G001"}, False),
        ("other customer denied machine discovery", "discovery", P("END_CUSTOMER", customer_id="CUS-004"), {"request": "hydraulic pump", "machine_instance_id": "MI-G001"}, False),
    ]
    rows = []
    for name, kind, principal, kw, expect_ok in cases:
        res = {}
        for label, eng in (("files", files), ("graph", live)):
            try:
                ctx = run(eng, kind, kw, principal)
                res[label] = {"allowed": True, "context": norm(ctx)}
            except AccessDenied as exc:
                res[label] = {"allowed": False, "message": str(exc)}
        agree = res["files"]["allowed"] == res["graph"]["allowed"] == expect_ok and (not expect_ok or not diffs(res["files"]["context"], res["graph"]["context"]))
        rows.append({"case": name, "expected_allowed": expect_ok, "files_allowed": res["files"]["allowed"], "graph_allowed": res["graph"]["allowed"], "ok": agree})
    return rows


def golden_checks(live: CommerceContextEngine) -> list[dict[str, Any]]:
    rows = []

    def row(name: str, ok: bool, detail: Any = None) -> None:
        rows.append({"check": name, "ok": bool(ok), "detail": detail})

    for text, expected in DISCOVERY:
        if expected:
            ctx = live.build_discovery_context(text)
            row(f"discovery {text!r} -> {expected}", ctx.decision.decision == expected, ctx.decision.decision)
    k6 = live.build_discovery_context("hydraulic pump for my KFT-600")
    row("PRT-007 compatible approved unavailable", k6.compatible_part and (k6.compatible_part["part_id"], k6.compatible_part["fitment"], k6.compatible_part["approved_source"], k6.compatible_part["availability"]) == ("PRT-007", "APPROVED", True, "UNAVAILABLE"))
    row("PRT-097 not recommended or offered", "PRT-097" not in json.dumps([k6.recommended_part, k6.compatible_part, k6.alternatives, k6.unconfirmed_matches]) and k6.rejection_reasons["PRT-097"][0]["code"] == "CANONICAL_TYPE_MISMATCH")
    row("discovery evidence path", [s["entity"] for s in k6.evidence_path][:3] == ["Part", "Fitment", "ApprovedSource"])
    for claim, outcome in GOLDEN_WARRANTY.items():
        w = live.build_warranty_context(claim_id=claim)
        row(f"warranty {claim} -> {outcome}", w.decision.decision == outcome, w.decision.decision)
        row(f"warranty {claim} provenance", all(f["sources"] and all(s["entity"] != "Record" for s in f["sources"]) for f in w.decision_factors))
    g1 = live.build_warranty_context(claim_id="CLM-G001")
    row("warranty evidence path", [s["entity"] for s in g1.evidence_path][:6] == ["MachineInstance", "Installation", "WorkOrder", "Dealer", "WarrantyPolicy", "WarrantyClaim"])
    sea = live.build_logistics_context(shipment_id="SHP-NET-0001")
    f = sea.decision.facts
    row("logistics sea in transit 1/3", (f["shipment_status"], f["completed_leg_count"], f["remaining_leg_count"]) == ("IN_TRANSIT", 1, 3), f)
    row("logistics evidence path", [s["entity"] for s in sea.evidence_path] == ["Order", "Shipment", "Route", "TrackingEvent"])
    alt = next((a for a in f["alternatives"] if a["transport_mode"] == "AIR"), None)
    row("logistics air alternative from route records", alt is not None and (alt["planned_transit_days"], alt["estimated_cost"], alt["days_vs_current"], alt["cost_vs_current"]) == (6, 12675.0, -85, 9840.0), alt)
    unresolved = [live.build_logistics_context(shipment_id=f"SHP-{n:04d}") for n in range(1, 12)]
    row("11 unresolved shipments INSUFFICIENT_DATA", all(u.decision.status == "INSUFFICIENT_DATA" and u.requires_review and u.route is None for u in unresolved))
    row("provenance on every context", all(c.source_records and all(r["entity"] and r["id"] for r in c.source_records) for c in (k6, g1, sea)))
    return rows


def api_checks(graph: Any) -> list[dict[str, Any]]:
    """The four routes through the real app, with the live graph behind the engine. Accounts are in-memory stand-ins (no AppUser is created in the graph)."""
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_commerce_engine, get_graph, get_orders_repository
    from app.main import app
    from tests.support.fake_orders import FakeRepo

    repo = FakeRepo()
    for uid, cid in (("U-C009", "CUS-009"), ("U-C010", "CUS-010"), ("U-C001", "CUS-001")):
        repo.users_[uid] = {"id": uid, "name": uid, "email": f"{uid}@x.example", "role": "END_USER", "customer_id": cid, "customer_name": cid}
    app.dependency_overrides[get_orders_repository] = lambda: repo
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_commerce_engine] = lambda: CommerceContextEngine.from_graph(graph, as_of=AS_OF)
    rows: list[dict[str, Any]] = []
    try:
        def client(uid: str | None = None) -> TestClient:
            c = TestClient(app, raise_server_exceptions=False)
            if uid:
                c.post("/api/v1/auth/login", json={"user_id": uid})
            return c

        base = "/api/v1/commerce"

        def check(name: str, resp: Any, status: int, pred: Any = lambda b: True) -> None:
            try:
                body = resp.json()
                ok = resp.status_code == status and bool(pred(body))
            except Exception as exc:  # noqa: BLE001
                body, ok = str(exc), False
            rows.append({"check": name, "ok": ok, "http": resp.status_code})

        check("401 without login", client().post(f"{base}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 401)
        check("discovery KFT-600", client("U-C001").post(f"{base}/discovery/context", json={"request": "I need a hydraulic pump for my KFT-600."}), 200,
              lambda b: b["decision"]["decision"] == "NO_AVAILABLE_RECOMMENDATION" and b["compatible_part"]["part_id"] == "PRT-007")
        check("discovery X200 clarification", client("U-C001").post(f"{base}/discovery/context", json={"request": "I need a hydraulic filter for my X200."}), 200,
              lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION" and b["machine"]["machine_id"] is None)
        check("logistics owner", client("U-C009").post(f"{base}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 200, lambda b: b["decision"]["facts"]["completed_leg_count"] == 1)
        check("logistics other customer 403", client("U-C010").post(f"{base}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 403)
        check("warranty owner", client("U-C001").post(f"{base}/warranty/context", json={"claim_id": "CLM-G001"}), 200, lambda b: b["decision"]["decision"] == "ELIGIBLE")
        check("warranty other customer 403", client("U-C010").post(f"{base}/warranty/context", json={"claim_id": "CLM-G001"}), 403)
        check("request: detected logistics", client("U-JANE").post(f"{base}/request", json={"request": "Where is my pump?", "shipment_id": "SHP-NET-0001"}), 200,
              lambda b: b["intent"] == "LOGISTICS" and b["decision"]["status"] == "SUCCESS")
        check("request: intent does not bypass ownership", client("U-C010").post(f"{base}/request", json={"intent": "LOGISTICS", "shipment_id": "SHP-NET-0001"}), 403)
        check("request: intent does not bypass warranty ownership", client("U-C010").post(f"{base}/request", json={"request": "covered under warranty?", "claim_id": "CLM-G001"}), 403)
        check("request: weak text asks", client("U-JANE").post(f"{base}/request", json={"request": "hello"}), 200, lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION" and b["context"] is None)
    finally:
        for dep in (get_orders_repository, get_graph, get_commerce_engine):
            app.dependency_overrides.pop(dep, None)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    ok, why = reachable()
    if not ok:
        print(f"NOT RUN: {why}. No check was performed; this is not a pass.")
        return 2
    from app.graph.client import GraphClient

    graph = GraphClient(get_settings())
    try:
        before = snapshot(graph)
        files = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)
        live = CommerceContextEngine.from_graph(graph, as_of=AS_OF)
        compare = compare_engines(files, live)
        auth = authorization_checks(files, live)
        golden = golden_checks(live)
        api = api_checks(graph)
        after = snapshot(graph)
    finally:
        graph.close()
    integrity = json.loads((CANON_DIR / "integrity.json").read_text(encoding="utf-8"))
    report = {"before": before, "after": after, "graph_unchanged": before == after, "src_canon_fingerprint_matches_recorded": before["src_canon_graph_fingerprint"] == integrity["graph_fingerprint"],
              "files_vs_graph": compare, "authorization": auth, "golden": golden, "api": api}
    failures = (len(compare["different"]) + sum(not r["ok"] for r in auth + golden + api) + (not report["graph_unchanged"]))
    report["failures"] = failures
    text = json.dumps(report, indent=1, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text if failures else json.dumps({k: report[k] for k in ("before", "after", "graph_unchanged", "src_canon_fingerprint_matches_recorded", "failures")} | {"files_vs_graph": {k: compare[k] for k in ("scenarios", "identical")}, "authorization_ok": len(auth), "golden_ok": len(golden), "api_ok": len(api)}, indent=1))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
