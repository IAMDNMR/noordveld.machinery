"""Live validation of the Commerce Context Engine against the real Neo4j graph. READ-ONLY, two passes, auditable.

Usage (from backend/):
    python scripts/commerce_live_validate.py [--out report.json] [--offline] [--full-detail]

ONLINE (default)
  connectivity (DNS, TCP, authentication, database)  ->  snapshot_before
  pass 1: entity counts, field-level canonical<->graph comparison of every dataset, protected-catalogue comparison, engine(files) vs engine(graph) on every scenario,
          discovery / logistics / warranty golden scenarios, authorization matrix, API checks, evidence and provenance checks
  snapshot_after_pass1  ->  pass 2 (the same, from scratch)  ->  snapshot_after_pass2
  determinism: pass 1 == pass 2 (business results; timestamps and durations excluded) and before == after_pass1 == after_pass2
OFFLINE (--offline, or automatically never)
  the same machinery against an in-memory twin of the canonical files. It proves the harness and the engine logic; it is NOT Neo4j and the report says
  mode = OFFLINE, live_graph_verified = false, final classification BLOCKED.

Every graph call goes through ReadOnlyGraph (scripts/commerce_validation_lib.py): no write method, and any query containing a write keyword is refused before it is sent.

Exit code: 0 = PASS (PHASE 4H COMPLETE), 1 = FAIL (live validation found issues), 2 = BLOCKED (Neo4j unreachable, authentication failed or OFFLINE).
A skipped or blocked check is never a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "scripts" / "eu_foundation"))

import commerce_validation_lib as L  # noqa: E402
from app.canonical.io import CANON_DIR  # noqa: E402
from app.commerce.access import AccessDenied, CommerceRole, Principal  # noqa: E402
from app.commerce.engine import CommerceContextEngine  # noqa: E402
from app.core.config import get_settings  # noqa: E402

SCHEMA_VERSION = 2
AS_OF = date(2026, 10, 7)
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
    """(ok, reason) kept for tests/test_commerce_live.py; the report uses the fuller L.connectivity."""
    c = L.connectivity(get_settings())
    if c["database_reachable"]:
        return True, c["host"]
    if not c["configured"]:
        return False, "Neo4j is not configured"
    return False, f"cannot reach {c['host']}:7687 (DNS {'yes' if c['dns_resolved'] else 'no'}, TCP {'yes' if c['tcp_reachable'] else 'no'}, authentication {c['authentication']}, {c['error_class']})"


# ── snapshot ─────────────────────────────────────────────────────────────────────────────────────
def snapshot(graph: Any) -> dict[str, Any]:
    """node_count, relationship_count, protected counts, integrity checksum, SRC-CANON fingerprint and per-label / per-relationship-type counts. Read-only."""
    g = graph if isinstance(graph, L.ReadOnlyGraph) else L.ReadOnlyGraph(graph)
    return L.CypherSource(g).snapshot()


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
        rows.append({"case": name, "role": principal.role.value, "resource": kind + ": " + ", ".join(f"{k}={v}" for k, v in kw.items() if k != "request"), "expected_allowed": expect_ok, "files_allowed": res["files"]["allowed"], "graph_allowed": res["graph"]["allowed"], "ok": agree})
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


# ── API checks (the real app, the real routes) ────────────────────────────────────────────────────
API_BASE = "/api/v1/commerce"


def _engine_for(target: Any) -> tuple[CommerceContextEngine, Any]:
    if isinstance(target, CommerceContextEngine):
        return target, None
    ro = target if isinstance(target, L.ReadOnlyGraph) else L.ReadOnlyGraph(target)
    return CommerceContextEngine.from_graph(ro, as_of=AS_OF), ro


def api_checks(target: Any) -> list[dict[str, Any]]:
    """The four routes through the real app. `target` is a graph handle (the live graph sits behind the engine) or an engine (OFFLINE: the files). Accounts are in-memory stand-ins:
    no AppUser is created in the graph. Rows: {endpoint, check, ok, http, decision, evidence, provenance}."""
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_commerce_engine, get_graph, get_orders_repository
    from app.main import app
    from tests.support.fake_orders import FakeRepo

    engine, ro = _engine_for(target)
    repo = FakeRepo()
    for uid, cid in (("U-C009", "CUS-009"), ("U-C010", "CUS-010"), ("U-C001", "CUS-001")):
        repo.users_[uid] = {"id": uid, "name": uid, "email": f"{uid}@x.example", "role": "END_USER", "customer_id": cid, "customer_name": cid}
    app.dependency_overrides[get_orders_repository] = lambda: repo
    app.dependency_overrides[get_commerce_engine] = lambda: engine
    if ro is not None:
        app.dependency_overrides[get_graph] = lambda: ro
    rows: list[dict[str, Any]] = []
    try:
        def client(uid: str | None = None) -> TestClient:
            c = TestClient(app, raise_server_exceptions=False)
            if uid:
                c.post("/api/v1/auth/login", json={"user_id": uid})
            return c

        def check(endpoint: str, name: str, resp: Any, status: int, pred: Any = lambda b: True) -> None:
            body: Any = {}
            try:
                body = resp.json()
                ok = resp.status_code == status and bool(pred(body))
            except Exception:  # noqa: BLE001
                ok = False
            ctx = body.get("context") if isinstance(body, dict) and "context" in body else body
            dec = (ctx or {}).get("decision") if isinstance(ctx, dict) else None
            rows.append({"endpoint": endpoint, "check": name, "ok": ok, "http": resp.status_code, "expected_http": status,
                         "decision": f"{dec['status']}/{dec['decision']}" if isinstance(dec, dict) and "status" in dec else None,
                         "evidence": bool(ctx.get("evidence_path")) if isinstance(ctx, dict) and resp.status_code == 200 else None,
                         "provenance": bool(ctx.get("source_records")) if isinstance(ctx, dict) and resp.status_code == 200 else None})

        d, lg, w, rq = "POST discovery/context", "POST logistics/context", "POST warranty/context", "POST request"
        check(d, "401 without login", client().post(f"{API_BASE}/discovery/context", json={"request": "hydraulic pump for my KFT-200"}), 401)
        check(lg, "401 without login", client().post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 401)
        check(w, "401 without login", client().post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G001"}), 401)
        check(rq, "401 without login", client().post(f"{API_BASE}/request", json={"request": "hello"}), 401)
        check(d, "KFT-600: no available recommendation, PRT-007 compatible", client("U-C001").post(f"{API_BASE}/discovery/context", json={"request": "I need a hydraulic pump for my KFT-600."}), 200,
              lambda b: b["decision"]["decision"] == "NO_AVAILABLE_RECOMMENDATION" and b["compatible_part"]["part_id"] == "PRT-007" and b["recommended_part"] is None
              and "PRT-097" not in json.dumps([b["recommended_part"], b["compatible_part"], b["alternatives"], b["unconfirmed_matches"]]))
        check(d, "KFT-200: recommendation", client("U-C001").post(f"{API_BASE}/discovery/context", json={"request": "I need a hydraulic pump for my KFT-200."}), 200,
              lambda b: b["decision"]["decision"] == "RECOMMEND" and b["recommended_part"]["part_id"] == "PRT-006")
        check(d, "X200: clarification, machine not guessed", client("U-C001").post(f"{API_BASE}/discovery/context", json={"request": "I need a hydraulic filter for my X200."}), 200,
              lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION" and b["machine"]["machine_id"] is None)
        check(d, "other customer's machine instance 403", client("U-C010").post(f"{API_BASE}/discovery/context", json={"request": "hydraulic pump", "machine_instance_id": "MI-G001"}), 403)
        check(d, "invalid body 422", client("U-C001").post(f"{API_BASE}/discovery/context", json={"request": "x", "surprise": 1}), 422)
        check(lg, "owner: in transit, 1 leg done, 3 remaining", client("U-C009").post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 200,
              lambda b: b["decision"]["facts"]["completed_leg_count"] == 1 and b["decision"]["facts"]["remaining_leg_count"] == 3 and b["decision"]["facts"]["alternatives"])
        check(lg, "other customer 403", client("U-C010").post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-NET-0001"}), 403)
        check(lg, "unknown shipment indistinguishable from foreign (403)", client("U-C010").post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-NOPE"}), 403)
        check(lg, "unresolved shipment INSUFFICIENT_DATA", client("U-JANE").post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-0001"}), 200,
              lambda b: b["decision"]["status"] == "INSUFFICIENT_DATA" and b["requires_review"] is True and b["route"] is None)
        check(lg, "order with two shipments asks", client("U-JANE").post(f"{API_BASE}/logistics/context", json={"order_id": "ORD-NET-0001"}), 200, lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION")
        check(lg, "OEM: missing shipment is NOT_FOUND", client("U-JANE").post(f"{API_BASE}/logistics/context", json={"shipment_id": "SHP-NOPE"}), 200, lambda b: b["decision"]["status"] == "NOT_FOUND")
        check(lg, "invalid body 422", client("U-JANE").post(f"{API_BASE}/logistics/context", json={"shipment_id": "bad id"}), 422)
        check(w, "owner: G001 ELIGIBLE", client("U-C001").post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G001"}), 200,
              lambda b: b["decision"]["decision"] == "ELIGIBLE" and all(f["sources"] for f in b["decision_factors"]))
        check(w, "other customer 403", client("U-C010").post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G001"}), 403)
        check(w, "dealer role without dealer id 403", client("U-JANE").post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G001", "user_role": "DEALER"}), 403)
        check(w, "G006 INSUFFICIENT_DATA with explicit missing", client("U-JANE").post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G006"}), 200,
              lambda b: b["decision"]["status"] == "INSUFFICIENT_DATA" and {"technician", "work_order"} <= set(b["missing"]))
        check(w, "invalid body 422", client("U-JANE").post(f"{API_BASE}/warranty/context", json={"claim_id": "CLM-G001", "part_id": "PRT-007"}), 422)
        check(rq, "detected logistics", client("U-JANE").post(f"{API_BASE}/request", json={"request": "Where is my pump?", "shipment_id": "SHP-NET-0001"}), 200,
              lambda b: b["intent"] == "LOGISTICS" and b["intent_source"] == "DETECTED" and b["decision"]["status"] == "SUCCESS")
        check(rq, "weak text asks, no context", client("U-JANE").post(f"{API_BASE}/request", json={"request": "hello"}), 200, lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION" and b["context"] is None)
        check(rq, "intent does not bypass logistics ownership", client("U-C010").post(f"{API_BASE}/request", json={"intent": "LOGISTICS", "shipment_id": "SHP-NET-0001"}), 403)
        check(rq, "intent does not bypass warranty ownership", client("U-C010").post(f"{API_BASE}/request", json={"intent": "WARRANTY", "claim_id": "CLM-G001"}), 403)
        check(rq, "intent does not bypass discovery clarification", client("U-JANE").post(f"{API_BASE}/request", json={"intent": "DISCOVERY", "request": "I need a hydraulic filter for my X200."}), 200,
              lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION")
        check(rq, "forced intent with no references asks", client("U-JANE").post(f"{API_BASE}/request", json={"intent": "WARRANTY"}), 200, lambda b: b["decision"]["status"] == "REQUIRES_CLARIFICATION")
        blob = json.dumps([r for r in rows])
        rows.append({"endpoint": "all", "check": "no credentials or account data in any response row", "ok": not any(x in blob for x in ("password", "NEO4J", "Traceback")), "http": None})
    finally:
        for dep in (get_orders_repository, get_graph, get_commerce_engine):
            app.dependency_overrides.pop(dep, None)
    return rows


def api_endpoint_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One line per endpoint: authentication, authorization, status code, decision, evidence, provenance."""
    out = []
    for ep in ("POST discovery/context", "POST logistics/context", "POST warranty/context", "POST request"):
        mine = [r for r in rows if r.get("endpoint") == ep]
        auth = next((r for r in mine if r["check"] == "401 without login"), None)
        deny = [r for r in mine if r["expected_http"] in (403, 422)] if mine else []
        good = next((r for r in mine if r["expected_http"] == 200 and r.get("evidence") is not None), None) or next((r for r in mine if r["expected_http"] == 200), None)
        out.append({"endpoint": ep, "authentication": "PASS" if auth and auth["ok"] else "FAIL", "authorization": "PASS" if deny and all(r["ok"] for r in deny) else "FAIL",
                    "status_code": good["http"] if good else None, "decision": good["decision"] if good else None, "evidence": good["evidence"] if good else None,
                    "provenance": good["provenance"] if good else None, "checks": len(mine), "status": "PASS" if mine and all(r["ok"] for r in mine) else "FAIL"})
    return out


# ═══ structured sections: one row per scenario ═════════════════════════════════════════════════════
DISCOVERY_CHAIN = ["Part", "Fitment", "ApprovedSource", "Inventory", "Price"]
LOGISTICS_CHAIN = ["Order", "Shipment", "Route", "TrackingEvent"]
WARRANTY_CHAIN = ["MachineInstance", "Installation", "WorkOrder", "Dealer", "WarrantyPolicy", "WarrantyClaim", "Evidence"]


def evidence_status(ctx: Any, chain: list[str], must_have: int = 0) -> dict[str, Any]:
    """The evidence path is ordered along `chain`, numbered from 1, every step names a record in source_records, and (when required) has at least `must_have` steps."""
    path = ctx.evidence_path
    recs = {(r["entity"], r["id"]) for r in ctx.source_records}
    order = [chain.index(s["entity"]) if s["entity"] in chain else -1 for s in path]
    problems = []
    if len(path) < must_have:
        problems.append(f"path has {len(path)} steps, expected at least {must_have}")
    if -1 in order:
        problems.append("a step is not part of the expected chain")
    if order != sorted(order):
        problems.append("steps are out of order")
    if [s["step"] for s in path] != list(range(1, len(path) + 1)):
        problems.append("steps are not numbered 1..n")
    problems += [f"{s['entity']} {s['id']} is not in source_records" for s in path if (s["entity"], s["id"]) not in recs]
    return {"status": "PASS" if not problems else "FAIL", "entities": [s["entity"] for s in path], "problems": problems}


def provenance_status(ctx: Any) -> dict[str, Any]:
    problems = [f"{r['entity']} {r['id']} has no data_status" for r in ctx.source_records if not r.get("data_status")]
    if not ctx.source_records and ctx.decision.status not in ("REQUIRES_CLARIFICATION", "NOT_FOUND"):
        problems.append("no source records")
    for f in getattr(ctx, "decision_factors", []):
        if not f["sources"] or any(x["entity"] == "Record" or not x["id"] for x in f["sources"]):
            problems.append(f"decision factor {f['code']} has no identifiable source record")
    if not ctx.confidence.get("data_status"):
        problems.append("confidence.data_status missing")
    return {"status": "PASS" if not problems else "FAIL", "source_records": len(ctx.source_records), "problems": problems}


def discovery_rows(live: CommerceContextEngine, files: CommerceContextEngine) -> list[dict[str, Any]]:
    rows = []
    for i, (text, expected) in enumerate(DISCOVERY + [("hydraulic pump for my KFT-200", "RECOMMEND")], 1):
        kw = {"destination_country": "NL"} if i == len(DISCOVERY) + 1 else {}
        ctx = live.build_discovery_context(text, **kw)
        ref = files.build_discovery_context(text, **kw)
        checks: list[tuple[str, bool]] = []
        d = ctx.decision.decision
        if expected:
            checks.append((f"decision == {expected}", d == expected))
        rec = ctx.recommended_part
        if rec:  # invariant for every scenario: a recommendation is canonical, fitting, approved and available
            checks.append(("recommended part is a canonical match, approved fitment, approved source, available",
                           rec["product_match"] is True and rec["fitment"] == "APPROVED" and rec["approved_source"] is True and rec["availability"] == "AVAILABLE"))
        checks.append(("no candidate that is not a canonical match is recommended", not any(c["recommendation"] and c["product_match"] != "CANONICAL_MATCH" for c in ctx.candidate_parts)))
        if "KFT-600" in text and "pump" in text and "NVM" not in text:
            cp = ctx.compatible_part or {}
            checks += [("PRT-007 compatible, approved, unavailable", (cp.get("part_id"), cp.get("fitment"), cp.get("approved_source"), cp.get("availability")) == ("PRT-007", "APPROVED", True, "UNAVAILABLE")),
                       ("PRT-097 and PRT-078 are canonical type mismatches and not offered", all(ctx.rejection_reasons.get(p, [{}])[0].get("code") == "CANONICAL_TYPE_MISMATCH" for p in ("PRT-097", "PRT-078"))
                        and not any(p in json.dumps([ctx.recommended_part, ctx.compatible_part, ctx.alternatives, ctx.unconfirmed_matches]) for p in ("PRT-097", "PRT-078")))]
        if "KFT-200" in text:
            checks.append(("PRT-006 recommended", (rec or {}).get("part_id") == "PRT-006"))
        if "X200" in text:
            checks.append(("machine not guessed", ctx.machine["machine_id"] is None and ctx.recommended_part is None))
        same = not diffs(norm(ref), norm(ctx))
        checks.append(("identical to the canonical-files engine", same))
        ev = (evidence_status(ctx, DISCOVERY_CHAIN, 3) if d in ("RECOMMEND", "NO_AVAILABLE_RECOMMENDATION") else {"status": "NOT_APPLICABLE", "entities": [], "problems": []})
        rows.append({"scenario": f"D{i:03d}", "request": text, "expected": expected or "(invariants only)", "actual": f"{ctx.decision.status}/{d}", "recommended_part": (rec or {}).get("part_id"),
                     "compatible_part": (ctx.compatible_part or {}).get("part_id"), "assertions": [{"check": c, "ok": ok} for c, ok in checks], "evidence_status": ev,
                     "provenance_status": provenance_status(ctx)["status"], "status": "PASS" if all(ok for _, ok in checks) and ev["status"] != "FAIL" else "FAIL"})
    return rows


def logistics_rows(live: CommerceContextEngine, files: CommerceContextEngine) -> list[dict[str, Any]]:
    import csv

    canon: dict[str, dict[str, str]] = {}
    for name in ("shipments", "network_shipments"):
        for r in csv.DictReader(open(CANON_DIR / "logistics" / f"{name}.csv", encoding="utf-8")):
            canon[r["shipment_id"]] = r
    rows = []
    for sid in sorted(canon):
        c = canon[sid]
        ctx, ref = live.build_logistics_context(shipment_id=sid), files.build_logistics_context(shipment_id=sid)
        linked = bool(c["route_id"]) and c["route_resolution_status"] == "LINKED"
        expected_status = "SUCCESS" if linked else "INSUFFICIENT_DATA"
        route_id = (ctx.route or {}).get("route_id")
        f = ctx.decision.facts
        checks = [(f"status == {expected_status}", ctx.decision.status == expected_status), (f"route == canonical route ({c['route_id'] or 'none'})", (route_id or "") == (c["route_id"] or "")),
                  ("identical to the canonical-files engine", not diffs(norm(ref), norm(ctx)))]
        if not linked:
            checks += [("requires_review and no route invented", ctx.requires_review is True and ctx.route is None and ctx.alternative_routes == [] and ctx.completed_legs == [] and ctx.remaining_legs == [])]
        else:
            alts = ctx.transport_comparison["options"] if ctx.transport_comparison else []
            cur = next((o for o in alts if o["is_current"]), None)
            checks += [("progress is computed (completed + remaining == legs)", f["completed_leg_count"] + f["remaining_leg_count"] == len(ctx.route_legs)),
                       ("every alternative's time and cost difference equals its route values minus the current route's",
                        all(o["days_vs_current"] == o["planned_transit_days"] - cur["planned_transit_days"] and o["cost_vs_current"] == round(o["estimated_cost"] - cur["estimated_cost"], 2) for o in alts if not o["is_current"]))]
        ev = evidence_status(ctx, LOGISTICS_CHAIN, 2)
        rows.append({"shipment": sid, "expected_status": expected_status, "actual_status": f"{ctx.decision.status}/{ctx.decision.decision}", "expected_route": c["route_id"] or None, "actual_route": route_id,
                     "shipment_status": f.get("shipment_status"), "completed_legs": f.get("completed_leg_count"), "remaining_legs": f.get("remaining_leg_count"), "planned_eta": f.get("planned_eta"),
                     "alternatives": [{k: a[k] for k in ("route_id", "transport_mode", "planned_transit_days", "estimated_cost", "days_vs_current", "cost_vs_current")} for a in f.get("alternatives", [])],
                     "requires_review": ctx.requires_review, "assertions": [{"check": k, "ok": ok} for k, ok in checks], "evidence_status": ev, "provenance_status": provenance_status(ctx)["status"],
                     "status": "PASS" if all(ok for _, ok in checks) and ev["status"] == "PASS" else "FAIL"})
    multi = live.build_logistics_context(order_id="ORD-NET-0001")
    rows.append({"shipment": "ORD-NET-0001 (order with two shipments)", "expected_status": "REQUIRES_CLARIFICATION", "actual_status": f"{multi.decision.status}/{multi.decision.decision}",
                 "assertions": [{"check": "asks which shipment, does not pick one", "ok": multi.decision.status == "REQUIRES_CLARIFICATION" and multi.shipment is None and len(multi.clarification["options"]) >= 2}],
                 "evidence_status": {"status": "NOT_APPLICABLE"}, "provenance_status": "NOT_APPLICABLE",
                 "status": "PASS" if multi.decision.status == "REQUIRES_CLARIFICATION" and multi.shipment is None and len(multi.clarification["options"]) >= 2 else "FAIL"})
    return rows


def warranty_rows(live: CommerceContextEngine, files: CommerceContextEngine) -> list[dict[str, Any]]:
    rows = []
    for claim, expected in GOLDEN_WARRANTY.items():
        ctx, ref = live.build_warranty_context(claim_id=claim), files.build_warranty_context(claim_id=claim)
        live_f = {f["code"]: (f["status"], tuple(s["id"] for s in f["sources"])) for f in ctx.decision_factors}
        ref_f = {f["code"]: (f["status"], tuple(s["id"] for s in f["sources"])) for f in ref.decision_factors}
        matching = sorted(k for k in live_f if live_f.get(k) == ref_f.get(k))
        mismatching = sorted(k for k in set(live_f) | set(ref_f) if live_f.get(k) != ref_f.get(k))
        ev = evidence_status(ctx, WARRANTY_CHAIN, 3)
        prov = provenance_status(ctx)
        ok = ctx.decision.decision == expected == ref.decision.decision and not mismatching and not diffs(norm(ref), norm(ctx)) and prov["status"] == "PASS"
        rows.append({"scenario": claim, "expected_decision": expected, "actual_decision": ctx.decision.decision, "phase3_evaluator_on_files": ref.decision.decision, "matching_factors": matching,
                     "mismatching_factors": mismatching, "missing": ctx.missing, "evidence_status": ev, "provenance_status": prov["status"], "status": "PASS" if ok and ev["status"] == "PASS" else "FAIL"})
    return rows


def authorization_rows(files: CommerceContextEngine, live: CommerceContextEngine) -> list[dict[str, Any]]:
    """Expected vs actual per case, with no private data: ids of the demo records only, never names or contact details."""
    rows = []
    for r in authorization_checks(files, live):
        rows.append({"test": r["case"], "role": r.get("role"), "resource": r.get("resource"), "expected": "200" if r["expected_allowed"] else "403", "actual": "200" if r["graph_allowed"] else "403",
                     "files_actual": "200" if r["files_allowed"] else "403", "status": "PASS" if r["ok"] else "FAIL"})
    oem = live.build_logistics_context(principal=P("OEM"), shipment_id="SHP-NOPE")
    rows.append({"test": "OEM: a genuinely missing shipment is NOT_FOUND, not an authorization answer", "role": "OEM", "resource": "shipment", "expected": "NOT_FOUND", "actual": oem.decision.status,
                 "files_actual": files.build_logistics_context(principal=P("OEM"), shipment_id="SHP-NOPE").decision.status, "status": "PASS" if oem.decision.status == "NOT_FOUND" else "FAIL"})
    msgs = []
    for sid in ("SHP-NOPE", "SHP-NET-0001"):
        try:
            live.build_logistics_context(principal=P("END_CUSTOMER", customer_id="CUS-010"), shipment_id=sid)
            msgs.append("allowed")
        except AccessDenied as exc:
            msgs.append(f"{exc.code}:{exc}")
    rows.append({"test": "missing and foreign shipment are refused identically (no existence leak)", "role": "END_CUSTOMER", "resource": "shipment", "expected": "identical refusal", "actual": "identical refusal" if msgs[0] == msgs[1] and "allowed" not in msgs else "different",
                 "files_actual": None, "status": "PASS" if msgs[0] == msgs[1] and "allowed" not in msgs else "FAIL"})
    return rows



# ═══ one complete read-only pass ═══════════════════════════════════════════════════════════════════
def run_pass(src: Any, files: CommerceContextEngine, make_live: Any, api_target: Any, keep_detail: bool = False) -> dict[str, Any]:
    """Everything the validation checks, from scratch (fresh engines, no cache shared with another pass). `src` is a graph source (live or twin)."""
    started = time.perf_counter()
    live = make_live()
    results = L.compare_datasets(src, keep_detail=keep_detail)
    protected = [r for r in results if r.protected] + L.compare_supplied_relationships(src, keep_detail=keep_detail)
    all_results = results + [r for r in protected if r.dataset.startswith("protected:")]
    summary = [r.summary() for r in all_results]
    engine_cmp = compare_engines(files, live)
    disc, logi, warr = discovery_rows(live, files), logistics_rows(live, files), warranty_rows(live, files)
    auth = authorization_rows(files, live)
    api = api_checks(api_target if api_target is not None else live)
    golden = golden_checks(live)
    ctxs = {"discovery": [live.build_discovery_context(t) for t, _ in DISCOVERY[:3]], "logistics": [live.build_logistics_context(shipment_id="SHP-NET-0001")],
            "warranty": [live.build_warranty_context(claim_id=c) for c in GOLDEN_WARRANTY]}
    evid = [{"domain": "discovery", "scenario": r["scenario"], **r["evidence_status"]} for r in disc if r["evidence_status"]["status"] != "NOT_APPLICABLE"]
    evid += [{"domain": "logistics", "scenario": r["shipment"], **r["evidence_status"]} for r in logi if r["evidence_status"].get("status") != "NOT_APPLICABLE"]
    evid += [{"domain": "warranty", "scenario": r["scenario"], **r["evidence_status"]} for r in warr]
    prov = [{"domain": k, "context": c.context_id, **provenance_status(c)} for k, v in ctxs.items() for c in v]
    prov += [{"domain": "warranty", "context": r["scenario"], "status": r["provenance_status"]} for r in warr]
    return {
        "entity_counts": L.entity_counts(src), "dataset_comparison": summary,
        "dataset_differences": {r.dataset: {"count": len(r.differences), "listed": r.differences[:500], "truncated": max(0, len(r.differences) - 500)} for r in all_results if r.differences},
        "dataset_samples": {r.dataset: r.samples[:12] for r in all_results if r.samples}, "dataset_detail": ({r.dataset: r.detail for r in all_results} if keep_detail else None),
        "protected_comparison": [r.summary() for r in all_results if r.protected], "normalization": L.normalization_report(all_results),
        "engine_files_vs_graph": engine_cmp, "discovery": disc, "logistics": logi, "warranty": warr, "authorization": auth, "apis": api, "api_endpoints": api_endpoint_summary(api),
        "golden": golden, "evidence": evid, "provenance": prov, "timing": {"duration_seconds": round(time.perf_counter() - started, 2)},
    }


def pass_failures(p: dict[str, Any]) -> dict[str, int]:
    g = lambda k: p.get(k, [])  # noqa: E731
    return {"entity_counts": sum(e["status"] != "PASS" for e in g("entity_counts")), "dataset_comparison": sum(d["status"] != "PASS" for d in g("dataset_comparison")),
            "protected_comparison": sum(d["status"] != "PASS" for d in g("protected_comparison")), "engine_files_vs_graph": len(p.get("engine_files_vs_graph", {}).get("different", {})),
            "discovery": sum(r["status"] != "PASS" for r in g("discovery")), "logistics": sum(r["status"] != "PASS" for r in g("logistics")), "warranty": sum(r["status"] != "PASS" for r in g("warranty")),
            "authorization": sum(r["status"] != "PASS" for r in g("authorization")), "apis": sum(not r["ok"] for r in g("apis")), "golden": sum(not r["ok"] for r in g("golden")),
            "evidence": sum(e["status"] != "PASS" for e in g("evidence")), "provenance": sum(e["status"] != "PASS" for e in g("provenance"))}


def business(p: dict[str, Any]) -> dict[str, Any]:
    """A pass without its time-dependent metadata."""
    return {k: v for k, v in p.items() if k != "timing"}


def determinism(p1: dict[str, Any], p2: dict[str, Any], s0: dict[str, Any], s1: dict[str, Any], s2: dict[str, Any]) -> dict[str, Any]:
    mism = diffs(L.json_safe(business(p1)), L.json_safe(business(p2)))
    snap = {k: [s0.get(k), s1.get(k), s2.get(k)] for k in s0 if not (s0.get(k) == s1.get(k) == s2.get(k))}
    return {"pass1_status": "PASS" if not any(pass_failures(p1).values()) else "FAIL", "pass2_status": "PASS" if not any(pass_failures(p2).values()) else "FAIL",
            "business_results_identical": not mism, "snapshot_identical": not snap, "mismatches": mism[:50], "snapshot_changes": snap, "excluded_as_time_dependent": ["validation_timestamp", "timing.duration_seconds"]}


def acceptance(mode: str, conn: dict[str, Any], p1: dict[str, Any] | None, det: dict[str, Any] | None, snaps: list[dict[str, Any]], ro: Any) -> list[dict[str, Any]]:
    """The machine-checkable PASS rules. BLOCKED = could not be evaluated because Neo4j was not reached (or OFFLINE); never PASS."""
    live = mode == "ONLINE" and conn.get("database_reachable")
    rows: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: Any = None, needs_graph: bool = True) -> None:
        status = "BLOCKED" if (needs_graph and not live) or ok is None else "PASS" if ok else "FAIL"
        rows.append({"criterion": name, "status": status, "detail": detail})

    add("DNS resolves", conn.get("dns_resolved") if mode == "ONLINE" else None, conn.get("host"))
    add("Neo4j TCP reachable", conn.get("tcp_reachable") if mode == "ONLINE" else None)
    add("authentication succeeds", conn.get("authentication") == "ok" if mode == "ONLINE" else None)
    add("database reachable", conn.get("database_reachable") if mode == "ONLINE" else None)
    f = pass_failures(p1) if p1 else {}
    for name, key in (("entity counts expected", "entity_counts"), ("field comparison has zero unexplained mismatches", "dataset_comparison"), ("protected data comparison has zero unexplained mismatches", "protected_comparison"),
                      ("engine(files) == engine(graph) on every scenario", "engine_files_vs_graph"), ("discovery golden scenarios", "discovery"), ("logistics golden scenarios", "logistics"),
                      ("warranty golden scenarios", "warranty"), ("authorization", "authorization"), ("API checks", "apis"), ("golden checks", "golden"), ("evidence checks", "evidence"), ("provenance checks", "provenance")):
        add(name, (f[key] == 0) if p1 and live else None, {"failures": f.get(key)})
    sn0, sn1, sn2 = (snaps + [{}, {}, {}])[:3]
    add("snapshot unchanged (before == after pass 1 == after pass 2)", (sn0 == sn1 == sn2) if live and sn0 else None)
    add("integrity checksum unchanged", (sn0.get("integrity_checksum") == sn1.get("integrity_checksum") == sn2.get("integrity_checksum")) if live and sn0 else None)
    add("fingerprint unchanged", (sn0.get("src_canon_graph_fingerprint") == sn1.get("src_canon_graph_fingerprint") == sn2.get("src_canon_graph_fingerprint")) if live and sn0 else None)
    add("pass 1 == pass 2", (det["business_results_identical"] and det["snapshot_identical"]) if live and det else None)
    add("only read queries were sent", (not ro.blocked) if ro is not None and live else None, {"queries": getattr(ro, "queries", None), "blocked_writes": getattr(ro, "blocked", None)})
    return rows


def classify_run(mode: str, conn: dict[str, Any], crit: list[dict[str, Any]]) -> dict[str, Any]:
    if mode != "ONLINE":
        return {"result": "BLOCKED", "phase_4h": "PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE", "reason": "OFFLINE mode never validates Neo4j"}
    if not conn.get("database_reachable"):
        why = "authentication failed" if conn.get("authentication") == "failed" else "DNS does not resolve" if not conn.get("dns_resolved") else "TCP connection failed" if not conn.get("tcp_reachable") else "database not reachable"
        return {"result": "BLOCKED", "phase_4h": "PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE", "reason": why}
    failed = [c["criterion"] for c in crit if c["status"] != "PASS"]
    if failed:
        return {"result": "FAIL", "phase_4h": "PHASE 4H FAILED — LIVE VALIDATION FOUND PRODUCT/DATA ISSUES", "reason": failed}
    return {"result": "PASS", "phase_4h": "PHASE 4H COMPLETE", "reason": "every acceptance criterion passed on the live graph, twice"}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    mode = "OFFLINE" if args.offline else "ONLINE"
    settings = get_settings()
    files = CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)
    report: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "mode": mode, "live_graph_verified": False, "validation_timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                              "connectivity": {}, "snapshot_before": {}, "entity_counts": [], "dataset_comparison": [], "discovery": [], "logistics": [], "warranty": [], "authorization": [],
                              "apis": [], "evidence": [], "provenance": [], "snapshot_after_pass1": {}, "snapshot_after_pass2": {}, "determinism": {}, "final_classification": ""}
    ro = None
    graph = None
    if mode == "OFFLINE":
        report["connectivity"] = {"mode": "OFFLINE", "note": "no connection attempted"}
        twin = L.MemorySource.from_files(CANON_DIR)
        src, make_live, api_target = twin, (lambda: CommerceContextEngine.from_files(CANON_DIR, as_of=AS_OF)), None
        snap = twin.snapshot
    else:
        conn = L.connectivity(settings)
        report["connectivity"] = conn
        if not conn["database_reachable"]:
            crit = acceptance(mode, conn, None, None, [], None)
            report["acceptance"] = crit
            report["final_classification_detail"] = classify_run(mode, conn, crit)
            report["final_classification"] = report["final_classification_detail"]["phase_4h"]
            report["timing"] = {"duration_seconds": round(time.perf_counter() - started, 2)}
            return report
        from app.graph.client import GraphClient

        graph = GraphClient(settings)
        ro = L.ReadOnlyGraph(graph)
        src = L.CypherSource(ro)
        make_live = lambda: CommerceContextEngine.from_graph(ro, as_of=AS_OF)  # noqa: E731
        api_target = ro
        snap = src.snapshot
    try:
        s0 = snap()
        report["snapshot_before"] = s0
        p1 = run_pass(src, files, make_live, api_target, args.full_detail)
        s1 = snap()
        p2 = run_pass(src, files, make_live, api_target, False)
        s2 = snap()
    finally:
        if graph is not None:
            graph.close()
    det = determinism(p1, p2, s0, s1, s2)
    report.update({k: p1[k] for k in ("entity_counts", "dataset_comparison", "discovery", "logistics", "warranty", "authorization", "apis", "evidence", "provenance")})
    report.update({"dataset_differences": p1["dataset_differences"], "dataset_samples": p1["dataset_samples"], "dataset_detail": p1["dataset_detail"], "protected_comparison": p1["protected_comparison"],
                   "normalization": p1["normalization"], "engine_files_vs_graph": p1["engine_files_vs_graph"], "api_endpoints": p1["api_endpoints"], "golden": p1["golden"],
                   "pass_failures": {"pass1": pass_failures(p1), "pass2": pass_failures(p2)}, "snapshot_after_pass1": s1, "snapshot_after_pass2": s2, "determinism": det,
                   "readonly": {"queries_executed": ro.queries if ro else None, "write_attempts_blocked": ro.blocked if ro else None, "snapshot_unchanged": s0 == s1 == s2}})
    # per-dataset table in the shape the acceptance review reads
    report["dataset_summary_table"] = [{"Dataset": d["dataset"], "Records checked": d["records_checked"], "Valid": d["valid"], "Invalid": d["invalid"], "Missing in graph": d["missing_in_graph"],
                                        "Missing in canonical": d["missing_in_canonical"], "Field mismatches": d["field_mismatches"], "Normalization-only differences": d["normalization_only"], "Status": d["status"]}
                                       for d in report["dataset_comparison"]]
    # legacy keys (earlier report consumers)
    report.update({"before": s0, "after": s1, "graph_unchanged": s0 == s1 == s2, "src_canon_fingerprint_matches_recorded": s0.get("src_canon_graph_fingerprint") == json.loads(
        (CANON_DIR / "integrity.json").read_text(encoding="utf-8")).get("graph_fingerprint") if mode == "ONLINE" else None, "files_vs_graph": p1["engine_files_vs_graph"],
        "golden_legacy": p1["golden"], "api": p1["apis"]})
    crit = acceptance(mode, report["connectivity"], p1, det, [s0, s1, s2], ro)
    report["acceptance"] = crit
    report["final_classification_detail"] = classify_run(mode, report["connectivity"], crit)
    report["final_classification"] = report["final_classification_detail"]["phase_4h"]
    report["live_graph_verified"] = bool(mode == "ONLINE" and report["final_classification_detail"]["result"] == "PASS")
    report["failures"] = sum(pass_failures(p1).values()) + (0 if det["business_results_identical"] and det["snapshot_identical"] else 1)
    if mode == "OFFLINE":
        report["offline_checks"] = {"harness_and_engine_logic": "PASS" if not any(pass_failures(p1).values()) and det["business_results_identical"] else "FAIL", "pass_failures": pass_failures(p1),
                                    "note": "Compared against an in-memory twin of the canonical files. This validates the validator and the engine logic, not Neo4j."}
    report["timing"] = {"duration_seconds": round(time.perf_counter() - started, 2)}
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--offline", action="store_true", help="validate against an in-memory twin of the canonical files; never reports live_graph_verified")
    ap.add_argument("--full-detail", action="store_true", help="include every compared field (large), not only the differences and samples")
    args = ap.parse_args()
    import logging

    logging.disable(logging.INFO)  # the in-process HTTP client logs every request; the report is the output
    report = build_report(args)
    text = json.dumps(L.json_safe(report), indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    c = report["connectivity"]
    print(f"mode={report['mode']}  live_graph_verified={report['live_graph_verified']}")
    if report["mode"] == "ONLINE":
        print(f"host={c.get('host')}  DNS={'yes' if c.get('dns_resolved') else 'no'}  TCP={'yes' if c.get('tcp_reachable') else 'no'}  authentication={c.get('authentication')}  database={'yes' if c.get('database_reachable') else 'no'}")
    for a in report["acceptance"]:
        print(f"  {a['status']:8} {a['criterion']}")
    if report["mode"] == "OFFLINE":
        print(f"  offline checks (harness + engine logic, NOT Neo4j): {report['offline_checks']['harness_and_engine_logic']}  {report['offline_checks']['pass_failures']}")
    print(report["final_classification"] + (f"  ({report['final_classification_detail']['reason']})" if report["final_classification_detail"]["result"] != "PASS" else ""))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["final_classification_detail"]["result"]]


if __name__ == "__main__":
    sys.exit(main())
