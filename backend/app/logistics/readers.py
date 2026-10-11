"""Where shipment context data comes from. Two readers return the SAME canonical-named dictionaries:

  FileReader   the canonical dataset files (no database: used by tests and for offline work)
  GraphReader  the Neo4j graph (read-only)

Because both speak the canonical vocabulary, the context builder is identical on either, and a test can check that the files and the graph agree.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from app.canonical.graph_rows import LOCATION_KIND_BY_LABEL, graph_row
from app.canonical.io import CANON_DIR, load_rows
from app.canonical.registry import BY_NAME, KINDS
from app.graph.client import GraphClient
from app.graph.queries import logistics as q

LOCATION_TYPE_BY_LABEL = {"Warehouse": "WAREHOUSE", "ShipTo": None, "Plant": "PLANT", "Dealer": "DEALER", "Supplier": "SUPPLIER", "Location": None, "TransportTerminal": "TERMINAL"}


class LogisticsReader(Protocol):
    def shipment(self, shipment_id: str) -> dict[str, Any] | None: ...
    def events(self, shipment_id: str) -> list[dict[str, Any]]: ...
    def shipment_lines(self, shipment_id: str) -> list[str]: ...
    def route(self, route_id: str) -> dict[str, Any] | None: ...
    def legs(self, route_id: str) -> list[dict[str, Any]]: ...
    def routes_between(self, origin: str, destination: str) -> list[dict[str, Any]]: ...
    def network_routes(self) -> list[dict[str, Any]]: ...
    def location(self, location_id: str) -> dict[str, Any] | None: ...
    def order(self, order_id: str) -> dict[str, Any] | None: ...
    def order_part(self, order_line_id: str) -> dict[str, Any] | None: ...
    def order_lines(self, order_id: str) -> list[dict[str, Any]]: ...
    def shipments_of_order(self, order_id: str) -> list[dict[str, Any]]: ...
    def orders_of_customer(self, customer_id: str) -> list[str]: ...


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

    def shipment_lines(self, shipment_id):
        key = "shipment_lines"
        if key not in self._cache:
            grouped: dict[str, list[str]] = defaultdict(list)
            for r in self._rows("shipment_lines", "network_shipment_lines"):
                grouped[r["shipment_id"]].append(r["order_line_id"])
            self._cache[key] = grouped  # type: ignore[assignment]
        return sorted(self._cache[key].get(shipment_id, []))  # type: ignore[union-attr]

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

    def network_routes(self):
        return sorted(self._rows("network_routes"), key=lambda r: r["route_id"])

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

    def order_lines(self, order_id):
        lines = [r for r in self._rows("order_lines", "network_order_lines") if r["order_id"] == order_id]
        parts = self._index("part", "part_id", "parts")
        return [{"order_line_id": r["order_line_id"], "part_id": r["part_id"], "part_number": (parts.get(r["part_id"]) or {}).get("part_number"), "name": (parts.get(r["part_id"]) or {}).get("name"),
                 "quantity": r["quantity"], "unit_price": r.get("unit_price"), "data_status": r.get("data_status"), "source_type": r.get("source_type"), "source_record_id": r.get("source_record_id")}
                for r in sorted(lines, key=lambda x: x["order_line_id"])]

    def shipments_of_order(self, order_id):
        return sorted((r for r in self._rows("shipments", "network_shipments") if r.get("order_id") == order_id), key=lambda r: r["shipment_id"])

    def orders_of_customer(self, customer_id):
        return sorted(r["order_id"] for r in self._rows("orders", "network_orders") if r.get("customer_id") == customer_id)


# ── the graph ────────────────────────────────────────────────────────────────────────────────────
class GraphReader:
    def __init__(self, graph: GraphClient) -> None:
        self._g = graph

    def _one(self, query: str, **params: Any) -> dict[str, Any] | None:
        rows = self._g.read(query, **params)
        return rows[0] if rows else None

    def shipment(self, shipment_id):
        r = self._one(q.SHIPMENT, id=shipment_id)
        if not r:
            return None
        p = r["p"]
        route_id = p.get("route_id") or r["route_rel"]
        return graph_row("shipments", p, order_id=r["order_id"], carrier=r["carrier"], carrier_id=r["carrier_id"], route_id=route_id,
                         origin_location_id=r["origin"], destination_location_id=r["destination"],
                         route_resolution_status=p.get("route_resolution_status") or ("LINKED" if route_id else "ROUTE_NOT_DETERMINABLE"))

    def shipment_lines(self, shipment_id):
        return [r["id"] for r in self._g.read(q.SHIPMENT_LINES, id=shipment_id)]

    def events(self, shipment_id):
        return [graph_row("tracking_events", r["p"], shipment_id=shipment_id, location_id=r["location_id"], event_type=r["p"].get("event_type") or r["p"].get("event_status"))
                for r in self._g.read(q.EVENTS, id=shipment_id)]

    @staticmethod
    def _route_row(r: dict[str, Any]) -> dict[str, Any]:
        p = r["p"]
        return graph_row("routes", p, origin_location_id=p.get("origin_location_id") or p.get("origin_depot_id"),
                         destination_location_id=p.get("destination_location_id") or p.get("destination_shipto_id"),
                         estimated_cost=p.get("estimated_cost") if p.get("estimated_cost") is not None else r["cost"], currency=p.get("currency") or r["currency"])

    def route(self, route_id):
        r = self._one(q.ROUTE, id=route_id)
        return self._route_row(r) if r else None

    @staticmethod
    def _leg_id(h: dict[str, Any], route_id: str, leg_id: str) -> str:
        """The canonical route_leg_id. Seeded legs: the HAS_LEG relationship id without its prefix. Network legs are linked by the engine's generic edge, whose id is
        'HAS_LEG:<route>:<leg>' while the canonical record id is '<route>><leg>': the same pair, written with the separator the canonical dataset uses."""
        rid = str(h.get("rel_id", "")).removeprefix("HAS_LEG:")
        return f"{route_id}>{leg_id}" if rid == f"{route_id}:{leg_id}" else rid

    def legs(self, route_id):
        out = []
        for r in self._g.read(q.LEGS, id=route_id):
            p, h = r["p"], r["hp"]
            # the leg record is the HAS_LEG relationship (its id, provenance and sequence) joined to the leg node (route, places, mode, status)
            row = graph_row("route_legs", {**p, **{k: v for k, v in h.items() if k in ("data_status", "source_type", "source_record_id", "effective_from", "effective_to")}},
                            route_id=route_id, route_leg_id=self._leg_id(h, route_id, p["leg_id"]), leg_id=p["leg_id"], sequence=r["sequence"],
                            origin_location_id=p.get("origin_location_id") or p.get("from_id"), destination_location_id=p.get("destination_location_id") or p.get("to_id"),
                            transport_mode=p.get("mode") or p.get("transport_mode"), status=p.get("leg_status"))
            out.append(row)
        return out

    def routes_between(self, origin, destination):
        return [self._route_row(r) for r in self._g.read(q.ROUTES_BETWEEN, origin=origin, destination=destination)]

    def network_routes(self):
        return [self._route_row(r) for r in self._g.read(q.ROUTES_NETWORK)]

    def location(self, location_id):
        for label, key in KINDS["location"]:
            r = self._one(q.LOCATION.format(label=label, key=key), id=location_id)
            if r:
                p = r["p"]
                location_type = p.get("logistics_type") or LOCATION_TYPE_BY_LABEL.get(label)
                kind = LOCATION_KIND_BY_LABEL.get(label) or location_type  # a plain Location node is its own logistics type; the other labels name the kind
                return graph_row("locations", p, location_id=location_id, graph_label=label, location_kind=kind, location_type=location_type)
        return None

    def order(self, order_id):
        r = self._one(q.ORDER, id=order_id)
        if not r:
            return None
        return graph_row("orders", r["p"], order_id=order_id, customer_id=r["customer_id"], dealer_id=r["dealer_id"])

    def order_part(self, order_line_id):
        return self._one(q.ORDER_PART, id=order_line_id)

    def order_lines(self, order_id):
        return [{"order_line_id": r["order_line_id"], "part_id": r["part_id"], "part_number": r["part_number"], "name": r["name"], "quantity": r["quantity"], "unit_price": r["unit_price"],
                 "data_status": r["data_status"], "source_type": r["data_status"] if r["data_status"] == "SYNTHETIC_DEMO" else None, "source_record_id": r["source_record_id"]}
                for r in self._g.read(q.ORDER_LINES, id=order_id)]

    def shipments_of_order(self, order_id):
        return [s for s in (self.shipment(r["id"]) for r in self._g.read(q.SHIPMENT_IDS_OF_ORDER, id=order_id)) if s]

    def orders_of_customer(self, customer_id):
        return [r["id"] for r in self._g.read(q.ORDER_IDS_OF_CUSTOMER, id=customer_id)]
