"""Live scenario matrix for the one Agentic E-Commerce screen (READ-ONLY).

    python backend/scripts/agentic_ecommerce_matrix.py [--base http://localhost:8000] [--out matrix.json]

Each scenario runs exactly as the screen does: POST /agent/recommend (Agentic Shopping), then, when the response names commerce_domains and the user is signed in,
POST /commerce/agent with the same message (orders, shipments, warranty). Users are the seeded demo accounts; nothing is written (no cart, no order). The check of each
scenario is stated next to it; the result is PASS or FAIL with what was observed. Exit code 0 when every scenario passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

import httpx

USERS = {"lars": "USR-EU-002", "anna": "USR-EU-001", "jane": "USR-OP-001"}


class Client:
    def __init__(self, base: str, user: str | None) -> None:
        self.http = httpx.Client(base_url=base, timeout=180)
        if user:
            r = self.http.post("/api/v1/auth/login", json={"user_id": USERS[user]})
            r.raise_for_status()

    def run(self, message: str) -> dict[str, Any]:
        s = self.http.post("/api/v1/agent/recommend", json={"request": message})
        out: dict[str, Any] = {"shopping_http": s.status_code}
        if s.status_code != 200:
            return out
        d = s.json()
        rec = next((c for c in d.get("candidates", []) if c.get("recommended")), None)
        out.update(state=d["state"], question=d.get("question"), recommended=rec["part"]["part_number"] if rec else None,
                   fits=[f["model_code"] for f in rec["part"]["fitment"]] if rec else [], interpretation=d.get("interpretation"), commerce_domains=d.get("commerce_domains", []),
                   delivery=d.get("delivery"), can_add_to_cart=rec.get("can_add_to_cart") if rec else None, candidates=len(d.get("candidates", [])))
        if out["commerce_domains"]:
            c = self.http.post("/api/v1/commerce/agent", json={"message": message, "state": {}})
            out["commerce_http"] = c.status_code
            if c.status_code == 200:
                a = c.json()
                out.update(commerce_intent=a["intent"], commerce_status=a["status"], clarification=(a.get("clarification") or {}).get("question"),
                           clarification_options=len((a.get("clarification") or {}).get("options") or []),
                           sections={x["domain"]: {"decision": x["decision"], "headline": x["headline"], "lines": x["lines"][:12]} for x in a["answer"]["sections"]})
        return out


def text(o: dict[str, Any]) -> str:
    return json.dumps(o, default=str)


Check = Callable[[dict[str, Any]], bool]
SCENARIOS: list[tuple[str, str, str | None, str, str, Check]] = [
    # (id, group, user, message, expected, check)
    ("A1", "Parts discovery", "lars", "I need a hydraulic pump.", "asks which machine; recommends nothing", lambda r: r["state"] == "need_machine" and not r["recommended"]),
    ("A2", "Parts discovery", "lars", "Find an air filter for my NV-3200.", "recommends an air filter with recorded fitment for NV-3200", lambda r: r["state"] == "recommendation" and "NV-3200" in r["fits"]),
    ("A3", "Parts discovery", "lars", "Find a hydraulic pump for my KFT-200.", "recommends NVM-1050-HY (the only verified fit)", lambda r: r["recommended"] == "NVM-1050-HY"),
    ("A4", "Parts discovery", "lars", "I need a replacement part for my machine.", "asks for the machine or the part", lambda r: r["state"] in ("need_machine", "need_part", "need_detail") and not r["recommended"]),
    ("A5", "Parts discovery", "lars", "I need a hydrualic pomp for my KFT-200", "misspelling: either reads it or asks; never a wrong part", lambda r: r["recommended"] in (None, "NVM-1050-HY")),
    ("A6", "Parts discovery", "lars", "I need part NVM-9999-XX", "unknown part number: nothing invented", lambda r: not r["recommended"]),
    ("A7", "Parts discovery", "lars", "I need a flux capacitor for my NV-3200", "not in the catalogue: nothing recommended", lambda r: not r["recommended"]),
    ("B1", "Compatibility", "lars", "Which parts fit my NV-3200?", "no part claimed without fitment; asks or lists verified fits", lambda r: not r["recommended"] or "NV-3200" in r["fits"]),
    ("B2", "Compatibility", "lars", "Is this hydraulic pump compatible with the KFT-200?", "only a verified fit for KFT-200", lambda r: not r["recommended"] or "KFT-200" in r["fits"]),
    ("B3", "Compatibility", "lars", "Which machines use NVM-1050-HY?", "commerce part lookup: approved for KFT-200 and KFT-450", lambda r: "KFT-200" in text(r.get("sections", {})) and "KFT-450" in text(r.get("sections", {}))),
    ("B4", "Compatibility", "lars", "Find a hydraulic pump for my XYZ-999", "unknown machine: asks, recommends nothing", lambda r: not r["recommended"]),
    ("B5", "Compatibility", "lars", "Find a bucket for my KFT", "machine family only: asks which model", lambda r: not r["recommended"] and r["state"] != "recommendation"),
    ("C1", "Budget and ranking", "lars", "Find the cheapest cooling fan for the NV-4500.", "cheapest preference applied; verified fit for NV-4500", lambda r: r["interpretation"]["preference"] == "cheapest" and (not r["recommended"] or "NV-4500" in r["fits"])),
    ("C2", "Budget and ranking", "lars", "Find a bucket under €220 for my NV-3200.", "budget read; no bucket within it, so no recommendation and a stated reason", lambda r: r["interpretation"].get("budget_max") == 220 and r["state"] == "no_match"),
    ("C3", "Budget and ranking", "lars", "Find the best available bucket for my NV-3200", "a verified, available bucket for NV-3200", lambda r: r["state"] == "recommendation" and "NV-3200" in r["fits"]),
    ("C4", "Budget and ranking", "lars", "I need 3 air filters for my NV-3200", "quantity 3 read", lambda r: r["interpretation"].get("quantity") == 3),
    ("C5", "Budget and ranking", "lars", "Find an air filter for my NV-3200 under €1", "no option meets the budget; explained", lambda r: r["state"] == "no_match"),
    ("D1", "Delivery and logistics", "lars", "How quickly can I get an air filter for my NV-3200 delivered to Aalborg?", "delivery to Aalborg from the recorded route", lambda r: (r.get("delivery") or {}).get("city") == "Aalborg"),
    ("D2", "Delivery and logistics", "lars", "Find the fastest option to Aalborg for an air filter for my NV-3200", "fastest preference and Aalborg", lambda r: r["interpretation"]["preference"] == "fastest" and (r.get("delivery") or {}).get("city") == "Aalborg"),
    ("D3", "Delivery and logistics", "jane", "Compare sea and air for shipment SHP-NET-0001", "recorded sea and air routes with their own days", lambda r: "RTE-NET-JPNL-AIR-EXP (AIR), 6 days" in text(r.get("sections", {}))),
    ("D4", "Delivery and logistics", "lars", "Can a hydraulic pump for my KFT-200 be delivered to Lagos?", "potential routes to Lagos, labelled as not assigned", lambda r: r.get("sections", {}).get("LOGISTICS", {}).get("decision") == "ROUTE_OPTIONS"),
    ("D5", "Delivery and logistics", "lars", "Where is my shipment?", "the customer's own shipment, its status", lambda r: r.get("commerce_http") == 200 and "LOGISTICS" in r.get("sections", {})),
    ("D6", "Delivery and logistics", "lars", "Which parts are included in my shipment?", "the shipment's order lines, not a part search", lambda r: list(r.get("sections", {})) == ["LOGISTICS"]),
    ("D7", "Delivery and logistics", "jane", "Is shipment SHP-NET-0003 overdue?", "past the planned ETA, no new ETA invented", lambda r: "Past the planned ETA" in text(r.get("sections", {}))),
    ("D8", "Delivery and logistics", "jane", "What is the planned ETA of shipment SHP-NET-0001?", "the recorded planned ETA", lambda r: "2026-11-19" in text(r.get("sections", {}))),
    ("D9", "Delivery and logistics", "jane", "Where is shipment SHP-NET-0004?", "delivered", lambda r: r.get("sections", {}).get("LOGISTICS", {}).get("decision") == "DELIVERED"),
    ("D10", "Delivery and logistics", "jane", "Where is shipment SHP-NET-9999?", "a well-formed but unknown shipment id: not recorded", lambda r: r.get("sections", {}).get("LOGISTICS", {}).get("decision") == "NOT_FOUND"),
    ("D12", "Delivery and logistics", "jane", "Where is shipment SHP-NOPE-0001?", "not an id the agent recognises: asks for a shipment or order number, invents none", lambda r: r.get("commerce_status") == "REQUIRES_CLARIFICATION"),
    ("D11", "Delivery and logistics", "lars", "How long does shipping to Atlantis take?", "no route invented for an unknown place and no unrelated shipment shown", lambda r: "ROUTE_OPTIONS" not in text(r) and not r.get("sections")),
    ("E1", "Orders", "lars", "Show me the status of my order.", "the customer's own order(s), or a question listing only theirs", lambda r: r.get("commerce_http") == 200 and ("LOGISTICS" in r.get("sections", {}))),
    ("E2", "Orders", "lars", "What parts are in order HCME-ORD-000001?", "the order and its lines", lambda r: "HCME-ORD-000001" in text(r.get("sections", {}))),
    ("E3", "Orders", "lars", "Has order HCME-ORD-000001 shipped?", "no shipment recorded yet, said so", lambda r: r.get("sections", {}).get("LOGISTICS", {}).get("decision") == "NO_SHIPMENT_RECORDED"),
    ("E4", "Orders", "lars", "Where is order ORD-99999999?", "unknown order: refused or not found, nothing shown", lambda r: r.get("commerce_http") in (403, 200) and "status ALLOCATED" not in text(r)),
    ("E5", "Orders", "anna", "Where is order HCME-ORD-000001?", "another customer's order: 403", lambda r: r.get("commerce_http") == 403),
    ("F1", "Warranty", "lars", "Is this failed part covered by warranty?", "asks which claim/machine, offering only the customer's own", lambda r: r.get("commerce_status") == "REQUIRES_CLARIFICATION" and r.get("clarification_options", 0) >= 1),
    ("F2", "Warranty", "lars", "Is claim CLM-G001 covered?", "ELIGIBLE from the rules", lambda r: r.get("sections", {}).get("WARRANTY", {}).get("decision") == "ELIGIBLE"),
    ("F3", "Warranty", "jane", "Why was claim CLM-G003 rejected?", "NOT_ELIGIBLE: coverage expired", lambda r: r.get("sections", {}).get("WARRANTY", {}).get("decision") == "NOT_ELIGIBLE" and "Coverage ended" in text(r.get("sections", {}))),
    ("F4", "Warranty", "jane", "What evidence is available for claim CLM-G006?", "INSUFFICIENT_DATA, the missing records named", lambda r: r.get("sections", {}).get("WARRANTY", {}).get("decision") == "INSUFFICIENT_DATA"),
    ("F5", "Warranty", "jane", "Is claim CLM-NOPE covered?", "not recorded", lambda r: r.get("sections", {}).get("WARRANTY", {}).get("decision") == "NOT_FOUND"),
    ("F6", "Warranty", "anna", "Is claim CLM-G001 covered?", "another customer's claim: 403", lambda r: r.get("commerce_http") == 403),
    ("G1", "Combined", "lars", "I urgently need a replacement hydraulic pump for my machine. Find a compatible part, compare the available delivery options, and check whether the failed part is covered by warranty.",
     "asks which machine for the part (no guess) and answers or asks about the warranty", lambda r: not r["recommended"] and "WARRANTY" in r["commerce_domains"] and r.get("commerce_http") == 200),
    ("G2", "Combined", "lars", "Find a hydraulic pump for my KFT-200 delivered to Aalborg, and has order HCME-ORD-000001 shipped?", "the part, its delivery, and the order's shipment status",
     lambda r: r["recommended"] == "NVM-1050-HY" and "LOGISTICS" in r["commerce_domains"] and "HCME-ORD-000001" in text(r.get("sections", {}))),
    ("I1", "Conversation", "lars", "hello", "declined, no domain, nothing invented", lambda r: r["state"] == "out_of_scope" and r["commerce_domains"] == []),
    ("I2", "Conversation", None, "Where is my shipment?", "signed out: the screen asks to sign in (commerce API 401)", lambda r: r["commerce_domains"] == ["LOGISTICS"] and r.get("commerce_http") == 401),
    ("I3", "Permissions", "jane", "Where is order HCME-ORD-000001?", "order processor sees the order", lambda r: r.get("commerce_http") == 200 and "HCME-ORD-000001" in text(r.get("sections", {}))),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    clients: dict[str | None, Client] = {}
    rows = []
    for sid, group, user, message, expected, check in SCENARIOS:
        if args.only and sid not in args.only:
            continue
        c = clients.setdefault(user, Client(args.base, user))
        try:
            r = c.run(message)
            ok = r.get("shopping_http") == 200 and bool(check(r))
        except Exception as exc:  # a broken scenario is a FAIL with its error, never a pass
            r, ok = {"error": repr(exc)}, False
        rows.append({"id": sid, "group": group, "user": user or "signed out", "message": message, "expected": expected, "result": "PASS" if ok else "FAIL", "observed": r})
        print(f"{'PASS' if ok else 'FAIL'}  {sid:4} {message[:80]}")
    empty = clients.setdefault("lars", Client(args.base, "lars")).http.post("/api/v1/agent/recommend", json={"request": ""}).status_code
    rows.append({"id": "I4", "group": "Conversation", "user": "lars", "message": "(empty)", "expected": "refused before anything runs (422)", "result": "PASS" if empty == 422 else "FAIL", "observed": {"shopping_http": empty}})
    print(f"{'PASS' if empty == 422 else 'FAIL'}  I4   (empty input) -> {empty}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, default=str)
    fails = [r for r in rows if r["result"] != "PASS"]
    print(f"\n{len(rows) - len(fails)} passed, {len(fails)} failed of {len(rows)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
