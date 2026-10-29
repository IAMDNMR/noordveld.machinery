"""Response-time probe for the running API: the important reads a user waits on, measured the same way every time.

Read-only by default: catalogue, a large catalogue page, a part's relationship graph, order list and detail, and checkout review (a review
creates nothing). Spark calls the NVIDIA model and spends quota, so it runs only with --spark. Placing an order is never probed here; its
in-process budget is tests/test_performance.py.

    python scripts/perf_probe.py                      # 10 runs per scenario against http://localhost:8000
    python scripts/perf_probe.py --save before.json   # keep the numbers
    python scripts/perf_probe.py --compare before.json  # the same scenarios now, with the change in p50 and p95
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

BUYER, PROCESSOR = "USR-EU-001", "USR-OP-001"


def session(base: str, user: str) -> httpx.Client:
    c = httpx.Client(base_url=f"{base}/api/v1", timeout=120)
    r = c.post("/auth/login", json={"user_id": user})
    r.raise_for_status()
    return c


def scenarios(buyer: httpx.Client, processor: httpx.Client, spark: bool) -> dict:
    orders = processor.get("/orders").json()
    some_order = next((o["order_id"] for o in orders if o.get("channel") == "DIRECT_ORDER"), orders[0]["order_id"])
    part = buyer.get("/parts", params={"limit": 1}).json()["items"][0]
    country = buyer.get("/checkout/countries").json()[0]
    country = country.get("country_code", country) if isinstance(country, dict) else country
    site = buyer.get("/checkout/destinations", params={"country": country}).json()[0]["ship_to_id"]
    out = {
        "catalogue: first page": lambda: buyer.get("/parts", params={"limit": 24}),
        "catalogue: search": lambda: buyer.get("/parts", params={"q": "filter", "limit": 24}),
        "catalogue: largest page (60)": lambda: buyer.get("/parts", params={"limit": 60}),
        "catalogue: machine filter": lambda: buyer.get("/parts", params={"machine": "NV-3200", "limit": 60}),
        "part detail": lambda: buyer.get(f"/parts/{part['part_number']}"),
        "graph: part relationships": lambda: buyer.get(f"/intelligence/parts/{part['part_number']}/graph"),
        "graph: whole-graph figures": lambda: buyer.get("/intelligence/kpis"),
        f"orders: processor list ({len(orders)})": lambda: processor.get("/orders"),
        "orders: detail": lambda: processor.get(f"/orders/{some_order}"),
        "checkout: review": lambda: buyer.post("/checkout/review", json={"items": [{"part_id": part["part_id"], "quantity": 1}], "ship_to_id": site}),
    }
    if spark:
        out["spark: shopping question (NVIDIA)"] = lambda: buyer.post("/spark/conversation", json={"message": "I need an air filter for my NV-3200"})
    return out


def measure(fn, runs: int) -> dict:
    fn()  # warm-up: connection set-up and first-query caches are not what a user waits on every time
    times, status = [], set()
    for _ in range(runs):
        start = time.perf_counter()
        r = fn()
        times.append((time.perf_counter() - start) * 1000)
        status.add(r.status_code)
    times.sort()
    p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
    return {"runs": runs, "min": round(times[0], 1), "p50": round(statistics.median(times), 1), "p95": round(p95, 1), "max": round(times[-1], 1),
            "status": sorted(status)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--spark", action="store_true", help="also measure a Spark answer (calls NVIDIA; runs at most 3 times)")
    ap.add_argument("--save", type=Path)
    ap.add_argument("--compare", type=Path)
    a = ap.parse_args()
    buyer, processor = session(a.base, BUYER), session(a.base, PROCESSOR)
    before = json.loads(a.compare.read_text()) if a.compare else {}
    results = {}
    print(f"{'scenario':42} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}  status" + ("  d-p50   d-p95" if before else ""))
    for name, fn in scenarios(buyer, processor, a.spark).items():
        r = results[name] = measure(fn, min(a.runs, 3) if name.startswith("spark") else a.runs)
        line = f"{name:42} {r['p50']:8.1f} {r['p95']:8.1f} {r['max']:8.1f}  {r['status']}"
        if name in before:
            line += f" {r['p50'] - before[name]['p50']:+7.1f} {r['p95'] - before[name]['p95']:+7.1f}"
        print(line)
    bad = [n for n, r in results.items() if any(s >= 400 for s in r["status"])]
    if a.save:
        a.save.write_text(json.dumps(results, indent=1))
    if bad:
        raise SystemExit(f"failed responses in: {', '.join(bad)}")


if __name__ == "__main__":
    main()
