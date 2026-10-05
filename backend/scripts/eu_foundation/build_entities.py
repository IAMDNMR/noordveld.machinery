"""Entities of the European network: geography, capabilities, depots, dealers, suppliers, customers and ship-to locations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common import pick, stable_int, unit
from geo import CITIES_BY_COUNTRY, CITY, COUNTRIES, EU27, haversine_km
from model import Existing, Model, node_props
from names import company, email, group, person, phone, postal, slug, street

FAMILIES = {"FAM-NV": "NV", "FAM-KFT": "KFT", "FAM-BTS": "BTS"}
FAM_IDS = list(FAMILIES)
CAPABILITIES = ["PARTS", "SERVICE", "MACHINE_SALES", "FIELD_SERVICE", "WORKSHOP", "EMERGENCY_SERVICE", "MOBILE_SERVICE", "WARRANTY_SERVICE", "DIAGNOSTICS",
                "PREVENTIVE_MAINTENANCE", "TRAINING", "RENTAL_SUPPORT"]
INDUSTRIES = ["construction", "quarrying", "aggregates", "logistics", "warehousing", "manufacturing", "agriculture", "ports", "recycling", "infrastructure",
              "utilities", "industrial processing", "material handling"]
INDUSTRY_MACHINES = {
    "construction": ["NV-2100", "NV-3200", "NV-4500", "NV-6000"], "quarrying": ["NV-4500", "NV-7500"], "aggregates": ["NV-3200", "NV-4500", "NV-7500"],
    "logistics": ["KFT-120", "KFT-200", "KFT-450", "BTS-500"], "warehousing": ["KFT-120", "KFT-200", "KFT-450", "KFT-800", "BTS-500", "BTS-750"],
    "manufacturing": ["KFT-120", "KFT-200", "KFT-800", "BTS-100", "BTS-500", "BTS-750"], "agriculture": ["NV-2100", "NV-3200", "NV-6000", "NV-7500"],
    "ports": ["NV-4500", "NV-7500", "KFT-450", "BTS-900"], "recycling": ["NV-3200", "NV-4500", "BTS-100"], "infrastructure": ["NV-2100", "NV-4500", "NV-6000"],
    "utilities": ["NV-2100", "NV-6000"], "industrial processing": ["KFT-600", "BTS-100", "BTS-250", "BTS-500"], "material handling": ["KFT-200", "KFT-450", "KFT-600", "BTS-750", "BTS-900"],
}
# dealers per country (total, existing included). Higher density in NL, DE, BE, FR, IT, PL, ES, AT, CZ.
DEALER_TARGET = {"NL": 14, "DE": 14, "BE": 5, "FR": 7, "IT": 6, "PL": 6, "ES": 5, "AT": 4, "CZ": 4, "SE": 3, "DK": 3, "FI": 2, "PT": 2, "RO": 2, "HU": 2, "SK": 2,
                 "SI": 1, "HR": 1, "GR": 2, "IE": 1, "LT": 1, "LV": 1, "EE": 1, "LU": 1, "MT": 1, "CY": 1, "BG": 1}
CUSTOMER_TARGET = {"NL": 22, "DE": 24, "BE": 8, "FR": 10, "IT": 8, "PL": 8, "ES": 6, "AT": 4, "CZ": 4, "SE": 3, "DK": 3, "FI": 2, "PT": 2, "RO": 2, "HU": 2, "SK": 1,
                   "SI": 1, "HR": 1, "GR": 1, "IE": 1, "LT": 1, "LV": 1, "EE": 1, "LU": 1, "MT": 1, "CY": 1, "BG": 1}
SUPPLIER_PLAN = [("DE", 6), ("NL", 3), ("BE", 2), ("FR", 3), ("IT", 3), ("PL", 3), ("ES", 2), ("AT", 2), ("CZ", 2), ("SE", 1), ("DK", 1)]
SPECIALISATIONS = list(__import__("names").SUPPLIER_TRADE)
SPEC_CATEGORIES = {  # which catalogue categories a specialisation can supply (a supplier is only linked to parts inside these)
    "hydraulics": ["Hydraulics"], "seals": ["Hydraulics", "Drivetrain"], "hoses": ["Hydraulics", "Cooling", "Lubrication"], "fittings": ["Hydraulics", "Lubrication"],
    "electrical": ["Electrical"], "sensors": ["Electrical"], "controls": ["Cab & Controls", "Electrical"], "safety": ["Cab & Controls", "Electrical"],
    "bearings": ["Drivetrain", "Structural"], "fasteners": ["Structural"], "drivetrain": ["Drivetrain"], "material handling": ["Attachments", "Structural"],
    "conveyor components": ["Drivetrain", "Structural"], "structural": ["Structural"], "braking": ["Brakes"], "wheels/rollers": ["Drivetrain"],
}
SPEC_KEYWORDS = {
    "hydraulics": ["hydraulic", "cylinder", "pump", "valve"], "seals": ["seal"], "hoses": ["hose"], "fittings": ["coupling", "nipple", "grease", "line"],
    "electrical": ["wiring", "battery", "alternator", "starter", "headlight", "beacon", "switch", "module"], "sensors": ["sensor"],
    "controls": ["joystick", "control", "steering", "instrument", "display"], "safety": ["seat belt", "beacon", "warning", "glass"],
    "bearings": ["bearing", "bushing", "housing"], "fasteners": ["pin", "bracket", "bushing", "tie rod"],
    "drivetrain": ["gear", "axle", "chain", "belt", "clutch", "joint", "shaft", "carrier", "sprocket"], "material handling": ["bucket", "fork", "tine", "grapple", "coupler", "blade", "brush"],
    "conveyor components": ["belt", "chain", "sprocket", "roller"], "structural": ["loader arm", "boom", "frame", "counterweight", "chassis", "lift arm", "stabilizer", "tow", "mount", "footstep"],
    "braking": ["brake"], "wheels/rollers": ["wheel", "rim", "roller", "track"],
}
LANGS = {"NL": ["nl", "en"], "BE": ["nl", "fr", "en"], "DE": ["de", "en"], "AT": ["de", "en"], "LU": ["fr", "de", "en"], "FR": ["fr", "en"], "IT": ["it", "en"], "ES": ["es", "en"],
         "PT": ["pt", "en"], "PL": ["pl", "en"], "CZ": ["cs", "en"], "SK": ["sk", "en"], "SE": ["sv", "en"], "DK": ["da", "en"], "FI": ["fi", "sv", "en"], "EE": ["et", "en"],
         "LV": ["lv", "en"], "LT": ["lt", "en"], "RO": ["ro", "en"], "HU": ["hu", "en"], "SI": ["sl", "en"], "HR": ["hr", "en"], "GR": ["el", "en"], "CY": ["el", "en"],
         "BG": ["bg", "en"], "IE": ["en"], "MT": ["mt", "en"]}
FAMILY_AFFINITY = {"NL": (80, 60, 45), "BE": (70, 60, 35), "DE": (50, 85, 60), "AT": (40, 80, 40), "CZ": (45, 75, 50), "PL": (55, 70, 55), "FR": (70, 55, 40), "IT": (45, 65, 55),
                   "ES": (50, 60, 40), "PT": (55, 45, 30), "SE": (70, 50, 40), "DK": (70, 50, 30), "FI": (75, 40, 30), "IE": (70, 40, 10), "LU": (40, 60, 20), "SK": (40, 65, 35),
                   "HU": (45, 60, 35), "SI": (40, 60, 25), "HR": (45, 50, 25), "GR": (55, 35, 15), "RO": (60, 40, 25), "BG": (55, 40, 20), "LT": (55, 45, 20), "LV": (55, 45, 20),
                   "EE": (55, 45, 20), "MT": (40, 40, 10), "CY": (45, 35, 10)}
DEPOTS_NEW = [  # country, city, type, capacity class, families served
    ("NL", "Venlo", "CENTRAL_DC", "XL", ["FAM-NV", "FAM-KFT", "FAM-BTS"]), ("DE", "Duisburg", "CENTRAL_DC", "XL", ["FAM-NV", "FAM-KFT", "FAM-BTS"]),
    ("DE", "Nuernberg", "REGIONAL_DEPOT", "L", ["FAM-KFT", "FAM-BTS"]), ("BE", "Mechelen", "REGIONAL_DEPOT", "M", ["FAM-NV", "FAM-KFT"]),
    ("FR", "Lille", "REGIONAL_DEPOT", "L", ["FAM-NV", "FAM-KFT"]), ("FR", "Lyon", "REGIONAL_DEPOT", "M", ["FAM-KFT", "FAM-NV"]),
    ("PL", "Katowice", "REGIONAL_DEPOT", "L", ["FAM-KFT", "FAM-BTS", "FAM-NV"]), ("CZ", "Brno", "REGIONAL_DEPOT", "M", ["FAM-KFT", "FAM-BTS"]),
    ("AT", "Linz", "CROSS_DOCK_DEPOT", "S", ["FAM-KFT", "FAM-NV"]), ("IT", "Verona", "REGIONAL_DEPOT", "M", ["FAM-KFT", "FAM-BTS"]),
]


@dataclass
class Actor:
    id: str
    cc: str
    city: str
    lat: float
    lon: float
    kind: str
    is_new: bool = True
    tier: int = 3
    caps: set[str] = field(default_factory=set)
    families: list[str] = field(default_factory=list)
    machines: list[str] = field(default_factory=list)
    postal_code: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class Geo:
    """Locations, regions and addresses. Cities and regions are created only when something is placed in them."""

    def __init__(self, m: Model, ex: Existing) -> None:
        self.m, self.ex = m, ex
        self.region_by = {(r["cc"], r["name"]): r["id"] for r in ex.regions}
        self.region_ids = set(ex.all_ids["Region"])
        self.loc_ids = set(ex.all_ids["Location"])
        self.city_loc = {(l["cc"], l["name"]): l["id"] for l in ex.locations if l["type"] == "CITY"}
        self.country_loc = {l["cc"]: l["id"] for l in ex.locations if l["type"] == "COUNTRY"}
        self.used_cities: dict[tuple[str, str], str] = dict(self.city_loc)
        self.used_regions: set[str] = set()
        self.address_seq = 0

    def country(self, cc: str) -> str:
        if cc not in self.country_loc:
            lid = f"LOC-{cc}"
            self.m.node("Location", lid, node_props("eu_locations", lid, {"name": COUNTRIES[cc][0], "location_type": "COUNTRY", "country_code": cc, "eu_member": True}))
            self.country_loc[cc] = lid
        return self.country_loc[cc]

    def region(self, cc: str, name: str) -> str:
        key = (cc, name)
        if key not in self.region_by:
            base = f"REG-{cc}-{slug(name).upper()[:6]}"
            rid, n = base, 1
            while rid in self.region_ids:
                n += 1
                rid = f"{base}{n}"
            self.region_ids.add(rid)
            self.m.node("Region", rid, node_props("eu_regions", rid, {"name": name, "country": COUNTRIES[cc][0], "country_code": cc, "currency": "EUR"}))
            self.region_by[key] = rid
        self.used_regions.add(self.region_by[key])
        return self.region_by[key]

    def city(self, cc: str, name: str) -> str:
        key = (cc, name)
        if key not in self.used_cities:
            region, lat, lon = CITY[key]
            lid = f"LOC-{cc}-{slug(name).upper()}"
            self.m.node("Location", lid, node_props("eu_locations", lid, {"name": name, "location_type": "CITY", "country_code": cc, "latitude": lat, "longitude": lon, "geo_basis": "APPROX_CITY_CENTRE"}))
            self.m.rel("IN_COUNTRY", ("Location", lid), ("Location", self.country(cc)), "eu_locations")
            self.m.rel("IN_REGION", ("Location", lid), ("Region", self.region(cc, region)), "eu_locations")
            self.used_cities[key] = lid
        return self.used_cities[key]

    def place(self, owner: tuple[str, str], cc: str, city: str, *key: Any) -> tuple[str, str]:
        """Locate an owner in a city and (for operational sites) give it a synthetic street address in that city's region."""
        loc = self.city(cc, city)
        self.m.rel("LOCATED_IN", owner, ("Location", loc), "eu_locations")
        return loc, self.region(cc, CITY[(cc, city)][0])

    def address(self, owner: tuple[str, str], owner_type: str, cc: str, city: str, *key: Any) -> str:
        self.address_seq += 1
        aid = f"ADR-E{self.address_seq:04d}"
        region = CITY[(cc, city)][0]
        zip_ = postal(cc, *key)
        self.m.node("Address", aid, node_props("eu_addresses", aid, {
            "street": street(cc, *key), "house_number": 1 + stable_int(*key, "hn", mod=180), "postal_code": zip_, "city": city, "country_code": cc, "state_region": region,
            "owner_type": owner_type, "address_note": "Synthetic address; street, number and postal code are invented"}))
        self.m.rel("LOCATED_AT_ADDRESS", owner, ("Address", aid), "eu_addresses")
        self.m.rel("IN_REGION", ("Address", aid), ("Region", self.region(cc, region)), "eu_addresses")
        return zip_


def jitter(cc: str, city: str, *key: Any) -> tuple[float, float]:
    _, lat, lon = CITY[(cc, city)]
    return round(lat + (unit(*key, "la") - 0.5) * 0.10, 4), round(lon + (unit(*key, "lo") - 0.5) * 0.14, 4)


def next_city(cc: str, used: dict[str, int], taken: set[str]) -> str:
    cities = CITIES_BY_COUNTRY[cc]
    free = [c for c in cities if c not in taken]
    pool = free or cities
    return pool[used.get(cc, 0) % len(pool)] if not free else free[0]


def existing_industry(customer_name: str) -> str:
    """Industry of an original customer by name keyword (a labelled, derived assignment)."""
    n = customer_name.lower()
    return "logistics" if any(k in n for k in ("logist", "spedition", "transport")) else "construction" if any(k in n for k in ("bouw", "verhuur")) else         "agriculture" if "agri" in n else "ports" if any(k in n for k in ("hafen", "haven", "umschlag", "werf")) else "warehousing" if "warehous" in n else "manufacturing"


def build_reference(m: Model, ex: Existing) -> None:
    for cap in CAPABILITIES:
        m.node("Capability", f"CAP-{cap}", node_props("eu_capabilities", f"CAP-{cap}", {"name": cap.replace("_", " ").title(), "capability_code": cap}))
    for ind in sorted({existing_industry(c["name"]) for c in ex.customers}):  # only the taxonomy the original customers use: no customer master is generated
        iid = f"IND-{slug(ind).upper()}"
        m.node("Industry", iid, node_props("eu_industries", iid, {"name": ind.title(), "industry_code": ind.upper().replace(" ", "_")}))


def machine_by_code(ex: Existing) -> dict[str, dict[str, Any]]:
    return {x["code"]: x for x in ex.machines}


def build_depots(m: Model, ex: Existing, geo: Geo) -> list[Actor]:
    depots = [Actor(w["id"], w["cc"], w["city"], w["lat"], w["lon"], "depot", is_new=False,
                    families=list(FAM_IDS) if w["id"] == "WH-004" else {"WH-001": ["FAM-NV"], "WH-002": ["FAM-KFT"], "WH-003": ["FAM-BTS"]}.get(w["id"], list(FAM_IDS)))
              for w in ex.warehouses]
    for n, (cc, city, wtype, cap, fams) in enumerate(DEPOTS_NEW, start=5):
        wid = f"WH-{n:03d}"
        region, lat, lon = CITY[(cc, city)]
        zip_ = ""
        d = Actor(wid, cc, city, lat, lon, "depot", families=fams, extra={"type": wtype, "capacity": cap})
        name = f"Noordveld EU Depot {city} (demo)" if wtype != "CENTRAL_DC" else f"Noordveld EU Central Distribution {city} (demo)"
        pallet = True
        parcel = wtype != "CROSS_DOCK_DEPOT"
        cap_list = ["PICK_PACK", "PALLET_DISPATCH"] + (["PARCEL_DISPATCH"] if parcel else []) + (["CROSS_BORDER_DISPATCH"] if cc != "XX" else [])
        m.node("Warehouse", wid, node_props("eu_depots", wid, {
            "name": name, "city": city, "country_code": cc, "depot_code": f"DEP-{cc}-{n:03d}", "warehouse_type": wtype, "operating_status": "OPERATIONAL", "pickup_allowed": False,
            "fulfilment_capability": cap_list, "latitude": lat, "longitude": lon, "geo_basis": "APPROX_CITY_CENTRE", "storage_capacity_class": cap,
            "machine_component_capability": [FAMILIES[f] for f in fams], "pallet_capability": pallet, "parcel_capability": parcel,
            "hazardous_handling_capability": wtype == "CENTRAL_DC", "controlled_handling_capability": cap in ("L", "XL"), "operating_hours": "Mon-Fri 06:00-22:00; Sat 07:00-13:00",
            "plant_participation": "NONE (a plant is not automatically a depot)"}))
        zip_ = geo.address(("Warehouse", wid), "WAREHOUSE", cc, city, "depot", wid)
        geo.place(("Warehouse", wid), cc, city)
        d.postal_code = zip_
        depots.append(d)
    for w in depots:
        if not w.is_new:  # existing depots: place them in a city location (additive relationship only)
            geo.place(("Warehouse", w.id), w.cc, w.city)
    return depots


def capability_set(cc: str, tier: int, dtype: str, key: str) -> set[str]:
    u = lambda tag: stable_int("cap", key, tag, mod=100)
    caps: set[str] = set()
    if dtype != "SERVICE_PARTNER" and u("parts") < 88 or tier == 1:
        caps.add("PARTS")
    if u("svc") < (92 if dtype == "SERVICE_PARTNER" else 78) or tier == 1:
        caps.add("SERVICE")
    if dtype == "AUTHORISED_DEALER" and u("sales") < (85 if tier <= 2 else 45):
        caps.add("MACHINE_SALES")
    if "SERVICE" in caps:
        if u("field") < 60:
            caps.add("FIELD_SERVICE")
        if u("ws") < 70 or tier == 1:
            caps.add("WORKSHOP")
        if u("pm") < 60:
            caps.add("PREVENTIVE_MAINTENANCE")
        if u("emg") < (65 if tier == 1 else 28):
            caps.add("EMERGENCY_SERVICE")
        if "FIELD_SERVICE" in caps and u("mob") < 60:
            caps.add("MOBILE_SERVICE")
        if "WORKSHOP" in caps and tier <= 2 and u("diag") < 65:
            caps.add("DIAGNOSTICS")
        if tier <= 2 and u("war") < 55:
            caps.add("WARRANTY_SERVICE")
    if tier == 1 and u("train") < 40:
        caps.add("TRAINING")
    if "SERVICE" in caps and u("rent") < 20:
        caps.add("RENTAL_SUPPORT")
    if not caps:
        caps.add("PARTS")
    return caps


LEGACY_CAP = {"PARTS_RECEIVING": ["PARTS"], "INSTALLATION": ["SERVICE", "FIELD_SERVICE"], "MAINTENANCE": ["PREVENTIVE_MAINTENANCE"], "REPAIR": ["WORKSHOP"]}
CAP_TO_LEGACY = {"PARTS": "PARTS_RECEIVING", "FIELD_SERVICE": "INSTALLATION", "PREVENTIVE_MAINTENANCE": "MAINTENANCE", "WORKSHOP": "REPAIR"}


def build_dealers(m: Model, ex: Existing, geo: Geo) -> list[Actor]:
    mach = {x["id"]: x for x in ex.machines}
    by_family: dict[str, list[str]] = {}
    for x in ex.machines:
        by_family.setdefault(x["family"], []).append(x["id"])
    actors: list[Actor] = []
    taken: dict[str, set[str]] = {}
    count: dict[str, int] = {}
    for d in ex.dealers:  # existing dealers keep every field; they get relationships only
        city = d["city"]
        taken.setdefault(d["cc"], set()).add(city)
        count[d["cc"]] = count.get(d["cc"], 0) + 1
        _, lat, lon = CITY[(d["cc"], city)]
        caps = {c for legacy in ex.existing_dealer_capability.get(d["id"], []) for c in LEGACY_CAP.get(legacy, [])}
        a = Actor(d["id"], d["cc"], city, lat, lon, "dealer", is_new=False, tier=2 if d["cc"] in ("NL", "DE") else 3, caps=caps or {"PARTS"},
                  families=list(ex.existing_dealer_families.get(d["id"], [])))
        actors.append(a)
    seq = 15
    for cc in sorted(DEALER_TARGET, key=lambda c: (-DEALER_TARGET[c], c)):
        need = DEALER_TARGET[cc] - count.get(cc, 0)
        for i in range(max(need, 0)):
            seq += 1
            did = f"DLR-{seq:03d}"
            city = next_city(cc, count, taken.setdefault(cc, set()))
            taken[cc].add(city)
            rank = count.get(cc, 0) + i
            tier = 1 if rank == 0 or (cc in ("NL", "DE") and rank == 1) else (2 if rank <= 3 else 3)
            specialist = stable_int("spec", did, mod=100) < 12
            dtype = "INDUSTRIAL_SPECIALIST" if specialist else ("SERVICE_PARTNER" if stable_int("sp", did, mod=100) < 22 and tier == 3 else "AUTHORISED_DEALER")
            lat, lon = jitter(cc, city, did)
            a = Actor(did, cc, city, lat, lon, "dealer", tier=tier, extra={"dealer_type": dtype})
            a.caps = capability_set(cc, tier, dtype, did)
            aff = FAMILY_AFFINITY[cc]
            fams = [f for f, w in zip(FAM_IDS, aff) if stable_int("fam", did, f, mod=100) < w * 0.85 and (f != "FAM-BTS" or specialist or w >= 55)]
            if specialist and "FAM-BTS" not in fams:
                fams.append("FAM-BTS")
            if not fams:
                fams = [FAM_IDS[max(range(3), key=lambda k: aff[k])]]
            if tier == 1:
                fams = list(dict.fromkeys(["FAM-NV", "FAM-KFT"] + fams)) if cc in ("NL", "DE", "BE", "FR", "PL") else fams
            a.families = fams
            name = company("dealer", cc, did, city)
            contact_name, role = person("dealer", cc, did, 1)
            languages = LANGS[cc]
            hours = "24/7 emergency line; workshop Mon-Fri 07:30-17:00" if "EMERGENCY_SERVICE" in a.caps else pick(["Mon-Fri 07:30-17:00", "Mon-Fri 08:00-17:30", "Mon-Fri 07:00-16:30; Sat 08:00-12:00"], "hours", did)
            legacy = sorted({CAP_TO_LEGACY[c] for c in a.caps if c in CAP_TO_LEGACY} | ({"MAINTENANCE"} if "PREVENTIVE_MAINTENANCE" in a.caps else set()))
            m.node("Dealer", did, node_props("eu_dealers", did, {
                "name": name, "city": city, "country_code": cc, "dealer_code": f"DLR-{cc}-{seq:03d}", "dealer_type": dtype, "dealer_status": "ACTIVE_DEMO", "dealer_tier": f"TIER_{tier}",
                "pickup_allowed": "PARTS" in a.caps, "latitude": lat, "longitude": lon, "geo_basis": "APPROX_CITY_CENTRE", "languages": languages, "opening_hours": hours,
                "phone": phone(cc, did), "email": f"info@{slug(name.replace('(demo)', ''))[:24]}.example", "website": f"https://{slug(name.replace('(demo)', ''))[:24]}.example",
                "service_capability": legacy or ["PARTS_RECEIVING"], "capability_count": len(a.caps)}))
            a.postal_code = geo.address(("Dealer", did), "DEALER", cc, city, "dealer", did)
            geo.place(("Dealer", did), cc, city)
            cid = f"DCT-{did}-01"
            m.node("DealerContact", cid, node_props("eu_dealer_contacts", cid, {"name": contact_name, "contact_role": role, "email": email(contact_name, name), "phone": phone(cc, did, "c1"), "contact_status": "ACTIVE_DEMO"}))
            m.rel("HAS_CONTACT", ("Dealer", did), ("DealerContact", cid), "eu_dealer_contacts")
            for f in fams:
                m.rel("SERVES_FAMILY", ("Dealer", did), ("MachineFamily", f), "eu_dealers")
            actors.append(a)
        count[cc] = count.get(cc, 0) + max(need, 0)
    # model-level support, selling, service categories (for every dealer, existing and new)
    for a in actors:
        if not a.is_new:
            geo.place(("Dealer", a.id), a.cc, a.city)
        for f in a.families:
            ms = by_family.get(f, [])
            k = 2 + stable_int("mk", a.id, f, mod=max(len(ms) - 1, 1))
            ordered = sorted(ms, key=lambda x: stable_int("mo", a.id, x, mod=1000))[:k]
            a.machines += ordered
        for c in sorted(a.caps):
            m.rel("HAS_CAPABILITY", ("Dealer", a.id), ("Capability", f"CAP-{c}"), "eu_dealer_capabilities", {"capability_status": "ACTIVE_DEMO"})
        if {"SERVICE", "FIELD_SERVICE", "WORKSHOP"} & a.caps:
            for f in a.families:
                m.rel("SERVICES_MACHINE_FAMILY", ("Dealer", a.id), ("MachineFamily", f), "eu_dealer_machine_support", {"basis": "CONFIGURED_SERVICE_SUPPORT"})
        if "MACHINE_SALES" in a.caps:
            for f in a.families:
                m.rel("SELLS_MACHINE_FAMILY", ("Dealer", a.id), ("MachineFamily", f), "eu_dealer_machine_support", {"basis": "CONFIGURED_SALES_RANGE"})
        for mid in a.machines:
            m.rel("SUPPORTS_MACHINE", ("Dealer", a.id), ("Machine", mid), "eu_dealer_machine_support", {"support_scope": "PARTS_AND_SERVICE" if {"PARTS", "SERVICE"} <= a.caps else ("SERVICE" if "SERVICE" in a.caps else "PARTS"),
                                                                                                     "basis": "CONFIGURED_MODEL_SUPPORT"})
    return actors


def build_service_centres(m: Model, dealers: list[Actor], geo: Geo) -> None:
    for a in dealers:
        if not ({"SERVICE", "FIELD_SERVICE", "WORKSHOP", "PREVENTIVE_MAINTENANCE"} & a.caps):
            continue
        sid = f"SVC-{a.id}"
        techs = 3 + stable_int("tech", a.id, mod=6) + (12 if a.tier == 1 else 5 if a.tier == 2 else 0)
        mobile = ("MOBILE_SERVICE" in a.caps)
        emergency = "EMERGENCY_SERVICE" in a.caps
        m.node("ServiceCentre", sid, node_props("eu_service_centres", sid, {
            "name": f"{a.id} Service Centre (demo)", "city": a.city, "country_code": a.cc, "service_centre_status": "ACTIVE_DEMO", "technicians_count": techs,
            "workshop_bays": (2 + stable_int("bays", a.id, mod=6)) if "WORKSHOP" in a.caps else 0, "mobile_service_units": (1 + stable_int("mob", a.id, mod=4)) if mobile else 0,
            "emergency_response_capability": emergency, "emergency_response_hours": pick([4, 8, 12], "emg", a.id) if emergency else None,
            "operating_hours": "24/7 on-call; workshop Mon-Fri 07:30-17:00" if emergency else "Mon-Fri 07:30-17:00",
            "service_priority": "PRIMARY" if a.tier == 1 else ("SECONDARY" if a.tier == 2 else "STANDARD"), "latitude": a.lat, "longitude": a.lon, "geo_basis": "APPROX_CITY_CENTRE",
            "machine_families_supported": [FAMILIES[f] for f in a.families]}))
        m.rel("HAS_SERVICE_CENTRE", ("Dealer", a.id), ("ServiceCentre", sid), "eu_service_centres")
        geo.place(("ServiceCentre", sid), a.cc, a.city)


def build_territories(m: Model, dealers: list[Actor], geo: Geo) -> None:
    """Explicit service/parts territories. Nothing is inferred from proximity: a dealer serves exactly the territories listed here."""
    postal_areas: set[str] = set()
    for a in dealers:
        if not ({"SERVICE", "PARTS", "FIELD_SERVICE"} & a.caps):
            if a.is_new:  # sales-only dealer: its territory is a sales territory in its home city
                m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("Location", geo.city(a.cc, a.city)), "eu_dealer_territories",
                      {"coverage_scope": "SALES", "basis": "CONFIGURED_TERRITORY", "service_priority": "PRIMARY", "territory_type": "CITY"}, ":CITY")
            continue
        scope = "SERVICE_AND_PARTS" if {"SERVICE", "PARTS"} <= a.caps else ("SERVICE" if "SERVICE" in a.caps else "PARTS")
        base = {"coverage_scope": scope, "basis": "CONFIGURED_TERRITORY", "service_priority": "PRIMARY"}
        m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("Location", geo.city(a.cc, a.city)), "eu_dealer_territories", {**base, "territory_type": "CITY"}, ":CITY")
        home = CITY[(a.cc, a.city)][0]
        m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("Region", geo.region(a.cc, home)), "eu_dealer_territories", {**base, "territory_type": "REGION"}, ":REGION")
        if a.tier <= 2:
            others = sorted({CITY[(a.cc, c)][0] for c in CITIES_BY_COUNTRY[a.cc]} - {home}, key=lambda r: stable_int("terr", a.id, r, mod=1000))
            for r in others[: (2 if a.tier == 1 else 1)]:
                m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("Region", geo.region(a.cc, r)), "eu_dealer_territories", {**base, "territory_type": "REGION", "service_priority": "SECONDARY"}, f":REGION:{slug(r)}")
        if a.tier == 1:
            m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("Location", geo.country(a.cc)), "eu_dealer_territories", {**base, "territory_type": "COUNTRY", "service_priority": "SECONDARY"}, ":COUNTRY")
        digits = "".join(ch for ch in a.postal_code if ch.isdigit())
        if a.is_new and a.cc in ("NL", "DE", "BE", "FR", "AT", "IT", "ES", "PL") and len(digits) >= 2 and stable_int("pa", a.id, mod=100) < 55:
            pid = f"PA-{a.cc}-{digits[:2]}"
            if pid not in postal_areas:
                postal_areas.add(pid)
                m.node("PostalArea", pid, node_props("eu_postal_areas", pid, {"country_code": a.cc, "postal_prefix": digits[:2], "name": f"{COUNTRIES[a.cc][0]} postal area {digits[:2]}"}))
                m.rel("IN_COUNTRY", ("PostalArea", pid), ("Location", geo.country(a.cc)), "eu_postal_areas")
            m.rel("SERVES_TERRITORY", ("Dealer", a.id), ("PostalArea", pid), "eu_dealer_territories", {**base, "territory_type": "POSTAL_AREA"}, ":POSTAL_AREA")


def build_suppliers(m: Model, ex: Existing, geo: Geo, parts: list[dict[str, Any]]) -> list[Actor]:
    cats = {c: cid for cid, c in {"CAT-01": "Hydraulics", "CAT-02": "Drivetrain", "CAT-03": "Electrical", "CAT-04": "Structural", "CAT-05": "Filtration", "CAT-06": "Brakes",
                                  "CAT-07": "Cooling", "CAT-08": "Cab & Controls", "CAT-09": "Attachments", "CAT-10": "Lubrication"}.items()}
    actors: list[Actor] = []
    seq = 12
    taken: dict[str, set[str]] = {}
    for s in ex.suppliers:
        taken.setdefault(s["cc"], set()).add(s["city"])
        _, lat, lon = CITY[(s["cc"], s["city"])]
        actors.append(Actor(s["id"], s["cc"], s["city"], lat, lon, "supplier", is_new=False))
        geo.place(("Supplier", s["id"]), s["cc"], s["city"])
    for cc, n in SUPPLIER_PLAN:
        for i in range(n):
            seq += 1
            sid = f"SUP-{seq:03d}"
            city = next_city(cc, {}, taken.setdefault(cc, set()))
            taken[cc].add(city)
            specs = list(dict.fromkeys([SPECIALISATIONS[(seq * 5 + i * 3) % len(SPECIALISATIONS)], SPECIALISATIONS[(seq * 7 + 2) % len(SPECIALISATIONS)]][: 1 + stable_int("nspec", sid, mod=2)]))
            lat, lon = jitter(cc, city, sid)
            a = Actor(sid, cc, city, lat, lon, "supplier", extra={"specialisations": specs})
            categories = sorted({c for sp in specs for c in SPEC_CATEGORIES[sp]})
            name = f"{pick(__import__('names').BRAND_WORDS, 'sup', sid)} {__import__('names').SUPPLIER_TRADE[specs[0]]} {__import__('names').LEGAL[cc]} (demo)"
            lead = pick(["FAST", "STANDARD", "STANDARD", "EXTENDED"], "lead", sid)
            stype = "COMPONENT_MANUFACTURER" if stable_int("st", sid, mod=100) < 65 else "DISTRIBUTOR"
            m.node("Supplier", sid, node_props("eu_suppliers", sid, {
                "name": name, "city": city, "country_code": cc, "supplier_code": f"SUP-{cc}-{seq:03d}", "supplier_type": stype, "supplier_status": "ACTIVE_DEMO", "lead_time_class": lead,
                "specialisations": specs, "capabilities": [pick(["CNC machining", "Hydraulic assembly", "Forging and casting", "Surface treatment", "Electronics assembly", "Kitting and packing"], "capab", sid, k) for k in range(2)],
                "categories_supplied": "|".join(cats[c] for c in categories), "payment_terms_days": pick([30, 45, 60], "pay", sid), "latitude": lat, "longitude": lon, "geo_basis": "APPROX_CITY_CENTRE",
                "phone": phone(cc, sid), "email": f"sales@{slug(name.replace('(demo)', ''))[:24]}.example"}))
            a.postal_code = geo.address(("Supplier", sid), "SUPPLIER", cc, city, "supplier", sid)
            geo.place(("Supplier", sid), cc, city)
            for c in categories:
                m.rel("SUPPLIES_CATEGORY", ("Supplier", sid), ("Category", cats[c]), "eu_suppliers", {"basis": "SPECIALISATION"})
            for k in range(1 + stable_int("nc", sid, mod=2)):
                cid = f"SCT-{sid}-{k + 1:02d}"
                pn, role = person("supplier", cc, sid, k)
                m.node("SupplierContact", cid, node_props("eu_supplier_contacts", cid, {"name": pn, "contact_role": role, "email": email(pn, name), "phone": phone(cc, sid, k), "contact_status": "ACTIVE_DEMO"}))
                m.rel("HAS_CONTACT", ("Supplier", sid), ("SupplierContact", cid), "eu_supplier_contacts")
            actors.append(a)
    return actors


def weighted_industry(cc: str, key: str) -> str:
    w = {i: 6 for i in INDUSTRIES}
    boosts = {"construction": ["DE", "FR", "IT", "ES", "PL", "NL", "BE", "AT", "CZ", "SE"], "quarrying": ["DE", "FR", "PL", "ES", "IT", "AT", "CZ", "IE"],
             "aggregates": ["DE", "FR", "PL", "NL", "BE", "SE", "DK"], "logistics": ["NL", "DE", "BE", "PL", "FR"], "warehousing": ["NL", "DE", "BE", "PL", "CZ"],
             "manufacturing": ["DE", "IT", "PL", "CZ", "AT", "SK", "HU"], "agriculture": ["FR", "PL", "IE", "ES", "RO", "HU", "DK", "NL"], "ports": ["NL", "BE", "DE", "ES", "IT", "GR", "PL", "DK", "SE"],
             "recycling": ["NL", "DE", "BE", "AT", "SE"], "infrastructure": ["DE", "FR", "ES", "PL", "RO", "BG", "HR"], "utilities": ["FR", "DE", "SE", "FI", "DK"],
             "industrial processing": ["DE", "IT", "NL", "BE", "CZ"], "material handling": ["DE", "NL", "IT", "PL", "AT"]}
    for ind, countries in boosts.items():
        if cc in countries:
            w[ind] += 10
    total = sum(w.values())
    pointer = stable_int("ind", key, mod=total)
    for ind in INDUSTRIES:
        if pointer < w[ind]:
            return ind
        pointer -= w[ind]
    return INDUSTRIES[0]


SITE_TYPES = {"construction": ["Project Site", "Main Yard", "Site Depot"], "quarrying": ["Quarry Site", "Plant Yard"], "aggregates": ["Quarry Site", "Terminal Yard"],
              "logistics": ["Distribution Centre", "Cross-Dock", "Main Yard"], "warehousing": ["Warehouse", "Distribution Centre"], "manufacturing": ["Plant", "Works Dock"],
              "agriculture": ["Farm Yard", "Storage Site"], "ports": ["Terminal", "Quay Yard"], "recycling": ["Recycling Yard", "Sorting Plant"], "infrastructure": ["Project Site", "Depot"],
              "utilities": ["Depot", "Works Yard"], "industrial processing": ["Plant", "Process Hall"], "material handling": ["Workshop", "Main Yard"]}
LOADING = ["FORKLIFT", "LOADING_DOCK", "TAIL_LIFT_ACCESS", "CRANE", "RAMP", "GROUND_LEVEL_ONLY"]
RESTRICTIONS = ["NONE", "MAX_VEHICLE_LENGTH_12M", "LOW_EMISSION_ZONE", "NO_WEEKEND_DELIVERY", "MAX_WEIGHT_18T", "APPOINTMENT_REQUIRED", "NONE", "NONE"]


def build_customers(m: Model, ex: Existing, geo: Geo, existing_shiptos: list[dict[str, Any]]) -> list[Actor]:
    actors: list[Actor] = []
    for c in ex.customers:  # existing customers: industry by name keyword (a labelled, derived assignment); relationships only
        ind = existing_industry(c["name"])
        m.rel("IN_INDUSTRY", ("Customer", c["id"]), ("Industry", f"IND-{slug(ind).upper()}"), "eu_customer_industries", {"basis": "NAME_KEYWORD_ASSIGNMENT"})
        geo.place(("Customer", c["id"]), c["cc"], c["city"])
    seq, shipto_seq = 10, 0
    for cc in sorted(CUSTOMER_TARGET, key=lambda x: (-CUSTOMER_TARGET[x], x)):
        for i in range(CUSTOMER_TARGET[cc]):
            seq += 1
            cid = f"CUS-{seq:03d}"
            cities = CITIES_BY_COUNTRY[cc]
            city = cities[stable_int("ccity", cid, mod=len(cities))]
            ind = weighted_industry(cc, cid)
            lat, lon = jitter(cc, city, cid)
            word = pick(__import__("names").CUSTOMER_WORDS, "cw", cid)
            sector = pick(__import__("names").CUSTOMER_SECTOR[ind], "cs", cid)
            name = f"{word} {sector} {__import__('names').LEGAL[cc]} (demo)"
            a = Actor(cid, cc, city, lat, lon, "customer", extra={"industry": ind})
            # No customer master: the customer is whoever places the order. `cid`/`name` only name and place the destination sites below.
            nship = 1 + (0 if stable_int("ns", cid, mod=100) < 35 else 1 if stable_int("ns", cid, mod=100) < 75 else 2)
            for k in range(nship):
                shipto_seq += 1
                sid = f"SHT-{seq:03d}-{k + 1}"
                scity = city if k == 0 and stable_int("sc", cid, mod=100) < 50 else cities[stable_int("scity", cid, k, mod=len(cities))]
                slat, slon = jitter(cc, scity, sid)
                site = pick(SITE_TYPES[ind], "site", sid)
                m.node("ShipTo", sid, node_props("eu_ship_tos", sid, {
                    "name": f"{name.replace(' (demo)', '')} - {site} (demo)", "shipto_code": sid, "street_address": street(cc, "shipto", sid), "postal_code": postal(cc, "shipto", sid), "city": scity,
                    "country_code": cc, "state_region": CITY[(cc, scity)][0], "latitude": slat, "longitude": slon, "geo_basis": "APPROX_CITY_CENTRE", "is_default": k == 0, "shipto_status": "ACTIVE_DEMO",
                    "receiving_hours": pick(["Mon-Fri 07:00-16:00", "Mon-Fri 06:00-14:00", "Mon-Fri 08:00-17:00", "Mon-Sat 07:00-15:00"], "rh", sid),
                    "loading_capability": sorted({pick(LOADING, "ld", sid, j) for j in range(2)}), "vehicle_restrictions": pick(RESTRICTIONS, "vr", sid),
                    "address_note": "Synthetic address; street, number and postal code are invented"}))
                geo.place(("ShipTo", sid), cc, scity)
                m.rel("IN_REGION", ("ShipTo", sid), ("Region", geo.region(cc, CITY[(cc, scity)][0])), "eu_ship_tos")
            actors.append(a)
    for st in existing_shiptos:  # existing ship-tos: place them in a city and region (relationships only)
        geo.place(("ShipTo", st["id"]), st["cc"], st["city"])
        m.rel("IN_REGION", ("ShipTo", st["id"]), ("Region", geo.region(st["cc"], CITY[(st["cc"], st["city"])][0])), "eu_ship_tos")
    return actors
