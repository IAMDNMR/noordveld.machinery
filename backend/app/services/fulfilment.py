"""Availability, depot selection and transport options for a direct order: pure functions over graph rows (no I/O).

Rules, each enforced again by the allocation transaction:
  * Stock is known only when the depot row says IN_STOCK or LOW_STOCK AND carries a quantity. UNKNOWN stays UNKNOWN: it is never read as zero
    and never allocated. ON_ORDER and OUT_OF_STOCK are known not to be available now.
  * A depot can supply an order only if every line has known stock >= the quantity AND a recorded route to the chosen destination exists.
  * The depot is chosen from those, never by "most stock": shortest estimated transit of its standard road route, then distance, then id.
  * A transport option exists only where the graph has a route from that depot to that destination with a freight-rate record.
  * Freight amounts are synthetic demo estimates: they are labelled as such and are never a price (transport and total cost are 'Not available').
"""
from __future__ import annotations

from typing import Any

STATES = ("IN_STOCK", "LOW_STOCK", "ON_ORDER", "OUT_OF_STOCK", "UNKNOWN")
KNOWN_AVAILABLE = ("IN_STOCK", "LOW_STOCK")
LOW_STOCK_AT = 5  # same threshold the depot inventory was seeded with

COST_NOTE = ("Part cost and transportation cost are not available: no real pricing source is connected. The freight figure shown with each transport option "
             "is a synthetic demo estimate for context, not a price.")


def stock_state(row: dict[str, Any] | None) -> dict[str, Any]:
    """{state, available, known}: UNKNOWN when there is no row, an unrecognised status, or a stock status that carries no quantity."""
    if not row:
        return {"state": "UNKNOWN", "available": None, "known": False}
    state = row.get("stock_status")
    qty = row.get("available")
    if state not in STATES:
        return {"state": "UNKNOWN", "available": None, "known": False}
    if state in KNOWN_AVAILABLE:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            return {"state": "UNKNOWN", "available": None, "known": False}  # a status without a quantity is not a quantity
        return {"state": state, "available": qty, "known": True}
    if state == "UNKNOWN":
        return {"state": "UNKNOWN", "available": None, "known": False}
    return {"state": state, "available": 0, "known": True}  # ON_ORDER / OUT_OF_STOCK: known to have nothing available now


def can_supply(state: dict[str, Any], quantity: int) -> bool:
    return bool(state["known"]) and state["state"] in KNOWN_AVAILABLE and state["available"] >= quantity


def status_after(available: int) -> str:
    return "OUT_OF_STOCK" if available <= 0 else "LOW_STOCK" if available <= LOW_STOCK_AT else "IN_STOCK"


def _reason(line_label: str, state: dict[str, Any], quantity: int) -> str:
    if state["state"] == "UNKNOWN":
        return f"{line_label}: stock is UNKNOWN at this depot (not treated as zero, not allocated)."
    if state["state"] in ("ON_ORDER", "OUT_OF_STOCK"):
        return f"{line_label}: {state['state'].replace('_', ' ').lower()} at this depot."
    return f"{line_label}: only {state['available']} available, {quantity} requested."


def option_view(r: dict[str, Any]) -> dict[str, Any]:
    freight = None
    if r.get("freight_total") is not None:
        freight = {"amount": r["freight_total"], "currency": r.get("freight_currency") or "EUR", "data_status": r.get("rate_data_status") or "SYNTHETIC_DEMO",
                   "label": "Synthetic demo freight estimate, not a price"}
    return {"route_id": r["route_id"], "option_id": r.get("option_id"), "option_code": r.get("option_code"), "option_name": r.get("option_name"), "mode": r.get("mode"),
            "service_level": r.get("service_level"), "origin_depot_id": r["depot_id"], "destination_shipto_id": r.get("shipto_id"),
            "distance_km": r.get("distance_km"), "estimated_days": r.get("days"), "estimate_basis": r.get("estimate_basis") or "ESTIMATED", "legs": r.get("legs"),
            "data_status": r.get("data_status") or "SYNTHETIC_DEMO", "freight": freight}


def depot_plan(lines: list[dict[str, Any]], stock: list[dict[str, Any]], routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per depot that holds any of the parts: per-line availability, whether the depot can supply everything, its transport options,
    and why not when it cannot. `lines`: part_id, part_number, quantity. Sorted: selectable first, best first."""
    by_depot: dict[str, dict[str, Any]] = {}
    for row in stock:
        d = by_depot.setdefault(row["warehouse_id"], {"depot_id": row["warehouse_id"], "name": row.get("name"), "city": row.get("city"), "country_code": row.get("country_code"), "rows": {}})
        d["rows"][row["part_id"]] = row
    options: dict[str, list[dict[str, Any]]] = {}
    for r in routes:
        options.setdefault(r["depot_id"], []).append(option_view(r))
    plan = []
    for depot_id, d in by_depot.items():
        reasons, per_line = [], []
        for ln in lines:
            st = stock_state(d["rows"].get(ln["part_id"]))
            ok = can_supply(st, ln["quantity"])
            per_line.append({"part_id": ln["part_id"], "part_number": ln["part_number"], "quantity": ln["quantity"], "state": st["state"], "available": st["available"], "can_supply": ok})
            if not ok:
                reasons.append(_reason(ln["part_number"], st, ln["quantity"]))
        opts = sorted(options.get(depot_id, []), key=_option_sort)
        if not opts:
            reasons.append("No recorded transport route from this depot to the chosen destination.")
        plan.append({"depot_id": depot_id, "name": d["name"], "city": d["city"], "country_code": d["country_code"], "lines": per_line,
                     "selectable": not reasons, "reasons": reasons, "options": opts, "recommended_route_id": _recommended(opts)})
    plan.sort(key=_depot_sort)
    first = next((p for p in plan if p["selectable"]), None)
    for p in plan:
        p["recommended"] = p is first
    return plan


def _recommended(opts: list[dict[str, Any]]) -> str | None:
    standard = [o for o in opts if o.get("mode") == "ROAD" and o.get("service_level") == "STANDARD"]
    pick = (standard or opts or [None])[0]
    return pick["route_id"] if pick else None


def _option_sort(o: dict[str, Any]) -> tuple:
    return (o.get("estimated_days") if o.get("estimated_days") is not None else 99, o.get("distance_km") or 0.0, o["route_id"])


def _depot_sort(p: dict[str, Any]) -> tuple:
    pick = next((o for o in p["options"] if o["route_id"] == p["recommended_route_id"]), None)
    return (not p["selectable"], pick["estimated_days"] if pick and pick["estimated_days"] is not None else 99, pick["distance_km"] if pick and pick["distance_km"] is not None else 1e9, p["depot_id"])


def cost_block() -> dict[str, Any]:
    """Cost is never invented. The three figures stay null until a real pricing source exists."""
    return {"part_cost": None, "transport_cost": None, "total": None, "currency": "EUR", "status": "NOT_AVAILABLE", "note": COST_NOTE}
