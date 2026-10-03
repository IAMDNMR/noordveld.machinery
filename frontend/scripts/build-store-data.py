"""Generates src/data/store.generated.ts (the Parts Store data) from the complete Noordveld workbook.

Run: npm run data:store   (requires: pip install openpyxl)
Reads backend/data/processed/noordveld-complete-dataset-synthetic-demo.xlsx (backend master data; temporary until the store reads the backend API). Nothing is invented here: the whole workbook is a
synthetic demo (prices, stock, delivery, compliance); the catalogue sheets carry fitment, which the store never extends.
"""
import json
from collections import defaultdict
from pathlib import Path
import openpyxl

root = Path(__file__).resolve().parent.parent
wb = openpyxl.load_workbook(root.parent / "backend" / "data" / "processed" / "noordveld-complete-dataset-synthetic-demo.xlsx", data_only=True)


def rows(sheet):
    data = list(wb[sheet].iter_rows(values_only=True))
    head = [str(h).strip() for h in data[0]]
    return [dict(zip(head, r)) for r in data[1:] if any(c is not None for c in r)]


def clean(v):
    """The workbook marks absent values as NOT_STATED / NOT_CONFIGURED; the store treats them as empty."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("NOT_STATED", "NOT_CONFIGURED") else s


def num(v, digits=2):
    return round(float(v), digits)


catalog = {r["part_id"]: r for r in rows("SYN_part_catalog")}
parts_raw = {r["part_id"]: r for r in rows("parts")}
machines = {r["machine_id"]: r for r in rows("machines")}

fits = defaultdict(list)
for r in rows("machine_part_fitment"):
    model = machines[r["machine_id"]]["model_code"]
    if model not in fits[r["part_id"]]:
        fits[r["part_id"]].append(model)

specs, notes = defaultdict(list), defaultdict(list)
spec_note = {}
for r in rows("part_specifications"):
    group = r["specification_group"]
    if group == "Source note (verbatim)":
        spec_note[r["part_id"]] = clean(r["value"])
    elif group == "Descriptive (source text)":
        notes[r["part_id"]].append(clean(r["value"]))
    else:
        name = clean(r["specification_name"]).replace("Dimension (role not stated)", "Size")
        specs[r["part_id"]].append({"group": group, "name": name, "value": clean(r["value"]), "unit": clean(r["unit"])})

warehouses = rows("SYN_warehouses")
wh_ids = [w["warehouse_id"] for w in warehouses]
stock = defaultdict(dict)
dealers = defaultdict(int)
for r in rows("SYN_inventory"):
    if r["location_type"] == "WAREHOUSE":
        stock[r["part_id"]][r["location_id"]] = int(r["available"])
    elif int(r["available"]) > 0:
        dealers[r["part_id"]] += 1

compliance_sheet = {r["compliance_id"]: r for r in rows("SYN_compliance")}
part_compliance = defaultdict(list)
for r in rows("SYN_part_compliance"):
    part_compliance[r["part_id"]].append(r["compliance_id"])

related = defaultdict(list)
for r in rows("SYN_part_relationships"):
    related[r["from_part_id"]].append({"id": r["to_part_id"], "kind": "together"})
    related[r["to_part_id"]].append({"id": r["from_part_id"], "kind": "together"})
for r in rows("part_relationships"):
    related[r["from_part_id"]].append({"id": r["to_part_id"], "kind": "family"})
    related[r["to_part_id"]].append({"id": r["from_part_id"], "kind": "family"})


def dedupe(items):
    seen, out = set(), []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            out.append(it)
    return out


variants = defaultdict(list)
for r in rows("SYN_machine_variants"):
    variants[r["machine_id"]].append({"name": r["variant_name"], "from": r["serial_from"], "to": r["serial_to"], "id": r["variant_id"]})
ident = defaultdict(list)
for r in rows("SYN_identification_requirements"):
    allowed = set(str(r["fits_variant_ids"] or "").split("|"))
    ident[r["part_id"]].append(
        {
            "model": r["model_code"],
            "variants": [{"name": v["name"], "from": v["from"], "to": v["to"]} for v in variants[r["machine_id"]] if v["id"] in allowed],
        }
    )

backorders = {r["part_id"]: {"qty": int(r["quantity_on_order"]), "days": int(r["expected_restock_days"])} for r in rows("SYN_supplier_backorders")}

aliases = defaultdict(list)
for r in rows("SYN_search_aliases"):
    if r["entity_type"] == "PART":
        aliases[r["entity_id"]].append(str(r["alias"]))

out_parts = []
for pid, c in catalog.items():
    p = parts_raw[pid]
    out_parts.append(
        {
            "id": pid,
            "no": c["unified_part_number"],
            "name": c["display_name"],
            "desc": clean(c["short_description"]),
            "category": p["part_category"],
            "categoryId": p["category_id"],
            "subcategory": clean(p["part_subcategory"]),
            "type": clean(c["part_type"]),
            "legacyNo": clean(p["legacy_part_number"]),
            "legacyBusiness": clean(p["legacy_business_unit"]),
            "plant": clean(p["origin_plant"]),
            "brand": clean(p["brand"]),
            "status": c["part_status"],
            "statusReason": clean(c["status_reason"]),
            "orderable": str(c["orderable"]).upper() == "TRUE",
            "availability": c["availability_state"],
            "price": num(c["list_price_ex_vat"]),
            "weightKg": num(c["weight_kg"], 1),
            "warrantyMonths": int(c["warranty_months"]),
            "returnDays": int(c["return_window_days"]),
            "specNote": spec_note.get(pid, ""),
            "specs": specs[pid],
            "notes": [n for n in notes[pid] if n],
            "fits": fits[pid],
            "stock": {w: stock[pid].get(w, 0) for w in wh_ids},
            "dealers": dealers[pid],
            "compliance": part_compliance[pid],
            "related": dedupe(related[pid]),
            "ident": ident[pid],
            "backorder": backorders.get(pid),
            "aliases": sorted(set(a for a in aliases[pid] if a.lower() != c["unified_part_number"].lower())),
        }
    )

categories = []
sub_rows = [r for r in rows("categories") if str(r["level"]) == "2"]
for r in rows("categories"):
    if str(r["level"]) != "1":
        continue
    subs = [{"id": s["category_id"], "name": s["category_name"], "count": int(s["part_count"])} for s in sub_rows if s["parent_category"] == r["category_name"]]
    categories.append({"id": r["category_id"], "name": r["category_name"], "count": int(r["part_count"]), "subs": subs})

countries, seen = [], set()
for r in rows("SYN_countries_regions"):
    if r["country_code"] not in seen:
        seen.add(r["country_code"])
        countries.append({"code": r["country_code"], "name": r["country"], "vat": float(r["vat_rate_demo"])})

store = {
    "warehouses": [{"id": w["warehouse_id"], "name": str(w["warehouse_name"]).replace(" (demo)", ""), "city": w["city"], "country": w["country"]} for w in warehouses],
    "categories": categories,
    "compliance": {
        k: {"requirement": str(v["requirement"]).replace(" (demo)", ""), "standard": str(v["standard"]).replace(" (demo)", ""), "certification": v["certification"], "status": v["certificate_status"], "validUntil": str(v["valid_until"])[:10]}
        for k, v in compliance_sheet.items()
    },
    "shippingRates": [
        {"band": r["distance_band"], "fromKm": int(r["from_km"]), "toKm": int(r["to_km"]), "method": r["method"], "price": float(r["price_ex_vat"]), "days": int(r["transit_days"])}
        for r in rows("SYN_shipping_rates")
    ],
    "countries": countries,
}

out = "// GENERATED by scripts/build-store-data.py from backend/data/processed/noordveld-complete-dataset-synthetic-demo.xlsx. Do not edit by hand.\n"
out += "// Everything here is demonstration data: prices, stock, delivery and compliance are synthetic.\n\n"
out += "import type { StoreCategory, StoreCountry, StoreWarehouse, StoreCompliance, StoreShippingRate, StorePartRaw } from '../types/store'\n\n"
for name, typ in (("storeWarehouses", "readonly StoreWarehouse[]"), ("storeCategories", "readonly StoreCategory[]"), ("storeCompliance", "Record<string, StoreCompliance>"), ("storeShippingRates", "readonly StoreShippingRate[]"), ("storeCountries", "readonly StoreCountry[]")):
    key = {"storeWarehouses": "warehouses", "storeCategories": "categories", "storeCompliance": "compliance", "storeShippingRates": "shippingRates", "storeCountries": "countries"}[name]
    out += f"export const {name}: {typ} = " + json.dumps(store[key], ensure_ascii=False) + "\n\n"
out += "export const storeParts: readonly StorePartRaw[] = " + json.dumps(out_parts, ensure_ascii=False) + "\n"
(root / "src" / "data" / "store.generated.ts").write_text(out, encoding="utf-8")
print(f"{len(out_parts)} parts, {len(categories)} categories, {sum(len(c['subs']) for c in categories)} subcategories")
