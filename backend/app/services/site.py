"""Business facts for the company website and the Agentic E-Commerce launch film, read from Neo4j.

The frontend keeps no catalogue of its own: machine, plant, brand, part, price, stock, supplier and delivery values all come
from here. Synthetic demo records keep their "(demo)" names and their data_status, so the UI can label them.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import NotFoundError
from app.graph.client import GraphClient
from app.graph.queries import site as q


class SiteService:
    """Which records the launch film features is the FeaturedScenario record in the graph; where a city is comes from graph locations. Nothing is kept in code."""

    def __init__(self, graph: GraphClient) -> None:
        self._g = graph
        self._points: dict[str, tuple[float, float]] | None = None

    def _point(self, city: str | None) -> dict[str, float | None]:
        if self._points is None:
            self._points = {}
            for r in self._g.read(q.CITY_POINTS):
                self._points.setdefault(r["city"], (r["lat"], r["lon"]))  # rows arrive in priority order
        lat, lon = self._points.get(city or "", (None, None))
        return {"lat": lat, "lon": lon}

    def overview(self) -> dict[str, Any]:
        machines = []
        for r in self._g.read(q.SITE_MACHINES):
            parts = sorted(r["parts"], key=lambda p: p["part_number"])
            machines.append({
                "model": r["model_code"], "slug": r["model_code"].lower(), "machine_id": r["machine_id"], "name": r["machine_type"], "full_name": r["name"],
                "family": r["family"], "brand": r["brand"], "acquired": r["acquired_year"], "plant_id": r["plant_id"], "plant": r["plant"], "plant_city": r["plant_city"],
                "plant_country_code": r["plant_country_code"], "data_status": r["data_status"], "parts": parts,
                "attachments": [p["name"] for p in parts if p["category"] == "Attachments"], "profile": r["profile"],
            })
        plants = [{**r, **self._point(r["city"])} for r in self._g.read(q.SITE_PLANTS)]
        cat = (self._g.read(q.SITE_CATALOGUE) or [{"parts": 0, "categories": []}])[0]
        families = sorted({m["family"] for m in machines if m["family"]})
        return {"machines": machines, "plants": plants, "families": families, "part_count": cat["parts"],
                "part_categories": sorted(cat["categories"], key=lambda c: (-c["count"], c["name"]))}

    def film(self) -> dict[str, Any]:
        pick = (self._g.read(q.FILM_SCENARIO) or [None])[0]
        if not pick or not (pick["model"] and pick["part"] and pick["customer"]):
            raise NotFoundError("Film scenario record", "FeaturedScenario FILM")
        film_machine, film_part, film_customer = pick["model"], pick["part"], pick["customer"]
        rows = self._g.read(q.FILM, model=film_machine, part=film_part, customer=film_customer)
        if not rows:
            raise NotFoundError("Film story records", f"{film_machine}/{film_part}/{film_customer}")
        r = rows[0]
        m, p, prof, cu = r["machine"], r["part"], r["profile"] or {}, r["customer"]
        stock = [{**s, "available": int(s["available"] or 0), "pickup": bool(s["pickup"]), **self._point(s["city"])} for s in [*r["warehouses"], *r["dealers"]]]
        stocked = [s["id"] for s in stock if s["kind"] == "warehouse" and s["available"] > 0]
        delivery = (self._g.read(q.FILM_DELIVERY, customer=film_customer, warehouses=stocked) or [None])[0]
        supplier = next((s for s in r["suppliers"] if s["primary"]), r["suppliers"][0] if r["suppliers"] else None)
        counts = self._g.read(q.FILM_COUNTS)[0]
        services = sorted(r["services"], key=lambda s: s["hours"] or 0)
        pickup = next((s["id"] for s in stock if s["kind"] == "dealer" and s["city"] == cu["city"] and s["available"] > 0 and s["pickup"]), None)
        return {
            "counts": counts,
            "machine": {"model": m["model_code"], "name": m["name"], "type": m["machine_type"], "plant": m["origin_plant"], "country": m["country"],
                        "partsFitted": r["parts_fitted"], "inStock": r["in_stock"], "legacyMapped": r["legacy_mapped"], "slug": m["model_code"].lower(),
                        "services": [s["name"] for s in services], "serviceInterval": [s["hours"] for s in services]},
            "part": {"id": p["part_id"], "no": p["part_number"], "name": p["name"], "category": p["category"], "subcategory": p["subcategory"] or "",
                     "legacyNo": r["legacy_no"], "legacyBusiness": r["legacy_business"] or "", "plant": p["origin_plant"],
                     "fits": [x.strip() for x in str(p["compatible_models_source"] or "").split(",") if x.strip()], "specNote": p["spec_note_source"] or "",
                     "priceExVat": r["price_ex_vat"], "weightKg": prof.get("weight_kg"), "status": prof.get("part_status"), "availability": prof.get("availability_state"),
                     "usedInService": bool(r["service_plans_with_part"])},
            "siblings": sorted(r["siblings"], key=lambda s: s["no"])[:6],
            "supplier": {"id": supplier["id"], "name": supplier["name"], "city": supplier["city"], "leadDays": supplier["lead"], "partNo": supplier["part_no"], **self._point(supplier["city"])} if supplier else None,
            "stock": sorted(stock, key=lambda s: (s["kind"], s["id"])),
            "customer": {"id": cu["customer_id"], "name": cu["name"], "city": cu["city"], **self._point(cu["city"])},
            "pickupDealer": pickup,
            "delivery": {"from": delivery["warehouse_id"], "km": delivery["km"], "standard": {"price": delivery["standard_price"], "days": delivery["standard_days"]},
                         "express": {"price": delivery["express_price"], "days": delivery["express_days"]}} if delivery else None,
            "provenance": "Machine, part, fitment and legacy records come from the supplied catalogue; suppliers, dealers, stock, prices, customers and delivery are synthetic demo data in the Noordveld graph.",
        }
