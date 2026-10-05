"""Supply relationships: depot inventory, supplier->part, dealer->part, replenishment and service requirements.

Rules: no Cartesian products. A relationship exists only where a business rationale is encoded here, and every rule uses only facts the
catalogue already states (fitment, category, subcategory, status). Nothing is inferred about interchangeability or engineering.
"""
from __future__ import annotations

from typing import Any

from build_entities import FAMILIES, SPEC_CATEGORIES, SPEC_KEYWORDS, Actor
from common import TODAY, stable_int
from geo import haversine_km
from model import Existing, Model

FAST_CATEGORIES = {"Filtration", "Lubrication", "Brakes", "Cooling", "Hydraulics", "Electrical"}
WORKSHOP_WORDS = ["cylinder", "pump", "valve", "gearbox", "differential", "axle", "planetary", "clutch", "transfer", "final drive", "caliper", "master cylinder",
                  "loader arm", "stabilizer", "crossmember", "steering column"]
DIAGNOSTIC_WORDS = ["control module", "joystick", "instrument cluster", "starter", "alternator", "proximity sensor", "load sensor"]
FIELD_WORDS = ["filter", "seal", "pad", "hose", "belt", "bushing", "pin", "grease", "lubrication", "brush", "blade", "bucket", "tine", "fork", "wiper", "headlight",
               "battery", "seat belt", "beacon", "coupling", "dipstick", "nipple", "thermostat", "fan", "disc", "chain"]


def part_text(p: dict[str, Any]) -> str:
    return f"{p['subcategory'] or ''} {p['name'] or ''}".lower()


def part_families(ex: Existing) -> dict[str, set[str]]:
    fam = {x["id"]: x["family"] for x in ex.machines}
    return {p["id"]: {fam[mid] for mid in p["machines"] if mid in fam} for p in ex.parts}


def nearest(actor: Actor, depots: list[Actor], n: int) -> list[Actor]:
    return sorted(depots, key=lambda d: haversine_km(actor.lat, actor.lon, d.lat, d.lon))[:n]


def build_inventory(m: Model, ex: Existing, depots: list[Actor]) -> None:
    pf = part_families(ex)
    for d in depots:
        if not d.is_new:
            continue  # the four original depots keep their inventory exactly as imported
        for p in ex.parts:
            if not (pf[p["id"]] & set(d.families)):
                continue
            if stable_int("inv", d.id, p["id"], mod=100) >= 60:
                continue
            u = stable_int("invs", d.id, p["id"], mod=100)
            base = {"reorder_point": 5, "last_inventory_update": TODAY, "inventory_basis": "SYNTHETIC_DEMO_SNAPSHOT"}
            if u < 2:  # unknown stays unknown: no quantity is stored, never a zero
                props = {**base, "stock_status": "UNKNOWN", "replenishment_status": "UNKNOWN"}
            elif p["availability"] in ("BACKORDER", "LIMITED"):  # keep the catalogue profile's availability true: no new stock for these parts
                on_order = stable_int("oo", d.id, p["id"], mod=100) < 60
                props = {**base, "on_hand": 0, "available": 0, "reserved": 0, "allocated": 0, "stock_status": "ON_ORDER" if on_order else "OUT_OF_STOCK",
                         "replenishment_status": "ORDERED" if on_order else "PLANNED"}
            else:
                on_hand = 0 if u < 7 else 3 + stable_int("qty", d.id, p["id"], mod=70)
                reserved = on_hand * stable_int("res", d.id, p["id"], mod=12) // 100
                allocated = on_hand * stable_int("alc", d.id, p["id"], mod=8) // 100
                available = max(on_hand - reserved - allocated, 0)
                if on_hand == 0:
                    status, repl = ("ON_ORDER", "ORDERED") if stable_int("oo", d.id, p["id"], mod=100) < 70 else ("OUT_OF_STOCK", "PLANNED")
                else:
                    status, repl = ("LOW_STOCK", "ORDERED") if available <= 5 else ("IN_STOCK", "NONE")
                props = {**base, "on_hand": on_hand, "available": available, "reserved": reserved, "allocated": allocated, "stock_status": status, "replenishment_status": repl}
            m.rel("AVAILABLE_AT", ("Part", p["id"]), ("Warehouse", d.id), "eu_depot_inventory", props)


def build_supplier_parts(m: Model, ex: Existing, suppliers: list[Actor], depots: list[Actor]) -> None:
    for s in suppliers:
        if s.is_new:
            cats = {c for sp in s.extra["specialisations"] for c in SPEC_CATEGORIES[sp]}
            words = [w for sp in s.extra["specialisations"] for w in SPEC_KEYWORDS[sp]]
            lead = {"FAST": (3, 4), "STANDARD": (7, 8), "EXTENDED": (15, 14)}[m.nodes["Supplier"][s.id]["lead_time_class"]]
            seq = 0
            for p in ex.parts:
                if p["category"] not in cats or not any(w in part_text(p) for w in words):
                    continue
                if stable_int("sp", s.id, p["id"], mod=100) >= 70 or (p["id"], s.id) in ex.existing_part_suppliers:
                    continue
                seq += 1
                m.rel("SUPPLIED_BY", ("Part", p["id"]), ("Supplier", s.id), "eu_part_suppliers", {
                    "is_primary": False, "lead_time_days": lead[0] + stable_int("lt", s.id, p["id"], mod=lead[1]), "min_order_qty": 1 + stable_int("moq", s.id, p["id"], mod=10),
                    "supplier_part_number": f"{s.id[4:]}-{p['number']}", "relationship_status": "ACTIVE_DEMO", "basis": "SPECIALISATION_AND_CATALOGUE_CATEGORY"})
            if seq == 0:  # keyword gate matched nothing: fall back to the first catalogue parts in the supplier's own categories
                for p in sorted((q for q in ex.parts if q["category"] in cats and (q["id"], s.id) not in ex.existing_part_suppliers), key=lambda q: stable_int("spf", s.id, q["id"], mod=10**6))[:3]:
                    m.rel("SUPPLIED_BY", ("Part", p["id"]), ("Supplier", s.id), "eu_part_suppliers", {
                        "is_primary": False, "lead_time_days": lead[0] + stable_int("lt", s.id, p["id"], mod=lead[1]), "min_order_qty": 1 + stable_int("moq", s.id, p["id"], mod=10),
                        "supplier_part_number": f"{s.id[4:]}-{p['number']}", "relationship_status": "ACTIVE_DEMO", "basis": "SPECIALISATION_AND_CATALOGUE_CATEGORY"})
        for d in nearest(s, depots, 2):  # configured receiving depots: explicit, not inferred
            m.rel("REPLENISHES_DEPOT", ("Supplier", s.id), ("Warehouse", d.id), "eu_supplier_depots", {
                "lead_time_days": 1 + int(haversine_km(s.lat, s.lon, d.lat, d.lon) // 600) + stable_int("rl", s.id, d.id, mod=3), "basis": "CONFIGURED_REPLENISHMENT",
                "priority": 1 + [x.id for x in nearest(s, depots, 2)].index(d.id)})


def build_dealer_parts(m: Model, ex: Existing, dealers: list[Actor], depots: list[Actor]) -> None:
    pf = part_families(ex)
    for a in dealers:
        for k, d in enumerate(nearest(a, depots, 2)):
            m.rel("REPLENISHED_FROM", ("Dealer", a.id), ("Warehouse", d.id), "eu_dealer_depots", {"priority": k + 1, "basis": "CONFIGURED_REPLENISHMENT"})
        mset = set(a.machines)
        fits = [p for p in ex.parts if mset & set(p["machines"])]
        has_parts, has_pm = "PARTS" in a.caps, "PREVENTIVE_MAINTENANCE" in a.caps
        for p in fits:
            orderable = p["status"] == "VERIFIED" and p["orderable"] is True
            stocked = False
            if has_parts and a.is_new and p["availability"] == "IN_STOCK" and orderable and (p["id"], a.id) not in ex.existing_part_dealers:
                limit = 50 if p["category"] in FAST_CATEGORIES else 16
                if stable_int("dst", a.id, p["id"], mod=100) < limit:
                    stocked = True
                    on_hand = 1 + stable_int("dq", a.id, p["id"], mod=9)
                    m.rel("STOCKED_BY", ("Part", p["id"]), ("Dealer", a.id), "eu_dealer_stock", {
                        "stocking_status": "STOCKED_DEMO", "stock_status": "LOW_STOCK" if on_hand <= 2 else "IN_STOCK", "on_hand": on_hand, "available": on_hand, "reserved": 0,
                        "reorder_point": 1, "last_inventory_update": TODAY})
            if has_parts and orderable and not stocked and (p["id"], a.id) not in ex.existing_part_dealers:
                m.rel("CAN_ORDER_PART", ("Dealer", a.id), ("Part", p["id"]), "eu_dealer_part_support", {"order_channel": "VIA_REPLENISHMENT_DEPOT", "basis": "SUPPORTS_FITTED_MACHINE_AND_PART_IS_ORDERABLE"})
            text = part_text(p)
            needs_ws = any(w in text for w in WORKSHOP_WORDS)
            needs_diag = any(w in text for w in DIAGNOSTIC_WORDS)
            simple = any(w in text for w in FIELD_WORDS)
            if (needs_ws and "WORKSHOP" in a.caps) or (needs_diag and {"DIAGNOSTICS", "WORKSHOP"} <= a.caps) or (simple and not needs_ws and {"FIELD_SERVICE", "WORKSHOP"} & a.caps):
                m.rel("INSTALLS_PART", ("Dealer", a.id), ("Part", p["id"]), "eu_dealer_part_support", {"basis": "HAS_REQUIRED_CAPABILITY_AND_SUPPORTS_FITTED_MACHINE"})
        if has_pm:
            for mid in a.machines:
                for pid in ex.service_plan_parts.get(mid, []):
                    m.rel("SERVICES_PART", ("Dealer", a.id), ("Part", pid), "eu_dealer_part_support", {"basis": "SERVICE_PLAN_PART_FOR_SUPPORTED_MACHINE"}, f":{mid}")


def build_part_service(m: Model, ex: Existing) -> None:
    for p in ex.parts:
        text = part_text(p)
        if any(w in text for w in DIAGNOSTIC_WORDS):
            m.rel("REQUIRES_SERVICE", ("Part", p["id"]), ("Capability", "CAP-DIAGNOSTICS"), "eu_part_service", {"basis": "SUBCATEGORY_RULE"})
        elif any(w in text for w in WORKSHOP_WORDS):
            m.rel("REQUIRES_SERVICE", ("Part", p["id"]), ("Capability", "CAP-WORKSHOP"), "eu_part_service", {"basis": "SUBCATEGORY_RULE"})
        elif any(w in text for w in FIELD_WORDS):
            m.rel("INSTALLABLE_BY", ("Part", p["id"]), ("Capability", "CAP-FIELD_SERVICE"), "eu_part_service", {"basis": "SUBCATEGORY_RULE"})
