"""Where shipment context data comes from. Two readers return the SAME canonical-named dictionaries:

  FileReader   the canonical dataset files (no database: used by tests and for offline work)
  GraphReader  the Neo4j graph (read-only)

Because both speak the canonical vocabulary, the context builder is identical on either, and a test can check that the files and the graph agree.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME, KINDS
from app.graph.client import GraphClient
from app.graph.queries import logistics as q

LOCATION_TYPE_BY_LABEL = {"Warehouse": "WAREHOUSE", "ShipTo": None, "Plant": "PLANT", "Dealer": "DEALER", "Supplier": "SUPPLIER", "Location": None, "TransportTerminal": "TERMINAL"}


class LogisticsReader(Protocol):
    def shipment(self, shipment_id: str) -> dict[str, Any] | None: ...
    def events(self, shipment_id: str) -> list[dict[str, Any]]: ...
    def route(self, route_id: str) -> dict[str, Any] | None: ...
    def legs(self, route_id: str) -> list[dict[str, Any]]: ...
    def routes_between(self, origin: str, destination: str) -> list[dict[str, Any]]: ...
    def location(self, location_id: str) -> dict[str, Any] | None: ...
    def order(self, order_id: str) -> dict[str, Any] | None: ...
    def order_part(self, order_line_id: str) -> dict[str, Any] | None: ...


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "ingestion_timestamp"}


# ── canonical files ──────────────────────────────────────────────────────────────────────────────
class FileReader:
    def __init__(self, root: Path = CANON_DIR) -> None:
        self.root = root
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _rows(self, *names: str) -> list[dict[str, Any]]:
        key = "+".join(names)
        if key not in self._cache:
            out: list[dict[str, Any]] = []
            for n in names:
                spec = BY_NAME[n]
                out.extend(_clean(spec.model.model_validate(r).model_dump()) for r in load_rows(spec, self.root)[0])
            self._cache[key] = out
        return self._cache[key]

    def _index(self, name: str, field: str, *names: str) -> dict[str, Any]:
        key = f"idx:{name}:{field}"
        if key not in self._cache:
            self._cache[key] = {r[field]: r for r in self._rows(*names)}  # type: ignore[assignment]
        return self._cache[key]  # type: ignore[return-value]

    def shipment(self, shipment_id):
        return self._index("shipment", "shipment_id", "shipments", "network_shipments").get(shipment_id)

    def events(self, shipment_id):
        key = "events"
        if key not in self._cache:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in self._rows("tracking_events", "network_tracking_events"):
                grouped[r["shipment_id"]].append(r)
            self._cache[key] = grouped  # type: ignore[assignment]
        return sorted(self._cache[key].get(shipment_id, []), key=lambda e: (e["sequence"] if e["sequence"] is not None else 0, e["timestamp"]))  # type: ignore[union-attr]

    def route(self, route_id):
        return self._index("route", "route_id", "routes", "network_routes").get(route_id)

    def legs(self, route_id):
        key = "legs"
        if key not in self._cache:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in self._rows("route_legs", "network_route_legs"):
                grouped[r["route_id"]].append(r)
            self._cache[key] = grouped  # type: ignore[assignment]
        return sorted(self._cache[key].get(route_id, []), key=lambda leg: leg["sequence"])  # type: ignore[union-attr]

    def routes_between(self, origin, destination):
        key = "pairs"
        if key not in self._cache:
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for r in self._rows("routes", "network_routes"):
                grouped[(r["origin_location_id"], r["destination_location_id"])].append(r)
            self._cache[key] = grouped  # type: ignore[assignment]
        return sorted(self._cache[key].get((origin, destination), []), key=lambda r: r["route_id"])  # type: ignore[union-attr]

    def location(self, location_id):
        return self._index("location", "location_id", "locations", "network_locations").get(location_id)

    def order(self, order_id):
        return self._index("order", "order_id", "orders", "network_orders").get(order_id)

    def order_part(self, order_line_id):
        line = self._index("line", "order_line_id", "order_lines", "network_order_lines").get(order_line_id)
        if not line:
            return None
        part = self._index("part", "part_id", "parts").get(line["part_id"])
        return {"part_id": line["part_id"], "part_number": part["part_number"] if part else None, "name": part["name"] if part else None, "quantity": line["quantity"]}


# ── the graph ────────────────────────────────────────────────────────────────────────────────────
class GraphReader:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph

    def _one(self, query: str, **params: Any) -> dict[str, Any] | None:
        rows = self._g.read(query, **params)
        return rows[0] if rows else None

    @staticmethod
    def _prov(p: dict[str, Any]) -> dict[str, Any]:
        return {"data_status": p.get("data_status"), "source_type": p.get("source_type") or ("SYNTHETIC_DEMO" if p.get("data_status") == "SYNTHETIC_DEMO" else None),
                "source_record_id": p.get("source_record_id")}

    def shipment(self, shipment_id):
        r = self._one(q.SHIPMENT, id=shipment_id)
        if not r:
            return None
        p = r["p"]
        route_id = p.get("route_id") or r["route_rel"]
        flags = p.get("remediation_flags") or []
        return {"shipment_id": p["shipment_id"], "order_id": r["order_id"], "order_line_id": r["order_line_id"], "carrier": r["carrier"], "carrier_id": None, "route_id": route_id,
                "origin_location_id": r["origin"], "destination_location_id": r["destination"], "transport_mode": p.get("transport_mode"), "status": p.get("shipment_status"),
                "departure_date": p.get("departure_date"), "planned_eta": p.get("planned_eta"), "actual_eta": p.get("actual_eta"), "tracking_ref": p.get("tracking_ref"),
                "remediation_flags": list(flags), "route_resolution_status": p.get("route_resolution_status") or ("LINKED" if route_id else "ROUTE_NOT_DETERMINABLE"), **self._prov(p)}

    def events(self, shipment_id):
        out = []
        for r in self._g.read(q.EVENTS, id=shipment_id):
            p = r["p"]
            out.append({"tracking_event_id": p["tracking_event_id"], "shipment_id": shipment_id, "timestamp": p.get("event_date"), "location_id": r["location_id"],
                        "location_text": p.get("event_location"), "status": p.get("event_status"), "event_type": p.get("event_type") or p.get("event_status"),
                        "description": p.get("description"), "sequence": p.get("event_seq"), **self._prov(p)})
        return out

    @staticmethod
    def _route_row(r: dict[str, Any]) -> dict[str, Any]:
        p = r["p"]
        return {"route_id": p["route_id"], "origin_location_id": p.get("origin_location_id") or p.get("origin_depot_id"),
                "destination_location_id": p.get("destination_location_id") or p.get("destination_shipto_id"), "transport_mode": p.get("transport_mode"),
                "planned_transit_days": p.get("total_estimated_days"), "estimated_cost": p.get("estimated_cost") if p.get("estimated_cost") is not None else r["cost"],
                "currency": p.get("currency") or r["currency"], "service_level": p.get("service_level"), "status": p.get("route_status"),
                "data_status": p.get("data_status"), "source_type": p.get("source_type") or ("SYNTHETIC_DEMO" if p.get("data_status") == "SYNTHETIC_DEMO" else None),
                "source_record_id": p.get("source_record_id")}

    def route(self, route_id):
        r = self._one(q.ROUTE, id=route_id)
        return self._route_row(r) if r else None

    def legs(self, route_id):
        out = []
        for r in self._g.read(q.LEGS, id=route_id):
            p = r["p"]
            out.append({"route_id": route_id, "leg_id": p["leg_id"], "sequence": r["sequence"], "origin_location_id": p.get("origin_location_id") or p.get("from_id"),
                        "destination_location_id": p.get("destination_location_id") or p.get("to_id"), "transport_mode": p.get("mode"), "planned_transit_days": p.get("planned_transit_days"),
                        "estimated_cost": p.get("estimated_cost"), "status": p.get("leg_status"), "distance_km": p.get("distance_km")})
        return out

    def routes_between(self, origin, destination):
        return [self._route_row(r) for r in self._g.read(q.ROUTES_BETWEEN, origin=origin, destination=destination)]

    def location(self, location_id):
        for label, key in KINDS["location"]:
            r = self._one(q.LOCATION.format(label=label, key=key), id=location_id)
            if r:
                p = r["p"]
                return {"location_id": location_id, "name": p.get("name"), "graph_label": label, "location_type": p.get("logistics_type") or LOCATION_TYPE_BY_LABEL.get(label),
                        "country_code": p.get("country_code"), "country": p.get("country"), "region": p.get("region"), "latitude": p.get("latitude"), "longitude": p.get("longitude"),
                        "timezone": p.get("timezone"), "city": p.get("city"), **self._prov(p)}
        return None

    def order(self, order_id):
        r = self._one(q.ORDER, id=order_id)
        if not r:
            return None
        p = r["p"]
        return {"order_id": order_id, "status": p.get("order_status"), "order_date": p.get("order_date"), "channel": p.get("channel"), "customer_id": r["customer_id"], "dealer_id": r["dealer_id"],
                **self._prov(p)}

    def order_part(self, order_line_id):
        return self._one(q.ORDER_PART, id=order_line_id)
