"""Phase 5 vertical-slice validation: the four user flows through the REAL API (FastAPI app, real session cookie, real commerce engine) against the LIVE Neo4j graph. READ-ONLY.

    python backend/scripts/commerce_agent_flows.py [--out flows.json] [--no-llm]

Nothing is overridden: the app's own dependencies build the graph client, the engine and (unless --no-llm) the configured language model. Each flow signs in as a seeded demo user
(Anna / Lars: end customers; Jane: order processor), posts to /api/v1/commerce/agent exactly as the browser does and checks the answer against the Phase 4 contexts it carries.
The graph snapshot (node and relationship counts, protected counts, integrity checksum, SRC-CANON fingerprint) is taken before and after: a difference fails the run.
Exit code 0 = every flow passed and the graph is unchanged; 1 = a flow failed; 2 = Neo4j unreachable (BLOCKED, never a pass).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "scripts" / "eu_foundation"))

import commerce_validation_lib as L  # noqa: E402
from app.api.dependencies import get_llm  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

USERS = {"anna": "USR-EU-001", "lars": "USR-EU-002", "jane": "USR-OP-001"}
KEEP = ("node_count", "relationship_count", "protected_node_count", "protected_relationship_count", "integrity_checksum", "src_canon_graph_fingerprint", "label_counts", "relationship_type_counts")


def client(user: str) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"user_id": USERS[user]})
    if r.status_code != 200:
        raise SystemExit(f"cannot sign in as {user}: {r.status_code}")
    return c


def post(c: TestClient, body: dict[str, Any]) -> tuple[int, dict[str, Any], float]:
    t = time.perf_counter()
    r = c.post("/api/v1/commerce/agent", json=body)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}), time.perf_counter() - t


class Run:
    def __init__(self) -> None:
        self.flows: list[dict[str, Any]] = []

    def flow(self, name: str, user: str, calls: list[dict[str, Any]], check) -> None:
        c, results, problems = client(user), [], []
        state: dict[str, Any] = {}
        for call in calls:
            body = {**call, "state": {**state, **call.get("state", {})}}
            status, data, secs = post(c, body)
            if status == 200:
                state = data.get("state", {})
            results.append({"request": body["message"], "http": status, "seconds": round(secs, 1), "intent": data.get("intent"), "status": data.get("status"),
                            "sections": [{"domain": s["domain"], "decision": s["decision"], "headline": s["headline"], "lines": s["lines"]} for s in data.get("answer", {}).get("sections", [])],
                            "answer": data.get("answer", {}).get("text"), "grounding": data.get("answer", {}).get("grounding"), "evidence_items": len(data.get("evidence", [])),
                            "evidence_path_steps": {d: len(p) for d, p in data.get("evidence_paths", {}).items()}, "source_records": len(data.get("source_records", [])),
                            "data_status": data.get("data_status"), "visibility": data.get("visibility"), "clarification": data.get("clarification"), "_data": data})
        try:
            check(results, problems)
        except AssertionError as exc:  # a failed expectation is a failed flow, with the reason
            problems.append(str(exc) or "assertion failed")
        for r in results:
            r.pop("_data")
        self.flows.append({"flow": name, "user": user, "passed": not problems, "problems": problems, "turns": results})


def need(cond: bool, message: str, problems: list[str]) -> None:
    if not cond:
        problems.append(message)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--no-llm", action="store_true", help="run with no language model (the deterministic path)")
    a = ap.parse_args()
    settings = get_settings()
    if not settings.graph_configured:
        print("BLOCKED: Neo4j is not configured")
        return 2
    conn = L.connectivity(settings)
    if not conn["database_reachable"]:
        print("BLOCKED: Neo4j unreachable —", {k: conn.get(k) for k in ("dns_resolved", "tcp_reachable", "authentication", "error_class")})
        return 2
    if a.no_llm:
        app.dependency_overrides[get_llm] = lambda: None
    ro = L.CypherSource(L.ReadOnlyGraph(GraphClient(dataclasses.replace(settings, neo4j_query_timeout=120.0))))
    before = ro.snapshot()
    run = Run()

    def flow_a(r: list[dict], p: list[str]) -> None:
        d = r[0]["_data"]
        need(r[0]["http"] == 200 and r[0]["intent"] == "DISCOVERY" and r[0]["sections"][0]["decision"] == "RECOMMEND", f"A: expected a RECOMMEND discovery answer, got {r[0]['intent']}/{r[0]['sections']}", p)
        ctx = d["contexts"]["DISCOVERY"]
        need(ctx["recommended_part"] is not None and ctx["recommended_part"]["fitment"] == "APPROVED" and ctx["recommended_part"]["approved_source"] is True, "A: the recommended part is not fitment-approved with an approved source", p)
        offered = json.dumps([ctx["recommended_part"], ctx["compatible_part"], ctx["alternatives"], ctx["unconfirmed_matches"]])
        need(not any(x in offered for x in ctx["decision"]["facts"].get("canonical_type_mismatches", ["?"])), "A: a canonical type mismatch was offered", p)
        need(r[0]["evidence_path_steps"].get("DISCOVERY", 0) >= 3 and r[0]["source_records"] > 0 and r[0]["data_status"] in ("MIXED", "SYNTHETIC_DEMO"), "A: evidence path, source records or data status missing", p)
        need(d["answer"]["synthetic_notice"] is not None, "A: the demonstration-data disclosure is missing", p)
        need("warehouses" not in json.dumps(ctx["availability"]), "A: internal depot stock reached a customer", p)

    def flow_b(r: list[dict], p: list[str]) -> None:
        x = r[0]["_data"]["contexts"]["LOGISTICS"]
        need(r[0]["http"] == 200 and r[0]["intent"] == "LOGISTICS", f"B: expected logistics, got {r[0]['intent']}", p)
        need(x["shipment_kind"] == "MULTI_LINE" and x["part"] is None and len(x["shipment_lines"]) == 2 and len(x["parts"]) == 2, "B: SHP-0010 must be a two-line shipment with no single part", p)
        need([ln["order_line_id"] for ln in x["shipment_lines"]] == ["OI-0021", "OI-0022"], "B: the two ShipmentLine records are not returned", p)
        text = "\n".join(l for s in r[0]["sections"] for l in s["lines"])
        need("NVM-1010-HY" in text and "NVM-1100-DT" in text, "B: the answer does not list both parts", p)
        need(x["order_split"] is False and "remediation_flags" not in x["shipment"], "B: order split or an internal flag shown", p)

    def flow_c(r: list[dict], p: list[str]) -> None:
        need(r[0]["status"] == "REQUIRES_CLARIFICATION" and r[0]["clarification"]["options"], "C: the first turn must ask which machine (and offer the customer's own)", p)
        need({o["machine_instance_id"] for o in r[0]["clarification"]["options"]} == {"MI-0001", "MI-0011", "MI-G001", "MI-G005"}, "C: the options are not exactly the customer's own machines", p)
        w = r[-1]["_data"]["contexts"].get("WARRANTY")
        need(w is not None and w["decision"]["facts"].get("outcome") == "ELIGIBLE" and w["claim"]["claim_id"] == "CLM-G001", "C: CLM-G001 must be ELIGIBLE", p)
        need(w is not None and len(w["decision_factors"]) >= 9 and all(f["status"] == "PASS" for f in w["decision_factors"]) and w["work_order"] and w["installation"], "C: checks, installation and work order missing", p)
        need("Hendrik" not in json.dumps(r[-1]["_data"]) and "technician.name" in w["visibility"]["hidden_fields"], "C: the technician's name reached a customer", p)

    def flow_d(r: list[dict], p: list[str]) -> None:
        d = r[0]["_data"]
        s = {x["domain"]: x for x in r[0]["sections"]}
        need(r[0]["intent"] == "MULTI_DOMAIN" and list(s) == ["DISCOVERY", "WARRANTY", "LOGISTICS"], f"D: expected discovery+warranty+logistics, got {r[0]['intent']} {list(s)}", p)
        need(s["DISCOVERY"]["decision"] == "NO_AVAILABLE_RECOMMENDATION" and s["WARRANTY"]["decision"] == "ELIGIBLE" and s["LOGISTICS"]["decision"] == "NO_SHIPMENT_FOR_UNORDERED_PART", f"D: unexpected decisions { {k: v['decision'] for k, v in s.items()} }", p)
        need(d["contexts"]["DISCOVERY"]["compatible_part"]["part_id"] == "PRT-007" and d["contexts"]["DISCOVERY"]["recommended_part"] is None and d["contexts"]["DISCOVERY"]["alternatives"] == [], "D: an unavailable correct part was replaced by another", p)
        need({e["domain"] for e in d["evidence"]} == {"DISCOVERY", "WARRANTY"} and set(d["evidence_paths"]) == {"DISCOVERY", "WARRANTY"}, "D: evidence from both grounded journeys expected", p)

    run.flow("A discovery: Find a hydraulic pump for KFT-200", "lars", [{"message": "Find a hydraulic pump for KFT-200."}], flow_a)
    run.flow("B logistics: Where is SHP-0010 and what parts are in it", "lars", [{"message": "Where is SHP-0010 and what parts are in it?"}], flow_b)
    run.flow("C warranty: Is this failed part covered by warranty (pick machine, part)", "lars", [{"message": "Is this failed part covered by warranty?"},
             {"message": "Is this failed part covered by warranty?", "state": {"machine_instance_id": "MI-G001"}}, {"message": "Is this failed part covered by warranty?", "state": {"machine_instance_id": "MI-G001", "part_id": "PRT-007"}}], flow_c)
    run.flow("D multi-domain: replacement pump urgently, covered, how fast", "lars", [{"message": "I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?", "state": {"machine_instance_id": "MI-G001"}}], flow_d)

    def clarification(r: list[dict], p: list[str]) -> None:
        need(r[0]["status"] == "REQUIRES_CLARIFICATION" and "pending_message" in r[0]["_data"]["state"], "E: the first turn must ask and remember the waiting question", p)
        need(r[1]["intent"] == "MULTI_DOMAIN" and r[1]["sections"][0]["decision"] == "NO_AVAILABLE_RECOMMENDATION", "E: the typed machine model must be read as the answer and continue the request", p)
        need(r[1]["clarification"] and {o["machine_instance_id"] for o in r[1]["clarification"]["options"]} == {"MI-G001", "MI-G005"}, "E: only the customer's two KFT-600 machines may be offered", p)
        need(r[2]["status"] == "PARTIAL" and {s["domain"]: s["decision"] for s in r[2]["sections"]}.get("WARRANTY") == "ELIGIBLE" and "pending_message" not in r[2]["_data"]["state"], "E: choosing a machine must finish the original request", p)

    def shop_order(r: list[dict], p: list[str]) -> None:
        x = r[0]["_data"]["contexts"].get("LOGISTICS")
        need(r[0]["http"] == 200 and x is not None and x["order"]["order_id"] == "HCME-ORD-000001" and x["shipment"] is None, "F: the owner must see the shop order with no shipment", p)
        need(x is not None and x["order"].get("status") == "ALLOCATED" and len(x["order_lines"]) >= 1 and r[0]["sections"][0]["decision"] == "NO_SHIPMENT_RECORDED", "F: order status, lines and the no-shipment statement expected", p)
        need(r[1]["http"] == 403 and r[1]["_data"].get("error", {}).get("code") == "forbidden", "F: another customer must be refused", p)
        need(r[2]["http"] == 200 and r[2]["_data"]["visibility"]["LOGISTICS"]["role"] == "OEM", "F: the OEM must see the order", p)

    def part_questions(r: list[dict], p: list[str]) -> None:
        fit, origin = r[1]["_data"]["contexts"]["DISCOVERY"], r[2]["_data"]["contexts"]["DISCOVERY"]
        need(fit.get("lookup") == "PART_FITMENT" and [m["model"] for m in fit["machines"]] == ["KFT-200", "KFT-450"], f"G: which machines use the part: {[m['model'] for m in fit.get('machines', [])]}", p)
        need(origin.get("lookup") == "PART_ORIGIN" and [s["source_id"] for s in origin["sources"]] == ["SUP-011", "SUP-025"] and r[2]["source_records"] > 0, "G: where the part came from: approved sources and provenance expected", p)

    def security(r: list[dict], p: list[str]) -> None:
        need([x["http"] for x in r] == [403, 403, 403], f"security: expected three 403s for another customer's records, got {[x['http'] for x in r]}", p)
        need(all(x["_data"].get("error", {}).get("code") == "forbidden" and "Hendrik" not in json.dumps(x["_data"]) for x in r), "security: the refusal must be the generic forbidden error", p)

    run.flow("E clarification: ask, answer in a few words, choose, finish", "lars", [{"message": "I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?"}, {"message": "KFT-600"},
             {"message": "KFT-600", "state": {"machine_instance_id": "MI-G001"}}], clarification)
    # three principals, one flow: owner, another customer, OEM
    c_lars, c_anna, c_jane = client("lars"), client("anna"), client("jane")
    results, problems = [], []
    for c, name in ((c_lars, "lars"), (c_anna, "anna"), (c_jane, "jane")):
        status, data, secs = post(c, {"message": "Where is order HCME-ORD-000001?", "state": {}})
        results.append({"request": name, "http": status, "seconds": round(secs, 1), "intent": data.get("intent"), "status": data.get("status"),
                        "sections": [{"domain": x["domain"], "decision": x["decision"], "headline": x["headline"], "lines": x["lines"]} for x in data.get("answer", {}).get("sections", [])],
                        "answer": data.get("answer", {}).get("text"), "grounding": data.get("answer", {}).get("grounding"), "source_records": len(data.get("source_records", [])), "_data": data})
    try:
        shop_order(results, problems)
    except AssertionError as exc:
        problems.append(str(exc))
    for r in results:
        r.pop("_data")
    run.flows.append({"flow": "F shop order: Where is order HCME-ORD-000001 (owner, another customer, OEM)", "user": "lars/anna/jane", "passed": not problems, "problems": problems, "turns": results})
    run.flow("G part questions: which machines use it, where it came from", "lars", [{"message": "Find a hydraulic pump for KFT-200."}, {"message": "Which machine uses this part?"}, {"message": "Where did this part come from?"}], part_questions)

    run.flow("Security: Anna cannot reach Lars's shipment, claim or machine", "anna", [{"message": "Where is SHP-0010?"}, {"message": "Is claim CLM-G001 covered?"},
             {"message": "Is it covered?", "state": {"machine_instance_id": "MI-G001", "part_id": "PRT-007"}}], security)

    def oem(r: list[dict], p: list[str]) -> None:
        w = r[0]["_data"]["contexts"]["WARRANTY"]
        need("Hendrik Vos (demo)" in json.dumps(w) and r[0]["_data"]["visibility"]["WARRANTY"]["role"] == "OEM", "OEM: must see the technician and the OEM view", p)
        need("remediation_flags" in r[1]["_data"]["contexts"]["LOGISTICS"]["shipment"], "OEM: must see the internal shipment flags", p)

    run.flow("OEM access: Jane sees what the customer view hides", "jane", [{"message": "Who installed the part on claim CLM-G001?"}, {"message": "Where is SHP-0010?"}], oem)

    after = ro.snapshot()
    changed = [k for k in KEEP if before[k] != after[k]]
    report = {"mode": "LIVE", "llm": "disabled" if a.no_llm else (settings.llm_provider if settings.llm_configured else "not configured"), "flows": run.flows,
              "graph": {"before": {k: before[k] for k in KEEP if k.endswith(("count", "checksum", "fingerprint"))}, "after": {k: after[k] for k in KEEP if k.endswith(("count", "checksum", "fingerprint"))},
                        "unchanged": not changed, "changed_measures": changed}}
    ok = all(f["passed"] for f in run.flows) and not changed
    report["passed"] = ok
    for f in run.flows:
        print(("PASS " if f["passed"] else "FAIL ") + f["flow"] + "".join(f"\n      - {x}" for x in f["problems"]))
    print(f"graph unchanged: {not changed}  (nodes {before['node_count']} -> {after['node_count']}, relationships {before['relationship_count']} -> {after['relationship_count']}, checksum {after['integrity_checksum'][:12]})")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
