"""Generates agentic-commerce/src/components/launch/launchData.ts: the handful of real dataset records the launch film shows.

Run: python scripts/build-film-data.py   (requires: pip install openpyxl)
Reads backend/data/processed/noordveld-complete-dataset-synthetic-demo.xlsx (backend master data; temporary until the film reads the backend API). Nothing is invented: every name, number, distance, price and
stock level in the film comes from a row of the workbook. The workbook's supply-side sheets (SYN_*) are synthetic demo data.
"""
import json
from pathlib import Path
import openpyxl

root = Path(__file__).resolve().parent.parent
wb = openpyxl.load_workbook(root.parent / "backend" / "data" / "processed" / "noordveld-complete-dataset-synthetic-demo.xlsx", read_only=True, data_only=True)


def rows(name):
    data = list(wb[name].iter_rows(values_only=True))
    head = data[0]
    return [dict(zip(head, r)) for r in data[1:] if any(c is not None for c in r)]


def clean(v):
    s = "" if v is None else str(v).strip()
    return "" if s in ("NOT_STATED", "NOT_CONFIGURED") else s


# The story: a customer in Eindhoven. The nearest warehouse holding the part ships it; a dealer in the same city also holds it.
MODEL, PART, CUSTOMER = "NV-4500", "PRT-002", "CUS-008"

machine = next(r for r in rows("machines") if r["model_code"] == MODEL)
fits = [r for r in rows("machine_part_fitment") if r["model_code"] == MODEL]
part = next(r for r in rows("parts") if r["part_id"] == PART)
catalog = next(r for r in rows("SYN_part_catalog") if r["part_id"] == PART)
legacy = next(r for r in rows("legacy_part_mapping") if r["current_part_id"] == PART)
spec_note = next((clean(r["value"]) for r in rows("part_specifications") if r["part_id"] == PART and r["specification_group"] == "Source note (verbatim)"), "")
supplier_link = next(r for r in rows("SYN_part_supplier") if r["part_id"] == PART and str(r["is_primary"]).upper() == "TRUE")
supplier = next(r for r in rows("SYN_suppliers") if r["supplier_id"] == supplier_link["supplier_id"])
warehouses = {r["warehouse_id"]: r for r in rows("SYN_warehouses")}
dealers = {r["dealer_id"]: r for r in rows("SYN_dealers")}
customer = next(r for r in rows("SYN_customers") if r["customer_id"] == CUSTOMER)
inventory = [r for r in rows("SYN_inventory") if r["part_id"] == PART]
stocked = {r["location_id"] for r in inventory if int(r["available"]) > 0}
option = min((r for r in rows("SYN_delivery_options") if r["to_id"] == CUSTOMER and r["from_warehouse_id"] in stocked), key=lambda r: float(r["est_road_km"]))
WAREHOUSE = option["from_warehouse_id"]
rates = {(r["distance_band"], r["method"]): r for r in rows("SYN_shipping_rates")}
price = next(r for r in rows("SYN_pricing") if r["part_id"] == PART)
services = [r for r in rows("SYN_services") if r["machine_id"] == machine["machine_id"]]
service_ids = {s["service_id"] for s in services}
service_parts = {r["service_id"] for r in rows("SYN_service_parts") if r["part_id"] == PART and r["service_id"] in service_ids}
catalog_by_id = {r["part_id"]: r for r in rows("SYN_part_catalog")}
legacy_by_id = {r["current_part_id"]: r for r in rows("legacy_part_mapping")}
fitted_ids = {f["part_id"] for f in fits}
in_stock = sum(1 for i in fitted_ids if catalog_by_id[i]["availability_state"] == "IN_STOCK")
legacy_mapped = sum(1 for i in fitted_ids if clean(legacy_by_id[i]["legacy_part_number"]))


def node(r, kind, ident):
    return {"id": r[ident], "kind": kind, "name": str(r["name" if "name" in r else f"{kind}_name"]).replace(" (demo)", ""), "city": r["city"], "lat": float(r["latitude"]), "lon": float(r["longitude"])}


stock_nodes = []
for r in inventory:
    loc = r["location_id"]
    if loc in warehouses:
        w = warehouses[loc]
        stock_nodes.append({"id": loc, "kind": "warehouse", "name": str(w["warehouse_name"]).replace(" (demo)", ""), "city": w["city"], "lat": float(w["latitude"]), "lon": float(w["longitude"]), "available": int(r["available"]), "pickup": str(w["pickup_allowed"]).upper() == "TRUE"})
    elif loc in dealers:
        d = dealers[loc]
        stock_nodes.append({"id": loc, "kind": "dealer", "name": str(d["dealer_name"]).replace(" (demo)", ""), "city": d["city"], "lat": float(d["latitude"]), "lon": float(d["longitude"]), "available": int(r["available"]), "pickup": str(d["pickup_allowed"]).upper() == "TRUE"})

siblings = []
for f in fits:
    p = next(x for x in rows("parts") if x["part_id"] == f["part_id"])
    if p["part_category"] == part["part_category"]:
        siblings.append({"no": p["unified_part_number"], "name": p["part_name"]})

band_rate = lambda m: rates[(next(b for b in ("LOCAL", "REGIONAL", "NATIONAL", "LONG_DISTANCE") if rates[(b, m)]["from_km"] <= option["est_road_km"] < rates[(b, m)]["to_km"]), m)]

out = {
    "counts": {"machines": len(rows("machines")), "parts": len(rows("parts")), "fitments": len(rows("machine_part_fitment")), "specifications": len(rows("part_specifications"))},
    "machine": {"model": MODEL, "name": machine["machine_name"], "type": machine["machine_type"], "plant": machine["origin_plant"], "country": machine["country"], "partsFitted": len(fits), "inStock": in_stock, "legacyMapped": legacy_mapped, "slug": MODEL.lower(), "services": [s["service_name"].replace(" (demo)", "") for s in services], "serviceInterval": [s["interval_hours"] for s in services]},
    "part": {
        "id": PART, "no": part["unified_part_number"], "name": part["part_name"], "category": part["part_category"], "subcategory": clean(part["part_subcategory"]),
        "legacyNo": legacy["legacy_part_number"], "legacyBusiness": clean(legacy["legacy_business"]), "plant": part["origin_plant"],
        "fits": [m.strip() for m in str(part["compatible_models_source"]).split(",")], "specNote": spec_note,
        "priceExVat": float(price["list_price_ex_vat"]), "weightKg": float(catalog["weight_kg"]), "status": catalog["part_status"], "availability": catalog["availability_state"],
        "usedInService": bool(service_parts),
    },
    "siblings": siblings[:6],
    "supplier": {"id": supplier["supplier_id"], "name": str(supplier["supplier_name"]).replace(" (demo)", ""), "city": supplier["city"], "lat": float(supplier["latitude"]), "lon": float(supplier["longitude"]), "leadDays": int(supplier_link["lead_time_days"]), "partNo": supplier_link["supplier_part_number"]},
    "stock": stock_nodes,
    "customer": {"id": customer["customer_id"], "name": str(customer["customer_name"]).replace(" (demo)", ""), "city": customer["city"], "lat": float(customer["latitude"]), "lon": float(customer["longitude"])},
    "pickupDealer": next((r["location_id"] for r in inventory if r["location_id"] in dealers and dealers[r["location_id"]]["city"] == customer["city"] and int(r["available"]) > 0 and str(dealers[r["location_id"]]["pickup_allowed"]).upper() == "TRUE"), None),
    "delivery": {"from": WAREHOUSE, "km": float(option["est_road_km"]), "standard": {"price": float(option["standard_price_ex_vat"]), "days": int(option["standard_days"])}, "express": {"price": float(option["express_price_ex_vat"]), "days": int(option["express_days"])}},
}

text = "// GENERATED by scripts/build-film-data.py from backend/data/processed/noordveld-complete-dataset-synthetic-demo.xlsx. Do not edit by hand.\n"
text += "// Every value is a row of the workbook. Supply-side records (suppliers, dealers, stock, prices, delivery) are synthetic demo data.\n\n"
text += "export const filmData = " + json.dumps(out, indent=2, ensure_ascii=False) + " as const\n"
target = root / "agentic-commerce" / "src" / "components" / "launch" / "launchData.ts"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(text, encoding="utf-8")
print("ok", len(text))
