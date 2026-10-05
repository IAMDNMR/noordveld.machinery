"""Agentic Shopping supply and destination, pure functions over graph rows (no I/O, no model).

Path every candidate must pass:  Part -> AVAILABLE_AT depot (known stock >= quantity) -> TransportRoute -> TransportOption -> ShipTo (the destination).

Rules (the same stock rules the direct-order flow enforces again at allocation):
  * IN_STOCK and LOW_STOCK with a recorded quantity are available now. ON_ORDER and OUT_OF_STOCK are known not to be available now.
  * UNKNOWN stays UNKNOWN: it is never read as zero and never counts as available. A status without a quantity is UNKNOWN.
  * With a destination, a depot supplies a part only if a recorded route from that depot to the destination exists.
  * The depot is chosen from the ones that can supply, by the fastest recorded route (days, then distance, then ids); never by "most stock".
  * Nothing here is guessed: no route means no delivery claim.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.core.geography import COUNTRY_NAMES
from app.services.fulfilment import KNOWN_AVAILABLE, option_view, stock_state

STATE_LABEL = {"IN_STOCK": "In stock", "LOW_STOCK": "Low stock", "ON_ORDER": "On order", "OUT_OF_STOCK": "Out of stock", "UNKNOWN": "Availability unknown"}
STATE_RANK = {"IN_STOCK": 0, "LOW_STOCK": 1, "ON_ORDER": 2, "UNKNOWN": 3, "OUT_OF_STOCK": 4}


def fold(text: str | None) -> str:
    """Case, accent and German-transliteration insensitive form of a place name ('Köln' = 'Koeln' = 'koln' is not claimed, only the first two)."""
    s = (text or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# ── destination ──────────────────────────────────────────────────────────────────────────────────
@dataclass
class Destination:
    """How a place the user named resolved against the recorded delivery destinations (ship-tos that a route ends at)."""

    kind: str  # city | country | ambiguous | unknown
    place: str
    city: str | None = None
    country_code: str | None = None
    shipto_ids: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)  # cities to offer when the place is not specific enough or not found


def resolve_destination(place: str, destinations: list[dict[str, Any]]) -> Destination:
    """City first ('Hamburg', 'Hamburg, Germany'); a country alone is ambiguous (which destination?); anything else is unknown. Never guessed."""
    raw = " ".join((place or "").split())
    head, _, tail = raw.partition(",")
    key, tail_key = fold(head), fold(tail)
    wanted_cc = next((cc for name, cc in COUNTRY_NAMES.items() if tail_key and tail_key in (fold(name), cc.lower())), None)
    hits = [d for d in destinations if fold(d["city"]) == key and (wanted_cc is None or d["country_code"] == wanted_cc)]
    if hits:
        countries = sorted({d["country_code"] for d in hits})
        if len(countries) > 1:
            return Destination("ambiguous", raw, choices=[f"{hits[0]['city']}, {c}" for c in countries])
        return Destination("city", raw, city=hits[0]["city"], country_code=countries[0], shipto_ids=sorted(d["shipto_id"] for d in hits))
    cc = next((c for name, c in COUNTRY_NAMES.items() if fold(name) == key or c.lower() == key), None)
    if cc and any(d["country_code"] == cc for d in destinations):
        return Destination("country", raw, country_code=cc, choices=sorted({d["city"] for d in destinations if d["country_code"] == cc}))
    return Destination("unknown", raw, choices=sorted({d["city"] for d in destinations}))


# ── supply for one part ──────────────────────────────────────────────────────────────────────────
def _fastest_first(o: dict[str, Any]) -> tuple:
    return (o["estimated_days"] if o.get("estimated_days") is not None else 10**6, o.get("distance_km") or 0.0, o["route_id"])


@dataclass
class Supply:
    availability: str = "UNKNOWN"  # best state across depots, spec vocabulary
    units: int | None = None  # known units across depots; None when nothing is known (never zero)
    depots: list[dict[str, Any]] = field(default_factory=list)  # every depot row: id, name, city, state, available, can_supply
    stock_ok: bool = False  # some depot has known stock >= the quantity
    route_ok: bool | None = None  # None when no destination was asked for
    depot: dict[str, Any] | None = None  # chosen depot (only when a destination makes the choice meaningful)
    route: dict[str, Any] | None = None  # chosen route option
    shipto_id: str | None = None

    @property
    def available_now(self) -> bool:
        return self.stock_ok and self.route_ok is not False


def part_supply(part_id: str, quantity: int, stock_rows: list[dict[str, Any]], route_rows: list[dict[str, Any]] | None) -> Supply:
    """`route_rows` None = no destination asked for; [] = a destination with no route from any of these depots."""
    mine = [r for r in stock_rows if r["part_id"] == part_id]
    depots, states = [], []
    for r in mine:
        st = stock_state(r)
        states.append(st["state"])
        depots.append({"depot_id": r["warehouse_id"], "name": r.get("name"), "city": r.get("city"), "country_code": r.get("country_code"), "state": st["state"],
                       "available": st["available"], "data_status": r.get("data_status"),
                       "can_supply": st["state"] in KNOWN_AVAILABLE and bool(st["known"]) and st["available"] >= quantity})
    out = Supply(availability=min(states, key=lambda s: STATE_RANK[s]) if states else "UNKNOWN", depots=depots)
    known = [d["available"] for d in depots if d["available"] is not None]
    out.units = sum(known) if known else None
    able = [d for d in depots if d["can_supply"]]
    out.stock_ok = bool(able)
    if route_rows is None:
        return out
    by_depot: dict[str, list[dict[str, Any]]] = {}
    for r in route_rows:
        by_depot.setdefault(r["depot_id"], []).append(option_view(r))
    best: tuple | None = None
    for d in able:
        opts = sorted(by_depot.get(d["depot_id"], []), key=_fastest_first)
        if opts:
            key = (*_fastest_first(opts[0]), d["depot_id"])
            if best is None or key < best[0]:
                best = (key, d, opts[0])
    out.route_ok = best is not None
    if best:
        out.depot, out.route = best[1], best[2]
        out.shipto_id = best[2].get("destination_shipto_id")
    return out
