"""Response-time budgets for the order paths, measured in-process on an isolated in-memory repository holding a large order book.

The budgets are the application's own work (FastAPI, validation, the order and checkout services), not the graph's network round trip,
so a regression such as an order list that grows quadratically with the number of orders fails here on every run. The time a user waits
against the hosted graph is measured with scripts/perf_probe.py."""

from __future__ import annotations

import statistics
import time

from tests.test_direct_order import client, place, repo, review  # noqa: F401 (repo is the fixture)

ORDERS = 300
BUDGET_MS = {"list": 400, "detail": 60, "review": 60, "place": 120}


def timed(fn, runs: int = 7) -> float:
    fn()  # warm-up
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        r = fn()
        samples.append((time.perf_counter() - start) * 1000)
        assert r.status_code < 400, r.text
    return statistics.median(samples)


def test_order_paths_stay_within_budget_with_a_large_order_book(repo):  # noqa: F811
    for row in repo.stock.values():
        row.update(available=100_000, on_hand=100_000)
    anna, jane = client("U-ANNA"), client("U-JANE")
    keys = iter(f"perf-key-{n:06d}" for n in range(10_000))
    for _ in range(ORDERS):
        assert place(anna, idempotency_key=next(keys)).status_code == 201
    oid = jane.get("/api/v1/orders").json()[0]["order_id"]

    seen = {
        "list": timed(lambda: jane.get("/api/v1/orders")),
        "detail": timed(lambda: jane.get(f"/api/v1/orders/{oid}")),
        "review": timed(lambda: review(anna)),
        "place": timed(lambda: place(anna, idempotency_key=next(keys))),
    }
    assert len(jane.get("/api/v1/orders").json()) >= ORDERS
    over = {k: round(v, 1) for k, v in seen.items() if v > BUDGET_MS[k]}
    print("order path medians (ms):", {k: round(v, 1) for k, v in seen.items()})
    assert not over, f"over budget (ms): {over}"
