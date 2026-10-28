"""Spark model benchmark: accuracy and latency of the two language steps Spark runs on every message.

1. routing  - `interpret()` with SPARK_RULES: which tool a message goes to, and which offered part 'order it' means.
2. reading  - `parse_order_message()` with ORDER_RULES: what a reply inside an order changes (date, quantity, preference, part...).

Every case has a checked expectation, so a faster model is only acceptable if it is as right as the current one.
Live calls: run by hand, never in the test suite. Usage (from backend/):
    python scripts/spark_model_benchmark.py nvidia-planner nvidia-fast groq gemini
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402  (also loads backend/.env)
from app.services.order_journey import ORDER_RULES  # noqa: E402
from app.services.spark import interpret, resolve_order_part  # noqa: E402

TODAY = dt.date.today()
DAY = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()  # noqa: E731
BUCKETS = [{"kind": "PART", "label": "NVM-1020-AT", "name": "Bucket, high-tip, 1.0m3", "part_id": "PRT-089", "recommended": True},
           {"kind": "PART", "label": "NVM-1010-AT", "name": "Bucket, standard, 0.8m3", "part_id": "PRT-088", "recommended": False}]
SHOP = {"history": [{"message": "Find a bucket under €2,200 for my NV-3200", "request": {"shopping": "Find a bucket for NV-3200 under 2200 EUR"}}],
        "offered": BUCKETS, "pending": None}
ORDERS = [{"order_id": "NM-ORD042", "date": "2026-10-27", "status": "NEW"}]


def has(text, *words):
    return bool(text) and all(w.casefold() in text.casefold() for w in words)


# (name, message, memory, extra kwargs, check(plan) -> bool)
ROUTING = [
    ("find a bucket", "Find a bucket under €2,200 for my NV-3200", {}, {},
     lambda p: has(p.shopping, "bucket", "NV-3200", "2") and not p.order and not p.clarification),
    ("order it after a recommendation", "I want it in one day, so order it", SHOP, {},
     lambda p: p.order is not None and (resolve_order_part(p.order, BUCKETS) or {}).get("part_id") == "PRT-089"),
    ("order the other one", "Actually, order the standard one instead", SHOP, {},
     lambda p: p.order is not None and (resolve_order_part(p.order, BUCKETS) or {}).get("part_id") == "PRT-088"),
    ("supplier question", "Who supplies NVM-1010-AT?", {}, {},
     lambda p: has(p.intelligence, "NVM-1010-AT") and not p.shopping and not p.order),
    ("fitment of a machine", "Which parts fit the NV-3200?", {}, {},
     lambda p: has(p.intelligence, "NV-3200") and not p.order),
    ("last order status", "What is the status of my last order?", {}, {"my_orders": ORDERS},
     lambda p: has(p.account, "NM-ORD042") and not p.shopping),
    ("order it mid-order", "ok, order it", {}, {"order_part": "NVM-1020-AT"},
     lambda p: p.order is not None and (resolve_order_part(p.order, [{"kind": "PART", "label": "NVM-1020-AT", "part_id": "PRT-089"}]) or {}).get("part_id") == "PRT-089"),
    ("out of scope", "What's the weather in Paris tomorrow?", {}, {},
     lambda p: not any((p.intelligence, p.shopping, p.account, p.order)) and bool(p.clarification)),
    ("greeting", "Hi there!", {}, {},
     lambda p: not any((p.intelligence, p.shopping, p.account, p.order))),
]

CURRENT = {"part": "NVM-1020-AT", "quantity": None, "machine": "NV-3200", "preference": None, "budget_eur": None, "needed_by": None}
READING = [
    ("one day question", "Can I get it in one day?", CURRENT,
     lambda r: r.relevant and str(r.needed_by) == DAY(1) and r.quantity is None and r.part is None),
    ("one or two days", "What if I want this in one or two days?", {**CURRENT, "needed_by": DAY(1)},
     lambda r: r.relevant and str(r.needed_by) == DAY(2) and r.quantity is None),
    ("tomorrow", "I need it tomorrow", CURRENT,
     lambda r: r.relevant and str(r.needed_by) == DAY(1)),
    ("make it two", "Make it two", {**CURRENT, "quantity": 1},
     lambda r: r.relevant and r.quantity == 2 and r.needed_by is None),
    ("quantity and place", "2 please, deliver to our Utrecht site", CURRENT,
     lambda r: r.relevant and r.quantity == 2 and has(r.destination, "Utrecht")),
    ("prioritise price", "Keep the same part, but prioritise price", CURRENT,
     lambda r: r.relevant and r.preference == "cheapest" and r.part is None),
    ("pay for speed", "I'll pay a little more for faster delivery", CURRENT,
     lambda r: r.relevant and r.preference == "fastest"),
    ("compare", "Can you compare the delivery options?", {**CURRENT, "quantity": 2},
     lambda r: r.relevant and r.compare_options is True and r.quantity is None),
    ("switch part", "Switch to NVM-1010-AT", CURRENT,
     lambda r: r.relevant and has(r.part, "1010")),
    ("unrelated", "Where is my last order?", CURRENT,
     lambda r: not r.relevant),
    ("question naming another part", "Who supplies NVM-1010-AT?", {**CURRENT, "quantity": 2},
     lambda r: not r.relevant and r.part is None),
    ("two days not two units", "Keep the same part, but change the delivery to two days", {**CURRENT, "quantity": 3},
     lambda r: r.relevant and str(r.needed_by) == DAY(2) and r.quantity is None and r.part is None),
]


def client(name: str):
    s = get_settings()
    if name.startswith("nvidia"):
        from app.llm.nvidia import NvidiaClient

        return NvidiaClient(s, model=s.nvidia_fast_model if name == "nvidia-fast" else s.nvidia_planner_model)
    from app.llm import create_llm

    return create_llm(replace(s, llm_provider=name))


def run(name: str) -> dict:
    llm = client(name)
    rows = []
    for case, message, memory, kw, check in ROUTING:
        rows.append(timed("routing", case, lambda: interpret(llm, message, memory, None, kw.get("my_orders"), kw.get("order_part")), check))
    for case, message, current, check in READING:
        prompt = json.dumps({"today": TODAY.isoformat(), "current_order": current, "reply": message}, ensure_ascii=False)
        rows.append(timed("reading", case, lambda: llm.parse_order_message(ORDER_RULES, prompt), check))
    return {"model": name, "rows": rows}


PACE = 0.0  # seconds between calls, for providers with a tokens-per-minute limit (--pace=N)


def timed(step, case, call, check):
    time.sleep(PACE)
    t = time.perf_counter()
    try:
        out = call()
        ok, note = bool(check(out)), json.dumps(out.model_dump(exclude_none=True, mode="json"), ensure_ascii=False)[:160]
    except Exception as exc:  # a failed call counts as wrong, with its reason
        ok, note = False, f"{type(exc).__name__}: {str(exc)[:120]}"
    return {"step": step, "case": case, "ok": ok, "s": time.perf_counter() - t, "note": note}


def report(result: dict) -> None:
    rows = result["rows"]
    secs = [r["s"] for r in rows]
    print(f"\n== {result['model']}: {sum(r['ok'] for r in rows)}/{len(rows)} correct · median {statistics.median(secs):.1f}s · "
          f"p90 {sorted(secs)[int(len(secs) * 0.9) - 1]:.1f}s · total {sum(secs):.0f}s")
    for r in rows:
        if not r["ok"]:
            print(f"   WRONG {r['step']}/{r['case']} ({r['s']:.1f}s): {r['note']}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--pace=")]
    PACE = next((float(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--pace=")), 0.0)
    for model in args or ["nvidia-planner", "nvidia-fast"]:
        report(run(model))
