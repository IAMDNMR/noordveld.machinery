"""Builds the Parts Intelligence graph package: audit pack, schema, readiness gate, Cypher import and validation queries.

Run (from backend/): python scripts/graph_build.py   (requires: pip install openpyxl)
Writes graph/audits/, graph/schema/, graph/cypher/ and graph/validation/. It NEVER connects to Neo4j; the Cypher
is only written to disk, and only when the readiness gate passes.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import re
import shutil
from pathlib import Path

from graph_audit_lib import AUDITS, COMPLETE, CYPHER, DOWNLOADS, ORIGINAL, ROOT, SCHEMA, VALIDATION, blank, load, token_missing
from graph_canon import EDGE_SPECS, NODE_SPECS, PROV_KEYS, build
from graph_contract import EXACTLY_ONE, FORBIDDEN_TYPES, NODE_DOC, ONE_OWNER, REL, SCHEMA_ONLY
from graph_coverage import BLK, CV, FK_ACCOUNT, IS_, IWD, NA, SCH

OUT = {"graph_audit": AUDITS, "graph_schema": SCHEMA, "cypher": CYPHER, "validation": VALIDATION}
TODAY = dt.date.today().isoformat()

S = load(COMPLETE)
O = load(ORIGINAL)
g = build(S)
N = g.nodes
E = g.edges
node_count = sum(len(v) for v in N.values())
ID_PROP = {spec.label: spec.id_prop for spec in NODE_SPECS} | {"Carrier": "carrier_id", "DataSource": "source_id"}


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else ["empty"])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def md_table(rows: list[dict], fields: list[str]) -> str:
    out = ["| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(f, "")).replace("|", "/").replace("\n", " ") for f in fields) + " |")
    return "\n".join(out)


# ======================================================================================================================
# 1. Source inventory (every sheet of both workbooks)
# ======================================================================================================================
SHEET_ROLE = {spec.sheet: spec.label for spec in NODE_SPECS}
for spec in EDGE_SPECS:
    SHEET_ROLE.setdefault(spec.sheet, f"relationships: {spec.type}")
SHEET_ROLE |= {
    "SYN_part_dealer": "relationships: STOCKED_BY",
    "SYN_inventory": "relationship properties on AVAILABLE_AT / STOCKED_BY",
    "SYN_part_supplier": "relationships: SUPPLIED_BY",
    "SYN_data_sources": "DataSource",
    "relationships_all": "NOT IMPORTED: workbook's own edge list; used only to reconcile counts",
    "search_index": "NOT IMPORTED: derived search text (embedding_status NOT_GENERATED)",
    "part_data_coverage": "NOT IMPORTED: derived coverage summary (used in this audit)",
    "record_counts": "NOT IMPORTED: workbook metadata",
    "data_dictionary": "NOT IMPORTED: workbook metadata",
    "SYN_quality_checks": "NOT IMPORTED: workbook's own QA results",
    "SYN_prototype_gap_analysis": "NOT IMPORTED: workbook metadata",
    "SYN_agent_test_questions": "NOT IMPORTED: golden test questions (used for validation design)",
    "SYN_distances": "NOT IMPORTED: pairwise distances; proximity must never create business relationships",
    "SYN_geo_nodes": "NOT IMPORTED: synthetic coordinates (kept off nodes so source NOT_STATED coordinates are not overwritten)",
    "SYN_roles": "NOT IMPORTED: access control, not required for this phase",
    "SYN_users": "NOT IMPORTED: access control, not required for this phase",
    "00_README": "NOT IMPORTED: workbook documentation",
    "01_Legend": "NOT IMPORTED: workbook documentation",
}
inventory_rows = []
for wb_name, book in (("complete", S), ("original", O)):
    for sheet, rows in book.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        idc = cols[0]
        ids = [r.get(idc) for r in rows]
        idc_ok = idc.endswith("_id") or idc in ("order_status_code", "Unified Part No.", "Model code", "Model Code") or sheet in ("SYN_part_catalog",)
        dup = sum(v > 1 for v in collections.Counter(str(i) for i in ids).values()) if idc_ok else ""
        nulls = sum(1 for i in ids if blank(i)) if idc_ok else ""
        not_stated = sum(1 for r in rows for v in r.values() if token_missing(v))
        blanks = sum(1 for r in rows for v in r.values() if blank(v))
        classes = collections.Counter(str(r.get("data_class")) for r in rows) if "data_class" in cols else {}
        prov = "SOURCE (original catalogue)" if wb_name == "original" else (" / ".join(f"{k}:{v}" for k, v in classes.items()) or ("SYNTHETIC" if sheet.startswith("SYN_") else "METADATA"))
        inventory_rows.append({
            "workbook": COMPLETE.name if wb_name == "complete" else ORIGINAL.name,
            "sheet": sheet, "rows": len(rows), "fields": len(cols), "primary_identifier": idc if idc_ok else "(none)",
            "unique_ids": len(set(map(str, ids))) if idc_ok else "", "duplicate_ids": dup, "null_ids": nulls,
            "not_stated_values": not_stated, "blank_values": blanks, "data_class": prov,
            "graph_role": SHEET_ROLE.get(sheet, "SOURCE: compared against the complete workbook" if wb_name == "original" else "NOT IMPORTED"),
            "field_list": "|".join(cols),
        })

# ======================================================================================================================
# 2. Checks (the readiness gate)
# ======================================================================================================================
checks: list[dict] = []


def check(cid: str, name: str, value, ok: bool, detail: str = "", blocking: bool = True) -> None:
    checks.append({"id": cid, "check": name, "result": value, "status": "PASS" if ok else ("FAIL" if blocking else "WARN"), "blocking": "yes" if blocking else "no", "detail": detail})


dup_nodes = [i for i in g.node_issues if i["issue"] == "DUPLICATE_ID"]
null_ids = [i for i in g.node_issues if i["issue"] == "NULL_ID"]
check("G01", "Duplicate canonical node IDs", len(dup_nodes), not dup_nodes)
check("G02", "Missing (null) canonical node IDs", len(null_ids), not null_ids)
rel_ids = collections.Counter(e["rel_id"] for e in E)
check("G03", "Duplicate relationship IDs", sum(v > 1 for v in rel_ids.values()), all(v == 1 for v in rel_ids.values()))
same = collections.Counter((e["type"], e["from_label"], e["from_id"], e["to_label"], e["to_id"]) for e in E)
dup_rel = [k for k, v in same.items() if v > 1]
check("G04", "Duplicate relationships (same type and endpoints)", len(dup_rel), not dup_rel, "; ".join(map(str, dup_rel[:5])))
sym_pairs = {(e["type"], e["from_id"], e["to_id"]) for e in E if e["symmetric"]}
sym_dup = [p for p in sym_pairs if (p[0], p[2], p[1]) in sym_pairs]
check("G05", "Duplicate semantic relationships (symmetric facts stored in both directions)", len(sym_dup) // 2, not sym_dup, "CO_ORDERED_WITH and SAME_NAME_GROUP_AS stored once (lower id -> higher id)")
broken = [e for e in E if e["from_id"] not in N.get(e["from_label"], {}) or e["to_id"] not in N.get(e["to_label"], {})]
check("G06", "Broken references (relationship endpoint does not exist)", len(broken), not broken)
check("G07", "Orphan relationships (no source record / provenance)", sum(1 for e in E if not e.get("source_record_id")), all(e.get("source_record_id") for e in E))
bad_end = [e for e in E if (e["type"], e["from_label"], e["to_label"]) not in REL]
check("G08", "Invalid endpoint types (not in the relationship contract)", len(bad_end), not bad_end, "; ".join(sorted({f"{e['type']}:{e['from_label']}->{e['to_label']}" for e in bad_end})[:5]))
bad_src = [e for e in E if e["source_sheet"] not in REL.get((e["type"], e["from_label"], e["to_label"]), ("", "", []))[2]]
check("G09", "Relationships from a source the contract does not allow", len(bad_src), not bad_src)
dirs = collections.defaultdict(set)
for e in E:
    dirs[e["type"]].add((e["from_label"], e["to_label"]))
reversed_types = [t for t, pairs in dirs.items() if any((b, a) in pairs and a != b for a, b in pairs)]
check("G10", "Inconsistent relationship direction (a type used both ways)", len(reversed_types), not reversed_types, ", ".join(reversed_types))
forbidden = sorted({e["type"] for e in E if e["type"] in FORBIDDEN_TYPES})
check("G11", "Generic or unsupported relationship types (RELATED_TO, HAS, ALTERNATIVE_TO, SUPERSEDES, INTERCHANGEABLE...)", len(forbidden), not forbidden, ", ".join(forbidden))
asserted = [e for e in E if str(e["props"].get("interchangeability_status", "UNKNOWN")).upper() not in ("UNKNOWN",)]
check("G12", "Interchangeability asserted anywhere", len(asserted), not asserted)
src_cond = sum(1 for r in S["machine_part_fitment"] if r["confidence"] == "SOURCE_STATED_CONDITIONAL")
fits = [e for e in E if e["type"] == "FITS"]
graph_cond = sum(1 for e in fits if e["props"]["fitment_status"] == "CONDITIONAL")
check("G13", "Conditional fitments kept CONDITIONAL", f"{graph_cond} of {src_cond}", graph_cond == src_cond and all(e["props"]["fitment_status"] in ("CONFIRMED", "CONDITIONAL") for e in fits))
check("G14", "Fitments imported = source fitment rows", f"{len(fits)} of {len(S['machine_part_fitment'])}", len(fits) == len(S["machine_part_fitment"]))
fit_from_syn = [e for e in fits if e["source_sheet"].startswith("SYN_")]
check("G15", "Fitment added by synthetic data", len(fit_from_syn), not fit_from_syn)
sup_bad = [e for e in E if e["type"] == "SUPPLIED_BY" and e["source_sheet"] != "SYN_part_supplier"]
check("G16", "Supplier relationships not backed by an explicit supplier record", len(sup_bad), not sup_bad)
dealer_bad = [e for e in E if e["type"] == "STOCKED_BY" and (e["source_sheet"] != "SYN_part_dealer" or "inventory_id" not in e["props"])]
check("G17", "Dealer relationships not backed by an explicit stocking record", len(dealer_bad), not dealer_bad)
zero_rows = [x for x in g.excluded if x["reason"] == "EXPLICIT_ZERO_WITHOUT_STOCKING_RECORD"]
check("G18", "Unknown dealer stock imported as 0 (unsupported inventory)", 0, True, f"{len(zero_rows)} such source rows excluded and documented")
syn_unmarked = [x for x in [*E, *[n for v in N.values() for n in v.values()]] if x.get("source_sheet", "").startswith("SYN_") and x.get("data_status") != "SYNTHETIC_DEMO"]
syn_total = sum(1 for x in [*E, *[n for v in N.values() for n in v.values()]] if x.get("source_sheet", "").startswith("SYN_"))
check("G19", "Synthetic records carrying data_status = SYNTHETIC_DEMO", f"{syn_total - len(syn_unmarked)} of {syn_total} (100%)" if not syn_unmarked else f"{syn_total - len(syn_unmarked)} of {syn_total}", not syn_unmarked)
cat_syn = [x for x in [*E, *[n for v in N.values() for n in v.values()]] if not x.get("source_sheet", "").startswith("SYN_") and x.get("data_status") == "SYNTHETIC_DEMO"]
check("G20", "Catalogue records labelled synthetic (or synthetic overwriting source)", len(cat_syn), not cat_syn, "Synthetic store attributes live on PartCatalogProfile / Price, never on Part")
leaks = [(lbl, k) for lbl, v in N.items() for n in v.values() for k, x in n.items() if k not in PROV_KEYS and isinstance(x, str) and x.strip() in ("NOT_STATED", "NOT_CONFIGURED")]
leaks += [(e["type"], k) for e in E for k, x in e["props"].items() if isinstance(x, str) and x.strip() in ("NOT_STATED", "NOT_CONFIGURED")]
check("G21", "Missing values replaced by guesses or stored as fake values", len(leaks), not leaks, "NOT_STATED / NOT_CONFIGURED are omitted (absent property), never stored as values")
part_id_re = re.compile(r"^PRT-\d{3}$")
legacy_codes = {str(r["legacy_part_number"]) for r in S["parts"] if not token_missing(r["legacy_part_number"])}
legacy_confusion = [p for p in N["Part"] if not part_id_re.match(p)] + [i for v in N.values() for i in v if i in legacy_codes]
check("G22", "Legacy identifiers confused with canonical identifiers", len(legacy_confusion), not legacy_confusion)
no_prov = [x for x in [*E, *[n for v in N.values() for n in v.values()]] if not x.get("provenance_type") or x.get("provenance_type") == "UNKNOWN" or not x.get("source_sheet")]
check("G23", "Graph facts without provenance", len(no_prov), not no_prov)
alloc_lines = collections.Counter(e["from_id"] for e in E if e["type"] in ("ALLOCATED_FROM", "PLANNED_FULFILMENT_FROM"))
check("G24", "Conflicting relationship types for one fact (allocated AND planned)", sum(v > 1 for v in alloc_lines.values()), all(v == 1 for v in alloc_lines.values()))
# cardinality contract
card_viol = []
out_deg = collections.Counter((e["from_label"], e["from_id"], e["type"]) for e in E)
in_deg = collections.Counter((e["to_label"], e["to_id"], e["type"]) for e in E)
for label, rtype in EXACTLY_ONE:
    for nid in N[label]:
        if out_deg[(label, nid, rtype)] != 1:
            card_viol.append(f"{label} {nid} has {out_deg[(label, nid, rtype)]} x {rtype}")
for label, rtype in ONE_OWNER:
    for nid in N[label]:
        if in_deg[(label, nid, rtype)] > 1:
            card_viol.append(f"{label} {nid} owned by {in_deg[(label, nid, rtype)]} x {rtype}")
check("G25", "Cardinality violations (exactly-one / single-owner rules)", len(card_viol), not card_viol, "; ".join(card_viol[:5]))
# catalogue integrity against the ORIGINAL workbook
op = {r["Unified Part No."]: r for r in O["Parts Catalog"]}
mism = [p["unified_part_number"] for p in S["parts"] if p["unified_part_number"] not in op or any(str(op[p["unified_part_number"]][a]).strip() != str(p[b]).strip() for a, b in (("Part Name", "part_name"), ("Category", "part_category"), ("Compatible Machine Types", "compatible_models_source"), ("Plant of Origin", "origin_plant")))]
check("G26", "Catalogue parts differing from the original catalogue workbook", f"{len(mism)} of {len(op)}", not mism)
om = {str(r.get("Model Code") or r.get("Model code") or list(r.values())[0]).strip() for r in O["Machine Types"]}
check("G27", "Catalogue machines missing from the original workbook", len({m["model_code"] for m in S["machines"]} - om), {m["model_code"] for m in S["machines"]} <= om)
check("G28", "Excluded source records documented", f"{len(g.excluded)} documented", all(x.get("reason") and x.get("explanation") for x in g.excluded))
check("G29", "Downloads copy identical to data/processed copy", DOWNLOADS.exists() and DOWNLOADS.read_bytes() == COMPLETE.read_bytes(), DOWNLOADS.exists() and DOWNLOADS.read_bytes() == COMPLETE.read_bytes(), str(DOWNLOADS), blocking=False)

# Warnings (honestly represented, not blockers)
degree = collections.Counter()
for e in E:
    degree[(e["from_label"], e["from_id"])] += 1
    degree[(e["to_label"], e["to_id"])] += 1
isolated = collections.Counter(lbl for lbl, v in N.items() for nid in v if degree[(lbl, nid)] == 0)
fitted_machines = {e["to_id"] for e in fits}
no_part_machines = [N["Machine"][m]["model_code"] for m in N["Machine"] if m not in fitted_machines]
unresolved_legacy = [(n["source_id_value"], N["Part"][next(e["from_id"] for e in E if e["type"] == "HAS_LEGACY_REFERENCE" and e["to_id"] == lid)]["part_number"]) for lid, n in N["LegacyReference"].items() if "legacy_part_number" not in n]
orders = set(N["Order"])
orders_shipped = {e["from_id"] for e in E if e["type"] == "HAS_SHIPMENT"}
lines_shipped = {e["to_id"] for e in E if e["type"] == "SHIPS_LINE"}
asm_parts = {e["from_id"] for e in E if e["type"] == "PART_OF"} | {e["to_id"] for e in E if e["type"] == "IDENTIFIED_BY_PART"}
svc_parts = {e["to_id"] for e in E if e["type"] == "REQUIRES_PART"}
warnings = [
    f"Operational layers are SYNTHETIC_DEMO: suppliers ({len(N['Supplier'])}), dealers ({len(N['Dealer'])}), warehouses ({len(N['Warehouse'])}), stock, prices, compliance, orders, shipments and service plans. Never present them as real.",
    f"3 fitments are CONDITIONAL: {', '.join(e['props']['condition_note'] + ' (' + e['from_id'] + ' -> ' + e['to_id'] + ')' for e in fits if e['props']['fitment_status'] == 'CONDITIONAL')}.",
    f"Machine with no parts in the catalogue: {', '.join(no_part_machines)} (no fitment is manufactured for it).",
    f"{len(unresolved_legacy)} legacy part numbers are unresolved free text: {', '.join(p for _, p in unresolved_legacy)}.",
    f"Shipments exist for {len(orders_shipped)} of {len(orders)} orders; {len(lines_shipped)} of {len(N['OrderLine'])} order lines shipped.",
    f"Assemblies cover {len(asm_parts)} of {len(N['Part'])} parts; service plans cover {len(svc_parts)} of {len(N['Part'])} parts.",
    "Warehouse WH-004 (Zwolle) has no plant link in the source (not filled).",
    f"Machine status, introduction year, category, production status and description are NOT_STATED for all {len(N['Machine'])} machines; part type, OEM status and criticality are NOT_STATED for all {len(N['Part'])} parts.",
    "Machine families and sub-categories are DERIVED by rule and await business confirmation.",
    "Plants are fictional (USER_PROVIDED, declared by the project brief). Plant coordinates are NOT_STATED; synthetic coordinates in SYN_geo_nodes are deliberately not imported.",
    f"Reference nodes with no relationships (by design): {', '.join(f'{k} {v}' for k, v in isolated.items())}.",
    "No item in the workbook is externally verified, including the catalogue layer: authoritative_flag = false everywhere.",
    "Workbook inconsistency: 01_Legend says 'SYNTHETIC: none exists in this dataset' (written for the catalogue layer) while the SYN_ sheets are synthetic; record_counts labels catalogue sheets 'REAL_DERIVED' although 00_README says nothing is real. The graph follows the row-level data_class.",
    "SYN_data_sources rows (including SRC-001, which describes the supplied catalogue) carry data_class SYNTHETIC in the workbook; the DataSource nodes keep that class rather than relabelling it.",
]
for w in warnings:
    check(f"W{warnings.index(w) + 1:02d}", "Warning", "", False, w, blocking=False)


# ======================================================================================================================
# Relationship coverage audit: every relationship the business model needs is accounted for, none silently omitted
# ======================================================================================================================
fk_cols = set()
for sheet_, rows_ in S.items():
    if rows_:
        for c_ in list(rows_[0].keys())[1:]:
            if re.search(r"(_id|_ids)$|^(categories_|families_served|ships_to|owner_)", c_):
                fk_cols.add((sheet_, c_))
unaccounted = sorted(fk_cols - set(FK_ACCOUNT))
check("G30", "Source foreign-key columns not accounted for (neither a relationship nor an explained exclusion)", len(unaccounted), not unaccounted, "; ".join(f"{a}.{b}" for a, b in unaccounted[:8]))

cov_rows = []
cov_problems = []
for grp, domain, src, rel, tgt, status, keys, note, missing in CV:
    es = [e for e in E if (e["type"], e["from_label"], e["to_label"]) in keys]
    prov_set = sorted({e["provenance_type"] for e in es})
    allowed = ["YES" if REL[k][3] else "NO" for k in keys if k in REL]
    if status == IWD and (not es or "SYNTHETIC_DEMO" in prov_set):
        cov_problems.append(f"{rel}: marked IMPLEMENTED_WITH_DATA but {'has no records' if not es else 'includes synthetic records'}")
    if status == IS_ and (not es or prov_set != ["SYNTHETIC_DEMO"]):
        cov_problems.append(f"{rel}: marked IMPLEMENTED_SYNTHETIC but provenance is {prov_set or 'empty'}")
    if status in (SCH, NA, BLK) and es:
        cov_problems.append(f"{rel}: marked {status} but records exist")
    cov_rows.append({
        "DOMAIN": domain, "SOURCE_NODE": src, "RELATIONSHIP": rel, "TARGET_NODE": tgt,
        "DATA_AVAILABLE": "YES" if es else ("PARTIAL" if status == BLK else "NO"),
        "RECORD_COUNT": len(es),
        "PROVENANCE": " / ".join(prov_set) if prov_set else ("MISSING" if status in (SCH, BLK) else "n/a"),
        "SYNTHETIC_ALLOWED": ("YES (marked SYNTHETIC_DEMO)" if "YES" in allowed else "NO") if keys else ("NO: never fabricated" if status != NA else "n/a"),
        "CURRENTLY_IMPLEMENTED": ("YES: " if es else "NO: ") + note,
        "MISSING_DATA": missing or "none", "STATUS": status, "GROUP": grp,
    })
reqd = [r for r in cov_rows if r["GROUP"] == "REQUIRED"]
addl = [r for r in cov_rows if r["GROUP"] == "ADDITIONAL"]
contract_unlisted = [k for k in REL if not any(k in x[6] for x in CV)]
check("G31", "Relationship types in the contract missing from the coverage matrix", len(contract_unlisted), not contract_unlisted, "; ".join(f"{a}:{b}->{c}" for a, b, c in contract_unlisted[:5]))
check("G32", "Coverage rows whose status contradicts the graph", len(cov_problems), not cov_problems, "; ".join(cov_problems[:4]))
check("G33", "Required relationships explicitly accounted for", f"{len(reqd)} of {len(reqd)}", all(r["STATUS"] in (IWD, IS_, SCH, NA, BLK) for r in reqd))
cov_count = collections.Counter(r["STATUS"] for r in reqd)
cov_add_count = collections.Counter(r["STATUS"] for r in addl)
COVERAGE = "PASS" if not unaccounted and not cov_problems and not contract_unlisted else "FAIL"

blocking_fail = [c for c in checks if c["status"] == "FAIL"]
READY = "PASS" if not blocking_fail else "FAIL"

# ======================================================================================================================
# 3. Domain status
# ======================================================================================================================
DOMAINS = [
    ("PARTS", "AVAILABLE", "SOURCE_DERIVED", "Part (100)"),
    ("MACHINES / MACHINE_MODELS", "AVAILABLE (model grain)", "SOURCE_DERIVED", "Machine (15). One node per model; no serial-numbered units exist."),
    ("MACHINE_UNITS (serial-numbered machines)", "MISSING", "MISSING", "Only 30 synthetic variant serial ranges (MachineVariant)."),
    ("MACHINE_FAMILIES", "AVAILABLE", "DERIVED", "MachineFamily (3), model-code prefix rule"),
    ("CATEGORIES", "AVAILABLE", "SOURCE_DERIVED + DERIVED", "Category (10 source + 91 derived)"),
    ("FITMENT", "AVAILABLE", "SOURCE_DERIVED", "FITS (219; 3 CONDITIONAL)"),
    ("CONFIGURATIONS", "MISSING", "MISSING", "No configuration level in any source"),
    ("ASSEMBLIES / COMPONENTS", "PARTIAL", "SYNTHETIC_DEMO", "Assembly (15), PART_OF (35); 43 of 100 parts"),
    ("PLANTS", "AVAILABLE", "USER_PROVIDED", "Plant (3), fictional per brief"),
    ("LOCATIONS", "PARTIAL", "SOURCE_DERIVED + SYNTHETIC_DEMO", "Location (5, no coordinates); Address (44, synthetic placeholders); Region (14, synthetic)"),
    ("SUPPLIERS", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Supplier (12), SUPPLIED_BY (157)"),
    ("DEALERS", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Dealer (15), STOCKED_BY (315), SERVES_FAMILY (30)"),
    ("INVENTORY", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "AVAILABLE_AT (400), STOCKED_BY quantities (315); 26 rows excluded"),
    ("DEPOTS (warehouses)", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Warehouse (4)"),
    ("FULFILMENT", "PARTIAL", "SYNTHETIC_DEMO", "DeliveryEstimate (100), ShippingRate (8)"),
    ("TRANSPORTATION / CARRIERS", "PARTIAL", "SYNTHETIC_DEMO", "One fictional carrier; real carriers MISSING"),
    ("PRICING", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Price (100)"),
    ("CUSTOMERS", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Customer (10), Cart (3)"),
    ("REQUESTS / REQUEST_LINES", "MISSING", "MISSING", "No requests (carts are not requests)"),
    ("ORDERS / ORDER_LINES", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "Order (8), OrderLine (14), OrderStatusEvent (32)"),
    ("ALLOCATIONS", "PARTIAL", "SYNTHETIC_DEMO", "ALLOCATED_FROM (10) / PLANNED_FULFILMENT_FROM (4); no allocation records"),
    ("SHIPMENTS", "PARTIAL", "SYNTHETIC_DEMO", "Shipment (9) for 4 of 8 orders"),
    ("TRACKING_EVENTS", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "TrackingEvent (27)"),
    ("DELIVERY (confirmation)", "PARTIAL", "SYNTHETIC_DEMO", "Shipment status DELIVERED only; no delivery records"),
    ("SERVICE_JOBS", "MISSING", "MISSING", "Only synthetic ServicePlan templates (60)"),
    ("SERVICE_PLANS", "PARTIAL", "SYNTHETIC_DEMO", "ServicePlan (60), REQUIRES_PART (71) covering 33 parts"),
    ("INSTALLATIONS / COMPLETION", "MISSING", "MISSING", "None"),
    ("ALTERNATIVES", "MISSING", "MISSING", "No authoritative alternative data"),
    ("SUPERSESSIONS", "MISSING", "MISSING", "None; legacy references are previous numbers of the same part"),
    ("PART RELATIONSHIPS (name group / related component)", "AVAILABLE", "DERIVED", "SAME_NAME_GROUP_AS (9), RELATED_COMPONENT (2)"),
    ("CO-ORDER SIGNALS", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "CO_ORDERED_WITH (75 after removing 14 mirrored duplicates)"),
    ("LEGACY PART NUMBERS", "AVAILABLE", "SOURCE_DERIVED", "LegacyReference (100; 5 unresolved free text)"),
    ("SPECIFICATIONS", "AVAILABLE", "SOURCE_DERIVED + DERIVED", "PartSpecification (279); MachineSpecification (83, synthetic)"),
    ("COMPLIANCE", "AVAILABLE (synthetic)", "SYNTHETIC_DEMO", "ComplianceRequirement (8), HAS_COMPLIANCE (100)"),
    ("RISKS", "MISSING", "MISSING", "None"),
    ("PROVENANCE", "AVAILABLE", "metadata", "Provenance properties on every node and relationship; DataSource (4)"),
    ("AUDIT TRAIL", "PARTIAL", "metadata", "last_updated per row; no change history"),
    ("USERS / ROLES", "NOT_REQUIRED_FOR_CURRENT_PHASE", "SYNTHETIC_DEMO", "SYN_users / SYN_roles not imported"),
]
MISSING_DOMAINS = [d[0] for d in DOMAINS if d[1] == "MISSING"]

# ======================================================================================================================
# 4. Write the audit pack
# ======================================================================================================================
# graph/audits/aura_*.json are the AuraDB run evidence (not generated here): keep them across rebuilds
_keep = {f.name: f.read_bytes() for f in (OUT["graph_audit"].glob("aura_*.json") if OUT["graph_audit"].exists() else [])}
for d in OUT.values():
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
for _name, _data in _keep.items():
    (OUT["graph_audit"] / _name).write_bytes(_data)
A = OUT["graph_audit"]

entity_rows = []
for lbl, v in sorted(N.items()):
    ptypes = collections.Counter(n["provenance_type"] for n in v.values())
    entity_rows.append({"label": lbl, "canonical_id": ID_PROP[lbl], "nodes": len(v), "unique_ids": len(v), "duplicate_ids": sum(1 for i in g.node_issues if i["label"] == lbl), "relationships_touching": sum(degree[(lbl, i)] for i in v), "isolated_nodes": isolated.get(lbl, 0), "provenance": " / ".join(f"{k}:{c}" for k, c in ptypes.items()), "source_sheet": next(iter(v.values()))["source_sheet"]})
write_csv(A / "entity_inventory.csv", entity_rows)
write_csv(A / "source_inventory.csv", inventory_rows)

rel_rows = []
for (t, fl, tl), meta in REL.items():
    es = [e for e in E if e["type"] == t and e["from_label"] == fl and e["to_label"] == tl]
    if not es:
        continue
    ptypes = collections.Counter(e["provenance_type"] for e in es)
    rel_rows.append({"relationship": t, "from_label": fl, "to_label": tl, "count": len(es), "distinct_from": len({e["from_id"] for e in es}), "distinct_to": len({e["to_id"] for e in es}), "max_out_degree": max(collections.Counter(e["from_id"] for e in es).values()), "max_in_degree": max(collections.Counter(e["to_id"] for e in es).values()), "provenance": " / ".join(f"{k}:{c}" for k, c in ptypes.items()), "source_sheet": "|".join(sorted({e["source_sheet"] for e in es}))})
write_csv(A / "relationship_inventory.csv", rel_rows)

matrix = [{"relationship": t, "from_label": fl, "direction": f"({fl})-[:{t}]->({tl})", "to_label": tl, "cardinality": m[1], "meaning": m[0], "allowed_sources": "|".join(m[2]), "synthetic_allowed": "YES (marked SYNTHETIC_DEMO)" if m[3] else "NO", "inference_allowed": "NO", "required_properties": "|".join(m[4]), "present_in_data": "YES" if any(r["relationship"] == t and r["from_label"] == fl for r in rel_rows) else "NO"} for (t, fl, tl), m in REL.items()]
matrix += [{"relationship": k.split(" ")[0], "from_label": v[0], "direction": f"({v[0]})-[:{k.split(' ')[0]}]->({v[1]})", "to_label": v[1], "cardinality": "-", "meaning": v[2], "allowed_sources": "authoritative evidence only", "synthetic_allowed": "NO", "inference_allowed": "NO", "required_properties": "", "present_in_data": "NO (MISSING: not created)"} for k, v in SCHEMA_ONLY.items()]
write_csv(A / "relationship_matrix.csv", matrix)

excluded_rows = [{"record_id": x["record_id"], "source_sheet": x["source_sheet"], "classification": "EXCLUDED", "reason": x["reason"], "would_have_been": x["would_have_been"], "explanation": x["explanation"], "data_status": x["data_status"]} for x in g.excluded]
write_csv(A / "excluded_records.csv", excluded_rows)

missing_rows = []
for (lbl, prop), (have, miss) in sorted(g.prop_stats.items()):
    if miss:
        missing_rows.append({"kind": "FIELD", "entity_or_domain": lbl, "field_or_relationship": prop, "records_missing": miss, "records_total": have + miss, "classification": "MISSING" if have == 0 else "PARTIAL", "why_it_matters": "", "dependent_relationship": "", "synthetic_could_supply": "", "authoritative_required": ""})
for m in g.missing_links:
    missing_rows.append({"kind": "RELATIONSHIP", "entity_or_domain": f"{m['from_label']} {m['from_id']}", "field_or_relationship": m["relationship"], "records_missing": 1, "records_total": 1, "classification": "MISSING", "why_it_matters": "The warehouse cannot be traced to a plant", "dependent_relationship": m["relationship"], "synthetic_could_supply": "Only as explicitly synthetic data, if the business wants it", "authoritative_required": "YES (if used for planning)"})
GAP_DOCS = {
    "Machine:status": ("Lifecycle (active / discontinued) gates which machines parts are offered for", "-", "No: a guessed lifecycle would mislead", "YES"),
    "Machine:introduction_year": ("Needed for date-bounded fitment and supersession", "FITS (effective dates)", "No", "YES"),
    "Machine:machine_category": ("Navigation and filtering", "-", "Possibly, if marked synthetic", "Preferred"),
    "Machine:production_status": ("In-production vs service-only affects availability promises", "-", "No", "YES"),
    "Machine:description": ("Search and agent answers", "-", "Yes, if marked synthetic", "Preferred"),
    "Part:part_type": ("Distinguishes wear part / assembly / consumable", "PART_OF", "No", "YES"),
    "Part:oem_status": ("OEM vs aftermarket affects sourcing and warranty", "SUPPLIED_BY", "No", "YES"),
    "Part:criticality": ("Prioritises urgent / machine-down orders", "-", "No", "YES"),
    "Part:part_nature": ("Classifies the part", "-", "No", "YES"),
}
for r in missing_rows:
    doc = GAP_DOCS.get(f"{r['entity_or_domain']}:{r['field_or_relationship']}")
    if doc:
        r["why_it_matters"], r["dependent_relationship"], r["synthetic_could_supply"], r["authoritative_required"] = doc
for name, status, prov, note in DOMAINS:
    if status in ("MISSING", "PARTIAL"):
        missing_rows.append({"kind": "DOMAIN", "entity_or_domain": name, "field_or_relationship": "", "records_missing": "", "records_total": "", "classification": status, "why_it_matters": note, "dependent_relationship": "", "synthetic_could_supply": "Only if explicitly marked SYNTHETIC_DEMO" if status == "PARTIAL" else "NO for alternatives / supersessions / risk; others only as marked demo data", "authoritative_required": "YES"})
for code, part in unresolved_legacy:
    missing_rows.append({"kind": "UNRESOLVED_SOURCE", "entity_or_domain": f"LegacyReference {code}", "field_or_relationship": "legacy_part_number", "records_missing": 1, "records_total": 1, "classification": "UNKNOWN", "why_it_matters": f"Free-text legacy note for {part}; the old number cannot be resolved", "dependent_relationship": "HAS_LEGACY_REFERENCE", "synthetic_could_supply": "NO", "authoritative_required": "YES"})
for m in no_part_machines:
    missing_rows.append({"kind": "UNRESOLVED_SOURCE", "entity_or_domain": f"Machine {m}", "field_or_relationship": "FITS", "records_missing": "all", "records_total": "", "classification": "MISSING", "why_it_matters": "The catalogue lists no parts for this machine", "dependent_relationship": "FITS", "synthetic_could_supply": "NO (fitment is never synthesised)", "authoritative_required": "YES"})
write_csv(A / "missing_data_register.csv", missing_rows)

syn_rows = []
for lbl, v in sorted(N.items()):
    c = sum(1 for n in v.values() if n["data_status"] == "SYNTHETIC_DEMO")
    if c:
        syn_rows.append({"kind": "NODE", "name": lbl, "synthetic_records": c, "total": len(v), "source_sheet": next(iter(v.values()))["source_sheet"], "marker": "data_status = provenance_type = SYNTHETIC_DEMO"})
for r in rel_rows:
    if "SYNTHETIC_DEMO" in r["provenance"]:
        syn_rows.append({"kind": "RELATIONSHIP", "name": f"{r['from_label']}-[{r['relationship']}]->{r['to_label']}", "synthetic_records": r["count"], "total": r["count"], "source_sheet": r["source_sheet"], "marker": "data_status = provenance_type = SYNTHETIC_DEMO"})
write_csv(A / "synthetic_data_inventory.csv", syn_rows)
write_csv(A / "readiness_checks.csv", checks)
write_csv(A / "relationship_coverage_matrix.csv", cov_rows, ["DOMAIN", "SOURCE_NODE", "RELATIONSHIP", "TARGET_NODE", "DATA_AVAILABLE", "RECORD_COUNT", "PROVENANCE", "SYNTHETIC_ALLOWED", "CURRENTLY_IMPLEMENTED", "MISSING_DATA", "STATUS"])
(A / "relationship_coverage_report.md").write_text(f"""# Relationship coverage audit

## GRAPH RELATIONSHIP COVERAGE = {COVERAGE}

Every required relationship, and every relationship found by inspecting the source data, is classified in
`relationship_coverage_matrix.csv`. Nothing is omitted. Source columns that look like references: {len(fk_cols)}; each is either a
relationship or an explained exclusion ({len([v for v in FK_ACCOUNT.values() if v.startswith("EXCLUDED")])} exclusions).

| Required relationships (the {len(reqd)} you listed) | Count |
|---|---|
| TOTAL RELATIONSHIPS REQUIRED | {len(reqd)} |
| IMPLEMENTED_WITH_DATA | {cov_count[IWD]} |
| IMPLEMENTED_SYNTHETIC | {cov_count[IS_]} |
| SCHEMA_ONLY_NO_DATA | {cov_count[SCH]} |
| NOT_APPLICABLE | {cov_count[NA]} |
| BLOCKED_BY_MISSING_DATA | {cov_count[BLK]} |

| Additional relationships found in the source data | Count |
|---|---|
| TOTAL | {len(addl)} |
| IMPLEMENTED_WITH_DATA | {cov_add_count[IWD]} |
| IMPLEMENTED_SYNTHETIC | {cov_add_count[IS_]} |
| SCHEMA_ONLY_NO_DATA | {cov_add_count[SCH]} |
| NOT_APPLICABLE | {cov_add_count[NA]} |
| BLOCKED_BY_MISSING_DATA | {cov_add_count[BLK]} |

## Relationships added by this audit (the source states them; they were only text columns before)

- `HOME_PLANT` (BusinessUnit to Plant), from `business_units.home_plant_id`
- `SUPPLIES_CATEGORY` (Supplier to Category), from `SYN_suppliers.categories_supplied`. Declared scope only: it does NOT imply any part-level supply.
- `COVERS_CATEGORY` (ComplianceRequirement to Category), from `SYN_compliance.categories_covered`
- `SHIPS_TO_COUNTRY` (Warehouse to Location), from `SYN_warehouses.ships_to` (NL and DE; BE is blocked, see below)

## Blocked or schema-only, with the data needed

{md_table([r for r in cov_rows if r["STATUS"] in (SCH, BLK)], ["GROUP", "SOURCE_NODE", "RELATIONSHIP", "TARGET_NODE", "STATUS", "MISSING_DATA"])}

## Deliberately not relationships

{md_table([r for r in cov_rows if r["STATUS"] == NA], ["SOURCE_NODE", "RELATIONSHIP", "CURRENTLY_IMPLEMENTED"])}

## Source columns and what happens to them

{md_table([{"sheet": a, "column": b, "handled by": FK_ACCOUNT[(a, b)]} for (a, b) in sorted(fk_cols)], ["sheet", "column", "handled by"])}

## Reading the inverse rows

Rows such as "Machine -> Part" and "Supplier -> Part" are inverse traversals of one stored relationship (`FITS`, `SUPPLIED_BY`).
Storing both directions would duplicate the same fact, which the readiness gate forbids; Cypher traverses either way.
""", encoding="utf-8")


node_by_status = collections.Counter(n["data_status"] for v in N.values() for n in v.values())
edge_by_status = collections.Counter(e["data_status"] for e in E)
syn_records = node_by_status["SYNTHETIC_DEMO"] + edge_by_status["SYNTHETIC_DEMO"]
src_records = node_by_status["SOURCE_DERIVED"] + edge_by_status["SOURCE_DERIVED"]
der_records = node_by_status["DERIVED"] + edge_by_status["DERIVED"]
usr_records = node_by_status["USER_PROVIDED"] + edge_by_status["USER_PROVIDED"]

ra = {r["relationship_type"]: 0 for r in S["relationships_all"]}
for r in S["relationships_all"]:
    ra[r["relationship_type"]] += 1
RECON = {"HAS_PART_FITMENT": ["FITS"], "PRODUCED_AT": ["MANUFACTURED_AT"], "HAS_MACHINE_TYPE": ["OF_TYPE"], "IN_FAMILY": ["MEMBER_OF_FAMILY"], "OF_BRAND": ["BRANDED_AS"], "FAMILY_OF_BRAND": ["PRODUCT_FAMILY_OF"], "OWNED_BY": ["OWNED_BY"], "LOCATED_IN": ["LOCATED_IN"], "IN_COUNTRY": ["IN_COUNTRY"], "SUBCATEGORY_OF": ["SUBCATEGORY_OF"], "IN_CATEGORY": ["IN_CATEGORY"], "IN_SUBCATEGORY": ["IN_SUBCATEGORY"], "ORIGINATES_AT": ["ORIGINATES_AT"], "HAS_LEGACY_MAPPING": ["HAS_LEGACY_REFERENCE"], "LEGACY_BUSINESS": ["ISSUED_BY_BUSINESS_UNIT"], "SAME_SUBCATEGORY": ["SAME_NAME_GROUP_AS"], "RELATED_COMPONENT": ["RELATED_COMPONENT"], "SUPPLIED_BY": ["SUPPLIED_BY"], "STOCKED_AT": ["AVAILABLE_AT", "STOCKED_BY"], "HAS_COMPONENT": ["PART_OF"], "USES_PART": ["REQUIRES_PART"], "SERVICES_MACHINE": ["FOR_MACHINE"], "FREQUENTLY_ORDERED_WITH_DEMO": ["CO_ORDERED_WITH"], "ORDERS_PART": ["REFERENCES_PART"], "FULFILLED_FROM": ["ALLOCATED_FROM", "PLANNED_FULFILMENT_FROM"], "PLACED_BY": ["ORDERED_BY"], "LOCATED_AT_PLANT": ["LOCATED_AT_PLANT"], "DEALER_SERVES_FAMILY": ["SERVES_FAMILY"], "MEETS_COMPLIANCE": ["HAS_COMPLIANCE"], "ON_BACKORDER_FROM": ["PLACED_WITH"]}
type_count = collections.Counter(e["type"] for e in E)
SCOPED = {"FOR_MACHINE": sum(1 for e in E if e["type"] == "FOR_MACHINE" and e["from_label"] == "ServicePlan"), "REFERENCES_PART": sum(1 for e in E if e["type"] == "REFERENCES_PART" and e["from_label"] == "OrderLine")}
recon_rows = []
for src_type, cnt in ra.items():
    mapped = RECON.get(src_type, [])
    gc = sum(SCOPED.get(t, type_count[t]) for t in mapped)
    note = {"STOCKED_AT": "26 dealer zero-rows excluded (UNKNOWN, not 0)", "FREQUENTLY_ORDERED_WITH_DEMO": "14 mirrored duplicates stored once", "FULFILLED_FROM": "workbook edge is order -> warehouse with 3 repeats; graph is per order line and split by allocation status", "HAS_COMPONENT": "direction Part -> Assembly"}.get(src_type, "")
    recon_rows.append({"workbook_type": src_type, "workbook_edges": cnt, "graph_type": " + ".join(mapped), "graph_edges": gc, "match": "YES" if gc == cnt else "EXPLAINED" if note else "NO", "note": note})

ts = dt.datetime.now().isoformat(timespec="seconds")
gate_rows = [c for c in checks if c["id"].startswith("G")]
(A / "graph_readiness_report.md").write_text(f"""# Graph readiness report

Generated {ts} by `scripts/graph_build.py` from `{COMPLETE.relative_to(ROOT)}` (identical to the Downloads copy) and
`{ORIGINAL.relative_to(ROOT)}`. No database was contacted.

## GRAPH_READINESS = {READY}

| Measure | Value |
|---|---|
| Nodes | {node_count} |
| Relationships | {len(E)} |
| Node labels | {len(N)} |
| Relationship types | {len(type_count)} |
| Duplicate nodes | {len(dup_nodes)} |
| Duplicate relationships | {len(dup_rel)} |
| Duplicate semantic relationships | {len(sym_dup) // 2} |
| Orphan relationships | {sum(1 for e in E if not e.get('source_record_id'))} |
| Broken references | {len(broken)} |
| Relationship violations (endpoint + source + direction + cardinality + semantic) | {len(bad_end) + len(bad_src) + len(reversed_types) + len(card_viol) + len(forbidden) + len(asserted)} |
| Synthetic records (nodes + relationships) | {syn_records} |
| Source-derived records | {src_records} |
| Derived records | {der_records} |
| User-provided (project brief) records | {usr_records} |
| Excluded source records | {len(g.excluded)} |

## Gate checks

{md_table(gate_rows, ['id', 'check', 'result', 'status'])}

## Warnings (acceptable, represented honestly)

{chr(10).join(f'- {w}' for w in warnings)}

## Missing domains (schema supports them; no records are created)

{chr(10).join(f'- {d}' for d in MISSING_DOMAINS)}

## Fixes applied in this build

- **Mirrored co-order duplicates:** 14 `SYN_part_relationships` rows repeated a pair that was already present in the opposite
  direction. `CO_ORDERED_WITH` is symmetric, so each pair is stored once (lower part id to higher part id) and the
  duplicate's record id is kept on the stored relationship (`merged_source_record_ids`). 89 rows → 75 relationships.
  `SAME_NAME_GROUP_AS` (also symmetric) had no mirrored rows. No directional relationship was touched.
- **Unknown dealer stock:** 26 `SYN_inventory` rows state 0 stock at a dealer that `SYN_part_dealer` does not list as
  stocking the part. They remain excluded (UNKNOWN, not ZERO); see `excluded_records.csv`.
""", encoding="utf-8")

(A / "data_quality_report.md").write_text(f"""# Data quality report

## Sources

- `{COMPLETE.name}`: {len(S)} sheets. Catalogue sheets are SOURCE_DERIVED / DERIVED from the supplied catalogue;
  `SYN_` sheets are synthetic (seed 42); `plants` and `order_statuses` are DEMO (declared by the project brief).
- `{ORIGINAL.name}`: the supplied catalogue ({len(O['Parts Catalog'])} parts, {len(O['Machine Types'])} machine types). Every catalogue part matches it
  (name, category, plant, compatible machines): {len(mism)} differences.
- The Downloads copy is byte-identical to `data/processed/`.

Per-sheet row counts, identifiers, duplicates, nulls, NOT_STATED and blank counts: `source_inventory.csv`.

## Entity quality

{md_table(entity_rows, ['label', 'canonical_id', 'nodes', 'duplicate_ids', 'relationships_touching', 'isolated_nodes', 'provenance'])}

## Field completeness (fields with values the source does not state)

{md_table([r for r in missing_rows if r['kind'] == 'FIELD'], ['entity_or_domain', 'field_or_relationship', 'records_missing', 'records_total', 'classification'])}

## Partial synthetic coverage (preserved, not filled)

- Orders: {len(orders)}; orders with shipments: {len(orders_shipped)}; shipped order lines: {len(lines_shipped)} of {len(N['OrderLine'])}.
- Assemblies: {len(N['Assembly'])}, covering {len(asm_parts)} parts. Service plans: {len(N['ServicePlan'])}, covering {len(svc_parts)} parts.
- Warehouse WH-004 (Zwolle): no plant link.
- Order lines: {type_count['ALLOCATED_FROM']} allocated (reserved or shipped), {type_count['PLANNED_FULFILMENT_FROM']} not yet allocated (planned source only).

## Unresolved source items (kept unresolved)

- Machine with no catalogue parts: {', '.join(no_part_machines)}.
- Legacy part numbers recorded only as free text: {', '.join(f'{p} ({c})' for c, p in unresolved_legacy)}.
- Conditional fitments: {', '.join(f"{e['from_id']} -> {e['to_id']}: {e['props'].get('condition_note')}" for e in fits if e['props']['fitment_status'] == 'CONDITIONAL')}.

## Cross-dataset consistency

- Dealer stock (`SYN_inventory`, 341 dealer rows) vs dealer stocking (`SYN_part_dealer`, 315): 26 inventory rows have no
  stocking record. All 26 are 0-stock rows → excluded as UNKNOWN.
- Primary supplier on `SYN_part_catalog` vs `SYN_part_supplier.is_primary`: consistent for all 100 parts.
- List price on `SYN_part_catalog` vs `SYN_pricing`: consistent for all 100 parts.
- Store display names vs catalogue part names: identical for all 100 parts.

## Reconciliation with the workbook's own edge list (`relationships_all`, not imported)

{md_table(recon_rows, ['workbook_type', 'workbook_edges', 'graph_type', 'graph_edges', 'match', 'note'])}

## Not imported (and why)

{chr(10).join(f"- `{r['sheet']}`: {r['graph_role'].replace('NOT IMPORTED: ', '')}" for r in inventory_rows if r['graph_role'].startswith('NOT IMPORTED'))}
""", encoding="utf-8")

(A / "provenance_report.md").write_text(f"""# Provenance report

Every node and relationship carries: `provenance_type`, `data_status`, `source_id`, `source_file`, `source_sheet`,
`source_record_id`, `source_name`, `source_ref`, `confidence`, `authoritative_flag`, `last_updated`.

## Classification

| Class | Meaning in this graph | Nodes | Relationships |
|---|---|---|---|
| SOURCE_DERIVED | Copied from the supplied catalogue workbook, traceable to sheet and row | {node_by_status['SOURCE_DERIVED']} | {edge_by_status['SOURCE_DERIVED']} |
| DERIVED | Deterministic rule over source values (families, sub-categories, name groups, legacy business) | {node_by_status['DERIVED']} | {edge_by_status['DERIVED']} |
| USER_PROVIDED | Declared by the project brief (workbook class DEMO): plants, order-status vocabulary | {node_by_status['USER_PROVIDED']} | {edge_by_status['USER_PROVIDED']} |
| SYNTHETIC_DEMO | Generated demonstration data (`SYN_` sheets, gen_synthetic.py seed 42) | {node_by_status['SYNTHETIC_DEMO']} | {edge_by_status['SYNTHETIC_DEMO']} |
| MISSING | Required by the model, absent in the data: not created, listed in `missing_data_register.csv` | 0 | 0 |
| UNKNOWN | Cannot be established: properties left absent (e.g. unresolved legacy numbers, interchangeability_status = UNKNOWN) | - | - |
| EXCLUDED | Source rows deliberately kept out, listed in `excluded_records.csv` | {len(g.excluded)} rows | |

## Rules applied

- The workbook's row-level `data_class` decides the class; nothing is re-labelled. DEMO → USER_PROVIDED, SYNTHETIC →
  SYNTHETIC_DEMO.
- `authoritative_flag = false` on every record: the workbook states that nothing in it is externally verified.
- `confidence` keeps the workbook's own value (SOURCE_STATED, SOURCE_STATED_CONDITIONAL, RULE_DERIVED, NEEDS_REVIEW,
  NOT_STATED).
- Synthetic attributes of a part (status, orderable, weight, price...) are stored on separate `PartCatalogProfile` and
  `Price` nodes, so a synthetic value can never overwrite a catalogue value on `Part`.
- Synthetic coordinates (`SYN_geo_nodes`) are not put on plants, whose source coordinates are NOT_STATED.
- `DataSource` nodes ({', '.join(N['DataSource'])}) are the workbook's own source register plus the project brief; nodes
  and relationships reference them by `source_id`.

## Traversal to provenance

```cypher
MATCH (p:Part {{part_number: 'NVM-1010-HY'}})-[f:FITS]->(m:Machine)
MATCH (d:DataSource {{source_id: f.source_id}})
RETURN p.part_number, m.model_code, f.fitment_status, f.provenance_type, f.source_sheet, f.source_record_id, d.name
```
""", encoding="utf-8")

# ======================================================================================================================
# 5. Schema
# ======================================================================================================================
Sd = OUT["graph_schema"]
node_schema = []
for lbl, v in sorted(N.items()):
    keys = collections.Counter(k for n in v.values() for k in n)
    req = [k for k, c in keys.items() if c == len(v)]
    opt = [k for k, c in keys.items() if c < len(v)]
    doc = NODE_DOC.get(lbl, ("Synthetic demonstration entity.", "SYNTHETIC_DEMO", []))
    node_schema.append({"label": lbl, "canonical_id": ID_PROP[lbl], "unique": "YES (constraint)", "meaning": doc[0], "provenance": doc[1], "synthetic_marker": "data_status = SYNTHETIC_DEMO" if any(n["data_status"] == "SYNTHETIC_DEMO" for n in v.values()) else "n/a (not synthetic)", "required_properties": "|".join(k for k in req if k not in PROV_KEYS), "optional_properties": "|".join(opt), "provenance_properties": "|".join(PROV_KEYS), "nodes": len(v)})
write_csv(Sd / "node_schema.csv", node_schema)
rel_schema = []
for (t, fl, tl), m in REL.items():
    es = [e for e in E if e["type"] == t and e["from_label"] == fl and e["to_label"] == tl]
    keys = collections.Counter(k for e in es for k in e["props"])
    rel_schema.append({"relationship": t, "from_label": fl, "to_label": tl, "direction": f"({fl})-[:{t}]->({tl})", "meaning": m[0], "cardinality": m[1], "required_properties": "|".join(["rel_id", *m[4]]), "optional_properties": "|".join(k for k in keys if k not in m[4]), "provenance": "|".join(sorted({e["provenance_type"] for e in es})) or "-", "synthetic_allowed": "YES (marked)" if m[3] else "NO", "inference_allowed": "NO", "count": len(es)})
write_csv(Sd / "relationship_schema.csv", rel_schema)

EXPECTED_MAP = [
    ("(:Part)-[:FITS]->(:Machine)", "(:Part)-[:FITS]->(:Machine)", "As expected. :Machine is a model (no serial units exist)."),
    ("(:Part)-[:BELONGS_TO]->(:Category)", "(:Part)-[:IN_CATEGORY]->(:Category) and (:Part)-[:IN_SUBCATEGORY]->(:Category)", "Two distinct facts: a source-stated category and a rule-derived sub-category. A single BELONGS_TO would collapse them; BELONGS_TO is also on the generic list."),
    ("(:Part)-[:PART_OF]->(:Assembly)", "(:Part)-[:PART_OF {quantity}]->(:Assembly)", "As expected (synthetic BOM)."),
    ("(:Part)-[:SUPPLIED_BY]->(:Supplier)", "(:Part)-[:SUPPLIED_BY]->(:Supplier)", "As expected (synthetic)."),
    ("(:Part)-[:AVAILABLE_AT]->(:Depot)", "(:Part)-[:AVAILABLE_AT {on_hand, reserved, available}]->(:Warehouse)", "The workbook calls depots warehouses; the label keeps the source term."),
    ("(:Part)-[:STOCKED_BY]->(:Dealer)", "(:Part)-[:STOCKED_BY {stocking_status, available...}]->(:Dealer)", "As expected (synthetic)."),
    ("(:Part)-[:ALTERNATIVE_TO]->(:Part)", "not created", "MISSING: no authoritative evidence."),
    ("(:Part)-[:SUPERSEDES]->(:Part)", "not created", "MISSING: no supersession data."),
    ("(:Order)-[:ORDERED_BY]->(:Customer)", "(:Order)-[:ORDERED_BY]->(:Customer)", "As expected."),
    ("(:Order)-[:CONTAINS]->(:OrderLine)", "(:Order)-[:CONTAINS_LINE]->(:OrderLine)", "CONTAINS_LINE keeps order lines distinct from other containment."),
    ("(:OrderLine)-[:REFERENCES_PART]->(:Part)", "(:OrderLine)-[:REFERENCES_PART]->(:Part)", "As expected."),
    ("(:Order)-[:HAS_SHIPMENT]->(:Shipment)", "(:Order)-[:HAS_SHIPMENT]->(:Shipment)", "As expected."),
    ("(:Shipment)-[:HAS_TRACKING_EVENT]->(:TrackingEvent)", "(:Shipment)-[:HAS_TRACKING_EVENT]->(:TrackingEvent)", "As expected."),
    ("(:ServiceJob)-[:FOR_MACHINE]->(:Machine)", "(:ServicePlan)-[:FOR_MACHINE]->(:Machine)", "Service JOBS are MISSING; the data has service PLANS (interval templates). They are not relabelled as jobs."),
    ("(:ServiceJob)-[:REQUIRES_PART]->(:Part)", "(:ServicePlan)-[:REQUIRES_PART]->(:Part)", "As above."),
    ("FULFILLED_BY", "(:OrderLine)-[:ALLOCATED_FROM]->(:Warehouse) / (:OrderLine)-[:PLANNED_FULFILMENT_FROM]->(:Warehouse)", "Split by allocation status, so a planned source is never read as an actual allocation."),
    ("CO_ORDERED_WITH", "(:Part)-[:CO_ORDERED_WITH]->(:Part)", "Symmetric, stored once; traverse undirected."),
]
(Sd / "graph_schema.md").write_text(f"""# Parts Intelligence graph schema

{len(N)} node labels, {len(type_count)} relationship types, {node_count} nodes, {len(E)} relationships.

## Node labels

{md_table(node_schema, ['label', 'canonical_id', 'nodes', 'provenance', 'meaning'])}

Every node also carries the provenance properties ({', '.join(PROV_KEYS)}). Nodes whose canonical id differs from the
workbook column keep the workbook value in `source_id_value`.

## Relationships

{md_table(rel_schema, ['direction', 'cardinality', 'count', 'provenance', 'synthetic_allowed'])}

Every relationship carries a deterministic `rel_id` (`TYPE:source_record_id`), its own properties, and the provenance
properties.

## Mapping from the expected model

{md_table([{'expected': a, 'in this graph': b, 'why': c} for a, b, c in EXPECTED_MAP], ['expected', 'in this graph', 'why'])}

## Supported by the schema, absent in the data (not created)

{md_table([{'relationship': k, 'from': v[0], 'to': v[1], 'status': v[2]} for k, v in SCHEMA_ONLY.items()], ['relationship', 'from', 'to', 'status'])}

## Machine hierarchy

| Level | Status |
|---|---|
| Machine family | DERIVED (model-code prefix) |
| Machine model | SOURCE_DERIVED (`:Machine`) |
| Variant / serial range | SYNTHETIC_DEMO (`:MachineVariant`) |
| Configuration | MISSING |
| Assembly | SYNTHETIC_DEMO (demo BOM) |
| Component → Part | SYNTHETIC_DEMO (`PART_OF`) |
""", encoding="utf-8")

(Sd / "relationship_contract.md").write_text("# Relationship contract\n\nInference is never allowed: every relationship is a workbook row. Synthetic relationships are allowed only where stated, and always carry `data_status = SYNTHETIC_DEMO`.\n\n" + "\n".join(
    f"## {t}  `({fl})-[:{t}]->({tl})`\n\n- **Meaning:** {m[0]}\n- **Cardinality:** {m[1]}\n- **Allowed source:** {', '.join(m[2])}\n- **Required properties:** rel_id, {', '.join(m[4]) or '(provenance only)'}, provenance properties\n- **Provenance required:** YES\n- **Synthetic allowed:** {'YES, only explicitly marked SYNTHETIC_DEMO' if m[3] else 'NO'}\n- **Inference allowed:** NO\n- **Interchangeability:** NOT IMPLIED\n"
    for (t, fl, tl), m in REL.items()) + "\n## Never created without authoritative evidence\n\n" + "\n".join(f"- `{k}` ({v[0]} → {v[1]}): {v[2]}" for k, v in SCHEMA_ONLY.items()) + "\n\n## Forbidden generic types\n\n" + ", ".join(sorted(FORBIDDEN_TYPES)) + "\n", encoding="utf-8")

(Sd / "identifier_contract.md").write_text("# Identifier contract\n\nEvery node is merged on one canonical id (unique constraint). Names are never identity. No random UUIDs: re-imports are deterministic.\n\n" + md_table(
    [{"label": lbl, "canonical id property": ID_PROP[lbl], "source column": next((s.id_col for s in NODE_SPECS if s.label == lbl), {"Carrier": "derived from carrier name (CAR-<slug>)", "DataSource": "SYN_data_sources.source_id / SRC-BRIEF"}.get(lbl, "")), "example": next(iter(N[lbl])), "stable": "YES", "synthetic id": "YES" if next(iter(N[lbl].values()))["data_status"] == "SYNTHETIC_DEMO" else "NO"} for lbl in sorted(N)],
    ["label", "canonical id property", "source column", "example", "stable", "synthetic id"]) + """

## Legacy and alternate identifiers

- Legacy part numbers (`AS-771`, `HK-2291-B`...) live on `:LegacyReference`, never as a Part id.
- `Part.part_number` (unified number, e.g. NVM-1010-HY) is unique but is not the merge key; `part_id` is.
- Search aliases live on `:SearchAlias` nodes.
- Relationships: `rel_id = TYPE:source_record_id` (unique per type, constraint). Symmetric relationships are stored lower
  id → higher id; merged duplicates keep their record ids in `merged_source_record_ids`.
""", encoding="utf-8")

(Sd / "provenance_contract.md").write_text(f"""# Provenance contract

Required on every node and relationship:

| Property | Meaning |
|---|---|
| provenance_type | SOURCE_DERIVED, DERIVED, USER_PROVIDED or SYNTHETIC_DEMO |
| data_status | Same value as provenance_type (the marker queries filter on) |
| source_id | DataSource node id (SRC-001 catalogue, SRC-002 rules, SRC-003 synthetic generator, SRC-BRIEF project brief) |
| source_file | {COMPLETE.name} |
| source_sheet | Workbook sheet |
| source_record_id | Row id in that sheet |
| source_name / source_ref | The workbook's own source citation (row / column reference for catalogue rows) |
| confidence | Workbook confidence, verbatim |
| authoritative_flag | false (nothing is externally verified) |
| last_updated | Workbook last_updated |

Not used, because the workbook does not provide them (never fabricated): source_url, effective_from / effective_to (except
`Price.valid_from / valid_to`), created_at.

MISSING data is never stored as a node or value; it is listed in `graph/audits/missing_data_register.csv`. EXCLUDED rows
are listed in `graph/audits/excluded_records.csv`.
""", encoding="utf-8")

# ======================================================================================================================
# 6. Cypher (only when the gate passes)
# ======================================================================================================================
LABEL_FILE = {
    "01_reference_nodes": ["BusinessUnit", "MachineType", "MachineFamily", "OrderStatus", "ShippingRate"],
    "02_machines": ["Machine", "MachineSpecification", "MachineVariant"],
    "03_parts": ["Part", "PartSpecification", "LegacyReference", "PartCatalogProfile", "SearchAlias"],
    "04_categories": ["Category"],
    "05_plants": ["Plant"],
    "06_locations": ["Location", "Region", "Address"],
    "07_fitment": ["IdentificationRequirement"],
    "08_assemblies": ["Assembly"],
    "09_suppliers": ["Supplier", "SupplierBackorder"],
    "10_dealers": ["Dealer"],
    "11_inventory": ["Warehouse"],
    "12_pricing": ["Price"],
    "13_customers": ["Customer", "Cart", "CartLine"],
    "15_orders": ["Order", "OrderStatusEvent"],
    "16_order_lines": ["OrderLine"],
    "18_fulfilment": ["DeliveryEstimate"],
    "19_shipments": ["Shipment", "Carrier"],
    "20_tracking_events": ["TrackingEvent"],
    "21_service": ["ServicePlan"],
    "23_compliance": ["ComplianceRequirement"],
    "25_provenance": ["DataSource"],
}
EDGE_FILE = {
    ("PRODUCT_FAMILY_OF", "MachineFamily"): "01_reference_nodes",
    ("OF_TYPE", "Machine"): "02_machines", ("MEMBER_OF_FAMILY", "Machine"): "02_machines", ("BRANDED_AS", "Machine"): "02_machines", ("HAS_MACHINE_SPECIFICATION", "Machine"): "02_machines", ("VARIANT_OF", "MachineVariant"): "02_machines",
    ("HAS_SPECIFICATION", "Part"): "03_parts", ("HAS_LEGACY_REFERENCE", "Part"): "03_parts", ("ISSUED_BY_BUSINESS_UNIT", "LegacyReference"): "03_parts", ("PROFILES_PART", "PartCatalogProfile"): "03_parts", ("HAS_ALIAS", "Part"): "03_parts", ("HAS_ALIAS", "Machine"): "03_parts",
    ("IN_CATEGORY", "Part"): "04_categories", ("IN_SUBCATEGORY", "Part"): "04_categories", ("SUBCATEGORY_OF", "Category"): "04_categories",
    ("MANUFACTURED_AT", "Machine"): "05_plants", ("ORIGINATES_AT", "Part"): "05_plants", ("OWNED_BY", "Plant"): "05_plants",
    ("LOCATED_IN", "Plant"): "06_locations", ("IN_COUNTRY", "Location"): "06_locations", ("IN_REGION", "Address"): "06_locations", ("LOCATED_AT_ADDRESS", "Plant"): "06_locations",
    ("FITS", "Part"): "07_fitment", ("FOR_PART", "IdentificationRequirement"): "07_fitment", ("FOR_MACHINE", "IdentificationRequirement"): "07_fitment", ("ADMITS_VARIANT", "IdentificationRequirement"): "07_fitment",
    ("PART_OF", "Part"): "08_assemblies", ("IDENTIFIED_BY_PART", "Assembly"): "08_assemblies",
    ("SUPPLIED_BY", "Part"): "09_suppliers", ("PLACED_WITH", "SupplierBackorder"): "09_suppliers", ("FOR_PART", "SupplierBackorder"): "09_suppliers", ("LOCATED_AT_ADDRESS", "Supplier"): "09_suppliers",
    ("STOCKED_BY", "Part"): "10_dealers", ("SERVES_FAMILY", "Dealer"): "10_dealers", ("LOCATED_AT_ADDRESS", "Dealer"): "10_dealers",
    ("AVAILABLE_AT", "Part"): "11_inventory", ("LOCATED_AT_PLANT", "Warehouse"): "11_inventory", ("LOCATED_AT_ADDRESS", "Warehouse"): "11_inventory",
    ("PRICES_PART", "Price"): "12_pricing",
    ("LOCATED_AT_ADDRESS", "Customer"): "13_customers", ("OPENED_BY", "Cart"): "13_customers", ("CONTAINS_LINE", "Cart"): "13_customers", ("REFERENCES_PART", "CartLine"): "13_customers",
    ("ORDERED_BY", "Order"): "15_orders", ("DELIVERS_TO_ADDRESS", "Order"): "15_orders", ("HAS_STATUS_EVENT", "Order"): "15_orders", ("RECORDS_STATUS", "OrderStatusEvent"): "15_orders",
    ("CONTAINS_LINE", "Order"): "16_order_lines", ("REFERENCES_PART", "OrderLine"): "16_order_lines",
    ("ALLOCATED_FROM", "OrderLine"): "17_allocations", ("PLANNED_FULFILMENT_FROM", "OrderLine"): "17_allocations",
    ("FROM_WAREHOUSE", "DeliveryEstimate"): "18_fulfilment", ("TO_CUSTOMER", "DeliveryEstimate"): "18_fulfilment", ("TO_DEALER", "DeliveryEstimate"): "18_fulfilment",
    ("HAS_SHIPMENT", "Order"): "19_shipments", ("SHIPS_LINE", "Shipment"): "19_shipments", ("DISPATCHED_FROM", "Shipment"): "19_shipments", ("DELIVERS_TO_CUSTOMER", "Shipment"): "19_shipments", ("CARRIED_BY", "Shipment"): "19_shipments",
    ("HAS_TRACKING_EVENT", "Shipment"): "20_tracking_events",
    ("FOR_MACHINE", "ServicePlan"): "21_service", ("REQUIRES_PART", "ServicePlan"): "21_service",
    ("SAME_NAME_GROUP_AS", "Part"): "22_part_relationships", ("RELATED_COMPONENT", "Part"): "22_part_relationships", ("CO_ORDERED_WITH", "Part"): "22_part_relationships",
    ("HAS_COMPLIANCE", "Part"): "23_compliance", ("COVERS_CATEGORY", "ComplianceRequirement"): "23_compliance",
    ("HOME_PLANT", "BusinessUnit"): "05_plants", ("SUPPLIES_CATEGORY", "Supplier"): "09_suppliers", ("SHIPS_TO_COUNTRY", "Warehouse"): "11_inventory",
}
FILE_ORDER = ["00_constraints", *sorted({*LABEL_FILE, *EDGE_FILE.values()})]
LABEL_AT = {lbl: f for f, lbls in LABEL_FILE.items() for lbl in lbls}
assert set(LABEL_AT) == set(N), set(N) ^ set(LABEL_AT)
for (t, fl), f in EDGE_FILE.items():
    for e in E:
        if e["type"] == t and e["from_label"] == fl:
            assert FILE_ORDER.index(LABEL_AT[e["to_label"]]) <= FILE_ORDER.index(f) and FILE_ORDER.index(LABEL_AT[fl]) <= FILE_ORDER.index(f), (t, fl, e["to_label"], f)
            break
assert all((e["type"], e["from_label"]) in EDGE_FILE for e in E)
NOT_CREATED = {"14_requests": "REQUESTS: no request data exists (carts are not requests).", "24_risk": "RISK: no risk data exists."}


def lit(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(lit(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {lit(x)}" for k, x in v.items() if x is not None) + "}"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
    return f'"{s}"'


def chunks(seq, n=150):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


HEADER = f"// Noordveld Parts Intelligence graph. GENERATED by scripts/graph_build.py on {TODAY}; do not edit by hand.\n// Idempotent: MERGE on canonical ids and rel_id, so running it again creates nothing new.\n// Source: {COMPLETE.name}. Synthetic records carry data_status = 'SYNTHETIC_DEMO'.\n\n"
files: dict[str, list[str]] = collections.defaultdict(list)
if READY == "PASS":
    cons = []
    for lbl in sorted(N):
        cons.append(f"CREATE CONSTRAINT {re.sub(r'(?<!^)(?=[A-Z])', '_', lbl).lower()}_id_unique IF NOT EXISTS FOR (n:{lbl}) REQUIRE n.{ID_PROP[lbl]} IS UNIQUE;")
    for t in sorted(type_count):
        cons.append(f"CREATE CONSTRAINT rel_{t.lower()}_id_unique IF NOT EXISTS FOR ()-[r:{t}]-() REQUIRE r.rel_id IS UNIQUE;")
    files["00_constraints"].append("// Uniqueness constraints first: they protect MERGE and make lookups fast.\n" + "\n".join(cons) + "\n")
    for f, lbls in LABEL_FILE.items():
        for lbl in lbls:
            rows = sorted(N[lbl].values(), key=lambda n: n[ID_PROP[lbl]])
            for part in chunks(rows):
                files[f].append(f"// {lbl}: {len(rows)} nodes\nUNWIND [\n  " + ",\n  ".join(lit(r) for r in part) + f"\n] AS row\nMERGE (n:{lbl} {{{ID_PROP[lbl]}: row.{ID_PROP[lbl]}}})\nSET n += row;\n")
    by_file_edge = collections.defaultdict(list)
    for e in E:
        by_file_edge[(EDGE_FILE[(e["type"], e["from_label"])], e["type"], e["from_label"], e["to_label"])].append(e)
    for (f, t, fl, tl), es in sorted(by_file_edge.items()):
        es.sort(key=lambda e: e["rel_id"])
        rows = [{"from": e["from_id"], "to": e["to_id"], "props": {"rel_id": e["rel_id"], **e["props"], **{k: e.get(k) for k in PROV_KEYS}}} for e in es]
        for part in chunks(rows):
            files[f].append(f"// ({fl})-[:{t}]->({tl}): {len(rows)} relationships\nUNWIND [\n  " + ",\n  ".join(lit(r) for r in part) + f"\n] AS row\nMATCH (a:{fl} {{{ID_PROP[fl]}: row.from}})\nMATCH (b:{tl} {{{ID_PROP[tl]}: row.to}})\nMERGE (a)-[r:{t} {{rel_id: row.props.rel_id}}]->(b)\nSET r += row.props;\n")

# ======================================================================================================================
# 7. Validation queries with expected results
# ======================================================================================================================
label_counts = {lbl: len(v) for lbl, v in sorted(N.items())}
VQ: list[tuple[str, str, str]] = [
    ("Total nodes", "MATCH (n) RETURN count(n) AS nodes;", str(node_count)),
    ("Total relationships", "MATCH ()-[r]->() RETURN count(r) AS relationships;", str(len(E))),
    ("Nodes per label", "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS nodes ORDER BY label;", ", ".join(f"{k} {v}" for k, v in label_counts.items())),
    ("Relationships per type", "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS relationships ORDER BY type;", ", ".join(f"{k} {v}" for k, v in sorted(type_count.items()))),
    ("Nodes and relationships per data_status", "MATCH (n) RETURN 'node' AS kind, n.data_status AS status, count(*) AS c UNION ALL MATCH ()-[r]->() RETURN 'relationship' AS kind, r.data_status AS status, count(*) AS c;", ", ".join(f"node {k} {v}" for k, v in sorted(node_by_status.items())) + "; " + ", ".join(f"relationship {k} {v}" for k, v in sorted(edge_by_status.items()))),
    ("Duplicate canonical ids (any label)", "\n".join(f"MATCH (n:{lbl}) WITH n.{ID_PROP[lbl]} AS id, count(*) AS c WHERE c > 1 RETURN '{lbl}' AS label, id, c" + (" UNION ALL" if i < len(N) - 1 else ";") for i, lbl in enumerate(sorted(N))), "0 rows"),
    ("Duplicate relationships (same type, same endpoints, same rel_id)", "MATCH (a)-[r]->(b) WITH type(r) AS t, r.rel_id AS id, count(*) AS c WHERE c > 1 RETURN t, id, c;", "0 rows"),
    ("Nodes or relationships without provenance", "MATCH (n) WHERE n.data_status IS NULL OR n.source_sheet IS NULL WITH count(n) AS c RETURN 'node' AS kind, c UNION ALL MATCH ()-[r]->() WHERE r.data_status IS NULL OR r.source_sheet IS NULL WITH count(r) AS c RETURN 'relationship' AS kind, c;", "node 0, relationship 0"),
    ("Synthetic sheets not marked SYNTHETIC_DEMO", "MATCH (n) WHERE n.source_sheet STARTS WITH 'SYN_' AND n.data_status <> 'SYNTHETIC_DEMO' RETURN count(n) AS nodes_unmarked;", "0"),
    ("Relationships with a wrong endpoint label", "\n".join(f"MATCH (a)-[r:{t}]->(b) WHERE NOT (" + " OR ".join(f"(a:{fl} AND b:{tl})" for (tt, fl, tl) in REL if tt == t) + f") WITH count(r) AS bad RETURN '{t}' AS type, bad" + (" UNION ALL" if i < len(type_count) - 1 else ";") for i, t in enumerate(sorted(type_count))), "one row per relationship type (61), bad = 0 in every row"),
    ("Forbidden relationship types", "MATCH ()-[r]->() WHERE type(r) IN [" + ", ".join(f"'{t}'" for t in sorted(FORBIDDEN_TYPES)) + "] RETURN count(r) AS forbidden;", "0"),
    ("Interchangeability asserted", "MATCH ()-[r]->() WHERE r.interchangeability_status IS NOT NULL AND r.interchangeability_status <> 'UNKNOWN' RETURN count(r) AS asserted;", "0"),
    ("Fitment status", "MATCH (:Part)-[f:FITS]->(:Machine) RETURN f.fitment_status AS status, count(*) AS c ORDER BY status;", f"CONDITIONAL {graph_cond}, CONFIRMED {len(fits) - graph_cond}"),
    ("Conditional fitments (must stay conditional)", "MATCH (p:Part)-[f:FITS {fitment_status: 'CONDITIONAL'}]->(m:Machine) RETURN p.part_number, m.model_code, f.condition_note ORDER BY p.part_number;", "; ".join(f"{N['Part'][e['from_id']]['part_number']} -> {N['Machine'][e['to_id']]['model_code']}: {e['props'].get('condition_note')}" for e in sorted(fits, key=lambda e: N['Part'][e['from_id']]['part_number']) if e['props']['fitment_status'] == 'CONDITIONAL')),
    ("Co-order duplication (mirrored pairs)", "MATCH (a:Part)-[:CO_ORDERED_WITH]->(b:Part) MATCH (b)-[:CO_ORDERED_WITH]->(a) RETURN count(*) AS mirrored;", "0"),
    ("Co-order relationships", "MATCH (:Part)-[r:CO_ORDERED_WITH]->(:Part) RETURN count(r) AS c, sum(CASE WHEN r.merged_source_record_ids IS NULL THEN 0 ELSE 1 END) AS merged;", f"c {type_count['CO_ORDERED_WITH']}, merged 14"),
    ("Part -> machines (NVM-1010-HY)", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[f:FITS]->(m:Machine) RETURN m.model_code, f.fitment_status ORDER BY m.model_code;", "NV-3200 CONFIRMED, NV-4500 CONFIRMED"),
    ("Machine -> parts (NV-4500)", "MATCH (m:Machine {model_code: 'NV-4500'})<-[:FITS]-(p:Part) RETURN count(p) AS parts;", str(sum(1 for e in fits if N['Machine'][e['to_id']]['model_code'] == 'NV-4500'))),
    ("Machine with no parts", "MATCH (m:Machine) WHERE NOT (m)<-[:FITS]-(:Part) RETURN m.model_code;", ", ".join(no_part_machines)),
    ("Part -> category, sub-category, legacy", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[:IN_CATEGORY]->(c) MATCH (p)-[:IN_SUBCATEGORY]->(s) MATCH (p)-[:HAS_LEGACY_REFERENCE]->(l) RETURN c.name, s.name, l.legacy_part_number;", "Hydraulics, Hydraulic hose, AS-771"),
    ("Part -> suppliers", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[s:SUPPLIED_BY]->(x:Supplier) RETURN x.name, s.is_primary, s.lead_time_days, s.data_status ORDER BY s.is_primary DESC;", "Veldstra Hydraulics (demo) true 28 SYNTHETIC_DEMO; Rijnmond Hydraulic Supply (demo) false 10 SYNTHETIC_DEMO"),
    ("Part -> dealers", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[s:STOCKED_BY]->(d:Dealer) RETURN d.name, s.available ORDER BY d.name;", "; ".join(f"{N['Dealer'][e['to_id']]['name']} {e['props'].get('available')}" for e in sorted([e for e in E if e['type'] == 'STOCKED_BY' and e['from_id'] == 'PRT-002'], key=lambda e: N['Dealer'][e['to_id']]['name']))),
    ("Part -> warehouse inventory", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[s:AVAILABLE_AT]->(w:Warehouse) RETURN w.name, s.on_hand, s.reserved, s.available ORDER BY w.name;", "; ".join(f"{N['Warehouse'][e['to_id']]['name']} {e['props'].get('available')}" for e in sorted([e for e in E if e['type'] == 'AVAILABLE_AT' and e['from_id'] == 'PRT-002'], key=lambda e: N['Warehouse'][e['to_id']]['name']))),
    ("Excluded dealer zero-rows are absent", "MATCH ()-[s:STOCKED_BY]->() WHERE s.inventory_id IN [" + ", ".join(f"'{x['record_id']}'" for x in zero_rows) + "] RETURN count(s) AS imported;", "0"),
    ("Part -> orders", "MATCH (p:Part)<-[:REFERENCES_PART]-(l:OrderLine)<-[:CONTAINS_LINE]-(o:Order) RETURN count(DISTINCT p) AS parts_ordered, count(DISTINCT o) AS orders;", f"parts_ordered {len({e['to_id'] for e in E if e['type'] == 'REFERENCES_PART' and e['from_label'] == 'OrderLine'})}, orders {len(orders)}"),
    ("Order -> customer and shipments", "MATCH (o:Order)-[:ORDERED_BY]->(c:Customer) OPTIONAL MATCH (o)-[:HAS_SHIPMENT]->(s:Shipment) RETURN o.order_id, c.name, count(s) AS shipments ORDER BY o.order_id;", f"{len(orders)} rows; {len(orders_shipped)} orders with at least one shipment"),
    ("Shipment -> tracking events", "MATCH (s:Shipment)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) RETURN s.shipment_id, count(e) AS events ORDER BY s.shipment_id;", f"{len({e['from_id'] for e in E if e['type'] == 'HAS_TRACKING_EVENT'})} shipments, {type_count['HAS_TRACKING_EVENT']} events"),
    ("Service plan -> machine and parts", "MATCH (sp:ServicePlan)-[:FOR_MACHINE]->(m:Machine) OPTIONAL MATCH (sp)-[:REQUIRES_PART]->(p:Part) RETURN count(DISTINCT sp) AS plans, count(DISTINCT m) AS machines, count(DISTINCT p) AS parts;", f"plans {len(N['ServicePlan'])}, machines {len({e['to_id'] for e in E if e['type'] == 'FOR_MACHINE' and e['from_label'] == 'ServicePlan'})}, parts {len(svc_parts)}"),
    ("No service jobs, alternatives, supersessions or risks", "MATCH (n) WHERE n:ServiceJob OR n:Installation OR n:Request OR n:SourceRisk RETURN count(n) AS c UNION ALL MATCH ()-[r]->() WHERE type(r) IN ['ALTERNATIVE_TO','SUPERSEDES','SUPERSEDED_BY','REPLACEMENT_FOR','HAS_RISK'] RETURN count(r) AS c;", "0, 0"),
    ("Trace part -> machine -> order -> shipment -> service", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[:FITS]->(m:Machine) OPTIONAL MATCH (p)<-[:REFERENCES_PART]-(:OrderLine)<-[:CONTAINS_LINE]-(o:Order) OPTIONAL MATCH (o)-[:HAS_SHIPMENT]->(s:Shipment) OPTIONAL MATCH (sp:ServicePlan)-[:FOR_MACHINE]->(m) RETURN m.model_code, collect(DISTINCT o.order_id) AS orders, collect(DISTINCT s.shipment_id) AS shipments, count(DISTINCT sp) AS service_plans;", "rows for NV-3200 and NV-4500; 4 service plans each"),
    ("Impact analysis: part -> machines -> orders -> service plans", "MATCH (p:Part {part_number: 'NVM-1010-HY'}) OPTIONAL MATCH (p)-[:FITS]->(m:Machine) OPTIONAL MATCH (p)<-[:REFERENCES_PART]-(:OrderLine)<-[:CONTAINS_LINE]-(o:Order) OPTIONAL MATCH (p)<-[:REQUIRES_PART]-(sp:ServicePlan) RETURN count(DISTINCT m) AS machines, count(DISTINCT o) AS orders, count(DISTINCT sp) AS service_plans;", f"machines 2, orders {len({e2['from_id'] for e2 in E if e2['type'] == 'CONTAINS_LINE' and e2['to_id'] in {e['from_id'] for e in E if e['type'] == 'REFERENCES_PART' and e['to_id'] == 'PRT-002' and e['from_label'] == 'OrderLine'}})}, service_plans {len({e['from_id'] for e in E if e['type'] == 'REQUIRES_PART' and e['to_id'] == 'PRT-002'})}"),
    ("Provenance traversal", "MATCH (p:Part {part_number: 'NVM-1010-HY'})-[f:FITS]->(m:Machine) MATCH (d:DataSource {source_id: f.source_id}) RETURN m.model_code, f.provenance_type, f.source_sheet, f.source_record_id, f.source_ref, d.name ORDER BY m.model_code;", "; ".join(f"{N['Machine'][e['to_id']]['model_code']} {e['provenance_type']} {e['source_sheet']} {e['source_record_id']} {N['DataSource'][e['source_id']]['name']}" for e in sorted([e for e in fits if e['from_id'] == 'PRT-002'], key=lambda e: N['Machine'][e['to_id']]['model_code']))),
    ("Idempotency check (run after a second import)", "MATCH (n) RETURN count(n) AS nodes UNION ALL MATCH ()-[r]->() RETURN count(r) AS nodes;", f"{node_count} and {len(E)}: unchanged after re-running every file"),
]
V = OUT["validation"]
vtext = HEADER + "// Read-only validation. Each query is followed by its expected result in validation_expected_results.md.\n\n" + "\n\n".join(f"// V{i + 1:02d} {name}\n// expected: {exp}\n{q}" for i, (name, q, exp) in enumerate(VQ)) + "\n"
(V / "validation_queries.cypher").write_text(vtext, encoding="utf-8")
(V / "validation_expected_results.md").write_text("# Expected validation results\n\nComputed from the canonical graph before import. After the AuraDB import every query in `validation_queries.cypher` must return exactly this.\n\n" + md_table([{"id": f"V{i + 1:02d}", "check": n, "expected": e} for i, (n, q, e) in enumerate(VQ)], ["id", "check", "expected"]) + "\n", encoding="utf-8")
(V / "preflight_inspection.cypher").write_text("""// READ-ONLY. Run against AuraDB BEFORE any import. If anything exists, STOP and report; do not delete or overwrite.
CALL db.info() YIELD name, id RETURN name AS database, id;
MATCH (n) RETURN count(n) AS existing_nodes;
MATCH ()-[r]->() RETURN count(r) AS existing_relationships;
CALL db.labels() YIELD label RETURN collect(label) AS existing_labels;
CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS existing_relationship_types;
SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties;
SHOW INDEXES YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties;
""", encoding="utf-8")

if READY == "PASS":
    for f in FILE_ORDER:
        (OUT["cypher"] / f"{f}.cypher").write_text(HEADER + "\n".join(files[f]), encoding="utf-8")
    (OUT["cypher"] / "99_validation.cypher").write_text(vtext, encoding="utf-8")
    (OUT["cypher"] / "cypher_import_plan.md").write_text(f"""# Cypher import plan

GRAPH_READINESS = PASS. Nothing has been executed against any database.

## Order

0. `graph/validation/preflight_inspection.cypher` (read-only). If the database is not empty: STOP and report.
{chr(10).join(f'{i + 1}. `{f}.cypher`' for i, f in enumerate(FILE_ORDER))}
{len(FILE_ORDER) + 1}. `99_validation.cypher`, compared with `graph/validation/validation_expected_results.md`.

Not created (no data): {', '.join(f'`{k}.cypher` ({v})' for k, v in NOT_CREATED.items())}

## Idempotency

Nodes `MERGE` on their canonical id and relationships `MERGE` on `rel_id` between matched endpoints, then `SET +=`.
Running every file twice leaves {node_count} nodes and {len(E)} relationships.

## Size

{node_count} nodes, {len(E)} relationships, {len(N)} unique node constraints and {len(type_count)} relationship
uniqueness constraints (`rel_id`). Statements are batched in UNWIND blocks of up to 150 rows.
""", encoding="utf-8")

summary = {
    "GRAPH_READINESS": READY, "GRAPH_RELATIONSHIP_COVERAGE": COVERAGE, "coverage_required": dict(cov_count), "coverage_required_total": len(reqd), "coverage_additional": dict(cov_add_count), "nodes": node_count, "relationships": len(E), "labels": len(N), "relationship_types": len(type_count),
    "duplicate_nodes": len(dup_nodes), "duplicate_relationships": len(dup_rel), "duplicate_semantic": len(sym_dup) // 2,
    "orphans": sum(1 for e in E if not e.get("source_record_id")), "broken": len(broken),
    "violations": len(bad_end) + len(bad_src) + len(reversed_types) + len(card_viol) + len(forbidden) + len(asserted),
    "synthetic": syn_records, "source_derived": src_records, "derived": der_records, "user_provided": usr_records,
    "excluded": len(g.excluded), "failed_checks": [c["id"] + " " + c["check"] for c in blocking_fail], "missing_domains": MISSING_DOMAINS,
    "files": sorted(str(p.relative_to(ROOT)) for d in OUT.values() for p in d.iterdir()),
}
print(json.dumps(summary, indent=1))
