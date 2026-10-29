"""Live functional test suite for the one Agentic E-Commerce screen (READ-ONLY).

    python backend/scripts/agentic_ecommerce_matrix.py [--base http://localhost:8000] [--out matrix.json] [--only ID ...]

Every scenario runs exactly as the screen does: POST /agent/recommend (Agentic Shopping), then, when the response names commerce_domains and the user is signed in,
POST /commerce/agent with the same message (orders, shipments, warranty, part questions). Users are the seeded demo accounts (Lars and Anna: End Users of two different
customers; Jane: Order Processor). Nothing is written: no cart line, no order. Each scenario states what it expects; the result is PASS or FAIL with what was observed, and
a scenario that errors is a FAIL. Exit code 0 when every scenario passes.
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
        self.http = httpx.Client(base_url=base, timeout=240)
        if user:
            self.http.post("/api/v1/auth/login", json={"user_id": USERS[user]}).raise_for_status()

    def run(self, message: str) -> dict[str, Any]:
        s = self.http.post("/api/v1/agent/recommend", json={"request": message})
        out: dict[str, Any] = {"shopping_http": s.status_code}
        if s.status_code != 200:
            return out
        d = s.json()
        cands = d.get("candidates", [])
        rec = next((c for c in cands if c.get("recommended")), None)
        out.update(state=d["state"], question=d.get("question"), recommended=rec["part"]["part_number"] if rec else None, rec_name=rec["part"]["name"] if rec else None,
                   fits=[f["model_code"] for f in rec["part"]["fitment"]] if rec else [], fitment_label=rec.get("fitment_label") if rec else None,
                   availability_label=rec.get("availability_label") if rec else None, can_add_to_cart=rec.get("can_add_to_cart") if rec else None,
                   price=(rec["part"].get("price") or {}).get("amount") if rec else None, price_status=(rec["part"].get("price") or {}).get("data_status") if rec else None,
                   within_budget=rec.get("within_budget") if rec else None, interpretation=d.get("interpretation") or {}, commerce_domains=d.get("commerce_domains", []),
                   delivery=d.get("delivery"), evidence=len(d.get("evidence", [])), why=len(d.get("why", [])),
                   candidates=[{"no": c["part"]["part_number"], "price": (c["part"].get("price") or {}).get("amount"), "eligible": c.get("can_add_to_cart"), "fits": [f["model_code"] for f in c["part"]["fitment"]],
                                "availability": c.get("availability_label")} for c in cands])
        if out["commerce_domains"]:
            c = self.http.post("/api/v1/commerce/agent", json={"message": message, "state": {}})
            out["commerce_http"] = c.status_code
            if c.status_code == 200:
                a = c.json()
                out.update(commerce_intent=a["intent"], commerce_status=a["status"], clarification=(a.get("clarification") or {}).get("question"),
                           clarification_options=len((a.get("clarification") or {}).get("options") or []), data_status=a.get("data_status"),
                           sections={x["domain"]: {"decision": x["decision"], "headline": x["headline"], "lines": x["lines"][:14]} for x in a["answer"]["sections"]})
        return out


def text(o: Any) -> str:
    return json.dumps(o, default=str)


def sec(r: dict[str, Any], domain: str) -> dict[str, Any]:
    return (r.get("sections") or {}).get(domain) or {}


def no_rec(r: dict[str, Any]) -> bool:
    return not r.get("recommended")


def fits(r: dict[str, Any], model: str) -> bool:
    return bool(r.get("recommended")) and model in r["fits"] and r.get("fitment_label") == "Confirmed fit"


def cheapest_eligible(r: dict[str, Any]) -> bool:
    """The recommended part has the lowest recorded price among the eligible candidates (the cheapest preference is deterministic)."""
    prices = [c["price"] for c in r.get("candidates", []) if c["eligible"] and c["price"] is not None]
    return bool(prices) and r.get("price") == min(prices)


def honest_price(r: dict[str, Any]) -> bool:
    """A price is shown only when recorded, and it is labelled as demonstration data."""
    return r.get("price") is None or r.get("price_status") == "SYNTHETIC_DEMO"


def no_rec_without_fit(r: dict[str, Any], model: str | None = None) -> bool:
    """Nothing is recommended without recorded fitment (for the named model, when one is named)."""
    return no_rec(r) or (r.get("fitment_label") == "Confirmed fit" and (model is None or model in r["fits"]))


Check = Callable[[dict[str, Any]], bool]
# (id, area, user, message, expected, check)
SCENARIOS: list[tuple[str, str, str | None, str, str, Check]] = [
    # 1. natural-language parts discovery
    ("P1", "Parts discovery", "lars", "I need a hydraulic pump.", "asks which machine; recommends nothing", lambda r: r["state"] == "need_machine" and no_rec(r)),
    ("P2", "Parts discovery", "lars", "Find a hydraulic pump for my KFT-200.", "NVM-1050-HY, confirmed fit for KFT-200, labelled demo price", lambda r: r["recommended"] == "NVM-1050-HY" and fits(r, "KFT-200") and honest_price(r)),
    ("P3", "Parts discovery", "lars", "I need an air filter for my NV-3200.", "an air filter with confirmed fit for NV-3200", lambda r: fits(r, "NV-3200") and "filter" in (r["rec_name"] or "").lower()),
    ("P4", "Parts discovery", "lars", "I need a replacement part for my machine.", "asks for machine or part; recommends nothing", lambda r: no_rec(r) and r["state"].startswith("need")),
    ("P5", "Parts discovery", "lars", "Find a cooling fan for the NV-4500.", "a cooling fan with confirmed fit for NV-4500", lambda r: fits(r, "NV-4500") and "fan" in (r["rec_name"] or "").lower()),
    ("P6", "Parts discovery", "lars", "I need a hydraulic pomp for my machine.", "typo and no machine: asks; recommends nothing", lambda r: no_rec(r) and r["state"].startswith(("need", "choose"))),
    ("P7", "Parts discovery", "lars", "I need a part delivered to Lagos.", "no part invented; the place's recorded routes may be shown, labelled potential", lambda r: no_rec(r) and ("ROUTE_OPTIONS" in text(r) or not r.get("sections"))),
    ("P8", "Parts discovery", "lars", "Find the right part for my machine.", "asks; recommends nothing", lambda r: no_rec(r) and r["state"].startswith("need")),
    ("P9", "Parts discovery", "lars", "I need a hydrualic pomp for my KFT-200", "typo with a machine: the verified part or a question, never a wrong part", lambda r: r["recommended"] in (None, "NVM-1050-HY")),
    # 2. machine and fitment
    ("M1", "Machine & fitment", "lars", "Which parts fit my NV-3200?", "no part claimed without fitment; asks which part", lambda r: no_rec_without_fit(r, "NV-3200") and ("Which part" in text(r) or r["state"].startswith("need"))),
    ("M2", "Machine & fitment", "lars", "Which machine uses this part?", "no part in context: asks which part", lambda r: no_rec(r) and ("Which part" in text(r) or "part number" in text(r).lower())),
    ("M3", "Machine & fitment", "lars", "Which machines use NVM-1050-HY?", "recorded fitment: KFT-200 and KFT-450", lambda r: "KFT-200" in text(sec(r, "DISCOVERY")) and "KFT-450" in text(sec(r, "DISCOVERY"))),
    ("M4", "Machine & fitment", "lars", "Is this pump compatible with the KFT-200?", "only a part with confirmed fit for KFT-200", lambda r: no_rec_without_fit(r, "KFT-200") and ("NVM-1050-HY" in text(r) or no_rec(r))),
    ("M5", "Machine & fitment", "lars", "Find a part for my NV-4500.", "asks which part; recommends nothing", lambda r: no_rec(r)),
    ("M6", "Machine & fitment", "lars", "Find a hydraulic pump for my NV-9999", "unknown model: recommends nothing", lambda r: no_rec(r)),
    ("M7", "Machine & fitment", "lars", "Find a hydraulic pump for my XYZ-999", "invalid machine: recommends nothing", lambda r: no_rec(r)),
    ("M8", "Machine & fitment", "lars", "I need a pump for the big yellow loader", "ambiguous machine: asks; recommends nothing", lambda r: no_rec(r)),
    ("M9", "Machine & fitment", "lars", "Find a bucket for my KFT", "machine family only: asks which model", lambda r: no_rec(r)),
    # 3. budget, price and availability
    ("B1", "Budget & availability", "lars", "Find the cheapest cooling fan for the NV-4500.", "cheapest eligible fan for NV-4500 (deterministic)", lambda r: r["interpretation"].get("preference") == "cheapest" and fits(r, "NV-4500") and cheapest_eligible(r)),
    ("B2", "Budget & availability", "lars", "Find a bucket under €2200 for my NV-3200.", "budget 2200 read; the bucket recommended is within it", lambda r: r["interpretation"].get("budget_max") == 2200 and fits(r, "NV-3200") and r.get("within_budget") is True),
    ("B3", "Budget & availability", "lars", "I need the cheapest available option.", "no part or machine: asks", lambda r: no_rec(r)),
    ("B4", "Budget & availability", "lars", "I need an air filter for my NV-3200 urgently.", "urgency read as fastest; fastest needs a destination, so it asks where (or recommends a confirmed fit)", lambda r: r["interpretation"].get("preference") == "fastest" and (fits(r, "NV-3200") or (no_rec(r) and "delivered" in (r.get("question") or "")))),
    ("B5", "Budget & availability", "lars", "Do you have NVM-1050-HY in stock?", "the part's recorded stock, no machine asked for, no depot detail for a customer", lambda r: sec(r, "DISCOVERY").get("decision") == "PART_STOCK" and "units recorded" in text(r) and "not a machine model" not in text(r) and "WH-0" not in text(sec(r, "DISCOVERY"))),
    ("B6", "Budget & availability", "lars", "I need 5 brake pad sets for my NV-3200", "quantity 5 read; nothing without confirmed fit", lambda r: r["interpretation"].get("quantity") == 5 and no_rec_without_fit(r, "NV-3200")),
    ("B7", "Budget & availability", "lars", "Find a bucket under €100 for my NV-3200", "no bucket within budget: none recommended, reason stated", lambda r: no_rec(r) and r["state"] == "no_match" and "budget" in (r.get("question") or "").lower()),
    ("B8", "Budget & availability", "lars", "Find the cheapest air filter for my NV-3200", "cheapest eligible filter (deterministic)", lambda r: fits(r, "NV-3200") and cheapest_eligible(r)),
    # 4. delivery and logistics
    ("L1", "Logistics", "lars", "How fast can I get an air filter for my NV-3200 delivered to Aalborg?", "delivery to Aalborg from a recorded route and depot", lambda r: (r.get("delivery") or {}).get("city") == "Aalborg"),
    ("L2", "Logistics", "lars", "How long to ship to Lagos?", "Lagos: recorded air 5 days and sea 31 days, labelled potential", lambda r: sec(r, "LOGISTICS").get("decision") == "ROUTE_OPTIONS" and "air 5 days, sea 31 days" in text(r) and "potential" in text(r)),
    ("L3", "Logistics", "lars", "Can you deliver to the USA?", "the four recorded US destinations, potential", lambda r: all(c in text(r) for c in ("Houston", "Savannah", "Chicago", "Los Angeles"))),
    ("L4", "Logistics", "jane", "Compare sea and air for shipment SHP-NET-0001", "recorded air alternative 6 days against the 91-day sea route", lambda r: "RTE-NET-JPNL-AIR-EXP (AIR), 6 days" in text(r) and "RTE-NET-JPNL-SEA-ECO" in text(r)),
    ("L5", "Logistics", "lars", "What is the fastest delivery option for an air filter for my NV-3200 to Aalborg?", "fastest preference, Aalborg", lambda r: r["interpretation"].get("preference") == "fastest" and (r.get("delivery") or {}).get("city") == "Aalborg"),
    ("L6", "Logistics", "lars", "What is the cheapest delivery option for an air filter for my NV-3200 to Aalborg?", "cheapest preference, Aalborg", lambda r: r["interpretation"].get("preference") == "cheapest" and (r.get("delivery") or {}).get("city") == "Aalborg"),
    ("L7", "Logistics", "lars", "Where is my shipment?", "the customer's own shipment and its recorded status", lambda r: "SHP-0010" in text(sec(r, "LOGISTICS"))),
    ("L8", "Logistics", "jane", "What is the ETA of shipment SHP-NET-0001?", "recorded planned ETA 2026-11-19", lambda r: "2026-11-19" in text(sec(r, "LOGISTICS"))),
    ("L9", "Logistics", "jane", "Is shipment SHP-NET-0003 overdue?", "past the planned ETA; no new ETA invented", lambda r: "Past the planned ETA" in text(r) and "no new ETA is recorded" in text(r)),
    ("L10", "Logistics", "lars", "Which parts are in my shipment?", "the shipment's recorded order lines; no part search", lambda r: list(r.get("sections") or {}) == ["LOGISTICS"] and "order lines" in text(r) and "NVM-" in text(sec(r, "LOGISTICS"))),
    ("L11", "Logistics", "lars", "How long does shipping to Atlantis take?", "unknown destination: no route, no unrelated shipment", lambda r: "ROUTE_OPTIONS" not in text(r) and not r.get("sections")),
    ("L12", "Logistics", "lars", "Has order NCME-ORD-000001 shipped?", "no shipment recorded, said so", lambda r: sec(r, "LOGISTICS").get("decision") == "NO_SHIPMENT_RECORDED"),
    ("L13", "Logistics", "jane", "Where is shipment SHP-NET-0004?", "delivered", lambda r: sec(r, "LOGISTICS").get("decision") == "DELIVERED"),
    ("L14", "Logistics", "jane", "Where is shipment SHP-0001?", "route not determinable: no ETA or faster option invented", lambda r: sec(r, "LOGISTICS").get("decision") == "ROUTE_NOT_DETERMINABLE" and "Planned ETA" not in text(r)),
    ("L15", "Logistics", "jane", "Where is shipment SHP-NET-9999?", "unknown shipment: not recorded", lambda r: sec(r, "LOGISTICS").get("decision") == "NOT_FOUND"),
    # 5. orders and fulfilment
    ("O1", "Orders", "lars", "Show me my order.", "the customer's own records only", lambda r: r.get("commerce_http") == 200 and "LOGISTICS" in (r.get("sections") or {})),
    ("O2", "Orders", "lars", "What is the status of my order?", "the customer's own records only", lambda r: r.get("commerce_http") == 200 and "LOGISTICS" in (r.get("sections") or {})),
    ("O3", "Orders", "lars", "What parts are in order NCME-ORD-000001?", "the order and its recorded lines", lambda r: "NCME-ORD-000001" in text(r) and "NVM-1140-ST" in text(sec(r, "LOGISTICS"))),
    ("O4", "Orders", "lars", "Has order NCME-ORD-000001 been allocated?", "recorded status ALLOCATED", lambda r: "ALLOCATED" in text(sec(r, "LOGISTICS"))),
    ("O5", "Orders", "lars", "Where is order ORD-0013?", "the customer's shipped order: its shipment SHP-0010 and lines", lambda r: r.get("commerce_http") == 200 and "SHP-0010" in text(sec(r, "LOGISTICS"))),
    ("O6", "Orders", "lars", "Where is order ORD-99999999?", "unknown order: refused or not found, nothing shown", lambda r: r.get("commerce_http") in (403, 200) and "status ALLOCATED" not in text(r)),
    # 6. warranty
    ("W1", "Warranty", "lars", "Is this failed part covered by warranty?", "asks which claim or machine, offering only the customer's own", lambda r: r.get("commerce_status") == "REQUIRES_CLARIFICATION" and r.get("clarification_options", 0) >= 1),
    ("W2", "Warranty", "lars", "Is my warranty still active?", "asks which claim or machine", lambda r: r.get("commerce_status") == "REQUIRES_CLARIFICATION"),
    ("W3", "Warranty", "lars", "Is claim CLM-G001 covered?", "ELIGIBLE by the rules, with coverage dates", lambda r: sec(r, "WARRANTY").get("decision") == "ELIGIBLE" and "2026-04-12" in text(r)),
    ("W4", "Warranty", "jane", "Why is claim CLM-G002 not eligible?", "NOT_ELIGIBLE: installed by a service partner", lambda r: sec(r, "WARRANTY").get("decision") == "NOT_ELIGIBLE" and "SERVICE_PARTNER" in text(r)),
    ("W5", "Warranty", "jane", "Is claim CLM-G003 covered?", "NOT_ELIGIBLE: coverage ended", lambda r: sec(r, "WARRANTY").get("decision") == "NOT_ELIGIBLE" and "Coverage ended" in text(r)),
    ("W6", "Warranty", "jane", "What evidence is available for claim CLM-G006?", "INSUFFICIENT_DATA, missing records named", lambda r: sec(r, "WARRANTY").get("decision") == "INSUFFICIENT_DATA" and "Missing" in text(r)),
    ("W7", "Warranty", "jane", "Is the replacement on claim CLM-G005 covered?", "REQUIRES_REVIEW: replacement history", lambda r: sec(r, "WARRANTY").get("decision") == "REQUIRES_REVIEW"),
    ("W8", "Warranty", "jane", "Is claim CLM-NOPE covered?", "unknown claim: not recorded", lambda r: sec(r, "WARRANTY").get("decision") == "NOT_FOUND"),
    ("W9", "Warranty", "lars", "Is part NVM-9999-XX on machine MI-G001 covered by warranty?", "unknown part: nothing decided or invented", lambda r: sec(r, "WARRANTY").get("decision") not in ("ELIGIBLE", "NOT_ELIGIBLE", "REQUIRES_REVIEW") or r.get("commerce_http") != 200),
    # 7. combined
    ("C1", "Combined", "lars", "I need a replacement hydraulic pump urgently. Is the failed one covered by warranty and how quickly can I get a replacement?",
     "asks which machine for the part (no guess) and asks or answers the warranty part", lambda r: no_rec(r) and "WARRANTY" in r["commerce_domains"] and r.get("commerce_http") == 200),
    ("C2", "Combined", "lars", "Find a compatible pump for my machine, compare delivery options, and tell me whether my existing order has shipped.",
     "asks which machine for the part; answers the order question from the customer's own records", lambda r: no_rec(r) and "LOGISTICS" in r["commerce_domains"] and sec(r, "LOGISTICS").get("decision") not in (None, "NO_SHIPMENT_FOR_UNORDERED_PART")),
    ("C3", "Combined", "lars", "Which part do I need, where can it come from, how fast can it arrive, and is my failed part covered by warranty?",
     "asks for the machine or part; the warranty part is asked or answered", lambda r: no_rec(r) and "WARRANTY" in r["commerce_domains"]),
    ("C4", "Combined", "lars", "Find a hydraulic pump for my KFT-200 delivered to Aalborg, and has order NCME-ORD-000001 shipped?",
     "the part with its delivery to Aalborg, and the order's shipment status", lambda r: r["recommended"] == "NVM-1050-HY" and (r.get("delivery") or {}).get("city") == "Aalborg" and sec(r, "LOGISTICS").get("decision") == "NO_SHIPMENT_RECORDED"),
    ("C5", "Combined", "lars", "I need a hydraulic pump for my KFT-200, and is claim CLM-G001 covered?", "the part and the claim's verdict", lambda r: r["recommended"] == "NVM-1050-HY" and sec(r, "WARRANTY").get("decision") == "ELIGIBLE"),
    # 8. recommendation flow (the cart and checkout steps are browser-tested)
    ("R1", "Cart & checkout", "lars", "Find a hydraulic pump for my KFT-200.", "a recommendation with evidence and reasons that may be added to the cart", lambda r: r["state"] == "recommendation" and r["evidence"] > 0 and r["why"] > 0 and r["can_add_to_cart"] is True),
    ("R2", "Cart & checkout", "lars", "Find a hydraulic pump for my KFT-200.", "the same request gives the same recommendation (deterministic ranking)", lambda r: r["recommended"] == "NVM-1050-HY"),
    ("R3", "Cart & checkout", "lars", "Find a bucket under €100 for my NV-3200", "nothing can be added when nothing qualifies", lambda r: no_rec(r) and not any(c["eligible"] and c["price"] is not None and c["price"] <= 100 for c in r.get("candidates", []))),
    # 9. ambiguous and invalid
    ("A1", "Ambiguous & invalid", "lars", "I need a filter.", "asks; recommends nothing", lambda r: no_rec(r)),
    ("A2", "Ambiguous & invalid", "lars", "I need a pump.", "asks; recommends nothing", lambda r: no_rec(r)),
    ("A3", "Ambiguous & invalid", "lars", "My machine needs a part.", "asks; recommends nothing", lambda r: no_rec(r)),
    ("A4", "Ambiguous & invalid", "lars", "BTS machine.", "asks or declines; recommends nothing", lambda r: no_rec(r)),
    ("A5", "Ambiguous & invalid", "lars", "I need part NVM-9999-XX", "invalid part number: nothing invented", lambda r: no_rec(r)),
    ("A6", "Ambiguous & invalid", "lars", "What is the weather in Paris?", "unsupported: declined, nothing looked up", lambda r: r["state"] == "out_of_scope" and r["commerce_domains"] == []),
    # 10. security and isolation
    ("S1", "Security/isolation", "anna", "Where is order NCME-ORD-000001?", "another customer's order: 403", lambda r: r.get("commerce_http") == 403),
    ("S2", "Security/isolation", "anna", "Where is shipment SHP-0010?", "another customer's shipment: 403", lambda r: r.get("commerce_http") == 403),
    ("S3", "Security/isolation", "anna", "Is claim CLM-G001 covered?", "another customer's claim: 403", lambda r: r.get("commerce_http") == 403),
    ("S4", "Security/isolation", None, "Where is my shipment?", "signed out: no protected data (401)", lambda r: r["commerce_domains"] == ["LOGISTICS"] and r.get("commerce_http") == 401),
    ("S5", "Security/isolation", None, "Is claim CLM-G001 covered?", "signed out: no protected data (401)", lambda r: r.get("commerce_http") == 401),
    ("S6", "Security/isolation", "jane", "Where is order NCME-ORD-000001?", "order processor sees the order (role unchanged)", lambda r: r.get("commerce_http") == 200 and "NCME-ORD-000001" in text(r)),
    ("S7", "Security/isolation", "lars", "Where is order NCME-ORD-000001?", "the owner sees their own order", lambda r: r.get("commerce_http") == 200 and "NCME-ORD-000001" in text(r)),
    ("S8", "Security/isolation", None, "Find a hydraulic pump for my KFT-200.", "signed out: the same part recommendation (public catalogue)", lambda r: r["recommended"] == "NVM-1050-HY"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    clients: dict[str | None, Client] = {}
    rows = []
    for sid, area, user, message, expected, check in SCENARIOS:
        if args.only and sid not in args.only:
            continue
        c = clients.setdefault(user, Client(args.base, user))
        try:
            r = c.run(message)
            ok = r.get("shopping_http") == 200 and bool(check(r))
        except Exception as exc:  # a broken scenario is a FAIL with its error, never a pass
            r, ok = {"error": repr(exc)}, False
        rows.append({"id": sid, "area": area, "user": user or "signed out", "message": message, "expected": expected, "result": "PASS" if ok else "FAIL", "observed": r})
        print(f"{'PASS' if ok else 'FAIL'}  {sid:4} {message[:90]}", flush=True)
    if not args.only or "A7" in args.only:
        empty = clients.setdefault("lars", Client(args.base, "lars")).http.post("/api/v1/agent/recommend", json={"request": ""}).status_code
        rows.append({"id": "A7", "area": "Ambiguous & invalid", "user": "lars", "message": "(empty)", "expected": "refused before anything runs (422)", "result": "PASS" if empty == 422 else "FAIL", "observed": {"shopping_http": empty}})
        print(f"{'PASS' if empty == 422 else 'FAIL'}  A7   (empty input) -> {empty}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, default=str)
    fails = [r for r in rows if r["result"] != "PASS"]
    print(f"\n{len(rows) - len(fails)} passed, {len(fails)} failed of {len(rows)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
