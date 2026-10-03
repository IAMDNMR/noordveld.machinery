"""Read-only post-import validation of the AuraDB graph against the offline model. Never writes; never prints credentials.

Runs: (1) every query of graph/cypher/99_validation.cypher against graph/validation/validation_expected_results.md,
(2) coverage: every row of graph/audits/relationship_coverage_matrix.csv re-counted in AuraDB,
(3) semantic, synthetic, provenance and missing-data checks, (4) 23 representative traversals.
Results go to graph/audits/aura_validation_results.json.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_coverage import CV  # noqa: E402
import aura_import as A  # noqa: E402

from graph_audit_lib import AUDITS, CYPHER, VALIDATION  # noqa: E402

OUTFILE = AUDITS / "aura_validation_results.json"
RESULTS: dict = {"checks": [], "coverage": [], "traversals": []}


def q(session, cypher: str):
    return [r.data() for r in session.run(cypher)]


def rec(group: str, cid: str, name: str, ok: bool, expected, actual) -> None:
    RESULTS[group].append({"id": cid, "check": name, "status": "PASS" if ok else "FAIL", "expected": expected, "actual": actual})
    print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {name}" + ("" if ok else f"\n        expected: {str(expected)[:200]}\n        actual:   {str(actual)[:200]}"))


def parse_counts(text: str) -> dict[str, int]:
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"([A-Za-z_]+(?: [A-Z_]+)?) (\d+)(?:,|$)", text.strip().rstrip("."))}


def expected_table() -> dict[str, tuple[str, str]]:
    out = {}
    for line in (VALIDATION / "validation_expected_results.md").read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.split("|")]
        if len(c) > 4 and re.match(r"V\d\d", c[1]):
            out[c[1]] = (c[2], c[3])
    return out


def queries() -> dict[str, tuple[str, str]]:
    text = (CYPHER / "99_validation.cypher").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"// (V\d\d) (.+?)\n// expected: (.*?)\n(.*?;)(?=\n\n// V|\n*\Z)", text, re.S):
        out[m.group(1)] = (m.group(2), m.group(4).strip())
    return out


def main() -> int:
    driver = A.connect()
    exp = expected_table()
    qs = queries()
    s = driver.session(database=A.DB, default_access_mode=A.READ_ACCESS)
    print(f"validation queries parsed: {len(qs)} of {len(exp)} expected rows")

    # ---------------- 1. the generated validation package ----------------
    print("1. graph/cypher/99_validation.cypher against validation_expected_results.md")
    R = {cid: q(s, cy) for cid, (name, cy) in qs.items()}
    E = {cid: v[1] for cid, v in exp.items()}
    rec("checks", "V01", "Total nodes", R["V01"][0]["nodes"] == 1840, 1840, R["V01"][0]["nodes"])
    rec("checks", "V02", "Total relationships", R["V02"][0]["relationships"] == 3812, 3812, R["V02"][0]["relationships"])
    act = {r["label"]: r["nodes"] for r in R["V03"]}
    want = {k: v for k, v in parse_counts(E["V03"]).items()}
    rec("checks", "V03", "Nodes per label", act == want, want, act)
    act = {r["type"]: r["relationships"] for r in R["V04"]}
    want = parse_counts(E["V04"])
    rec("checks", "V04", "Relationships per type", act == want, f"{len(want)} types", f"{len(act)} types; differences {sorted(set(act.items()) ^ set(want.items()))[:6]}")
    act = sorted(f"{r['kind']} {r['status']} {r['c']}" for r in R["V05"])
    want = sorted(x.strip() for x in E["V05"].split(";")[0].split(",") + E["V05"].split(";")[1].split(","))
    want = sorted(re.sub(r"^\s*", "", w) for w in want)
    rec("checks", "V05", "Counts per data_status", act == want, want, act)
    rec("checks", "V06", "Duplicate canonical ids", len(R["V06"]) == 0, "0 rows", R["V06"][:3])
    rec("checks", "V07", "Duplicate relationships", len(R["V07"]) == 0, "0 rows", R["V07"][:3])
    rec("checks", "V08", "Missing provenance", {r["kind"]: r["c"] for r in R["V08"]} == {"node": 0, "relationship": 0}, "node 0, relationship 0", R["V08"])
    rec("checks", "V09", "Synthetic sheets not marked", R["V09"][0]["nodes_unmarked"] == 0, 0, R["V09"])
    rec("checks", "V10", "Wrong endpoint labels", all(r["bad"] == 0 for r in R["V10"]) and len(R["V10"]) == 61, "61 types, bad = 0", f"{len(R['V10'])} types, bad total {sum(r['bad'] for r in R['V10'])}")
    rec("checks", "V11", "Forbidden relationship types", R["V11"][0]["forbidden"] == 0, 0, R["V11"])
    rec("checks", "V12", "Interchangeability asserted", R["V12"][0]["asserted"] == 0, 0, R["V12"])
    rec("checks", "V13", "Fitment status", {r["status"]: r["c"] for r in R["V13"]} == {"CONDITIONAL": 3, "CONFIRMED": 216}, "CONDITIONAL 3, CONFIRMED 216", R["V13"])
    act = sorted(f"{r['p.part_number']} -> {r['m.model_code']}: {r['f.condition_note']}" for r in R["V14"])
    want = sorted(x.strip() for x in E["V14"].split("; "))
    rec("checks", "V14", "Conditional fitments", act == want, want, act)
    rec("checks", "V15", "Mirrored co-order pairs", R["V15"][0]["mirrored"] == 0, 0, R["V15"])
    rec("checks", "V16", "Co-order relationships", (R["V16"][0]["c"], R["V16"][0]["merged"]) == (75, 14), "c 75, merged 14", R["V16"])
    rec("checks", "V17", "Part -> machines", sorted(f"{r['m.model_code']} {r['f.fitment_status']}" for r in R["V17"]) == ["NV-3200 CONFIRMED", "NV-4500 CONFIRMED"], E["V17"], R["V17"])
    rec("checks", "V18", "Machine -> parts (NV-4500)", R["V18"][0]["parts"] == 52, 52, R["V18"])
    rec("checks", "V19", "Machine with no parts", [r["m.model_code"] for r in R["V19"]] == ["KFT-120"], "KFT-120", R["V19"])
    r = R["V20"][0] if R["V20"] else {}
    rec("checks", "V20", "Part -> category, sub-category, legacy", (r.get("c.name"), r.get("s.name"), r.get("l.legacy_part_number")) == ("Hydraulics", "Hydraulic hose", "AS-771"), E["V20"], R["V20"])
    act = [f"{r['x.name']} {str(r['s.is_primary']).lower()} {r['s.lead_time_days']} {r['s.data_status']}" for r in R["V21"]]
    rec("checks", "V21", "Part -> suppliers", act == E["V21"].split("; "), E["V21"], act)
    act = [f"{r['d.name']} {r['s.available']}" for r in R["V22"]]
    rec("checks", "V22", "Part -> dealers", act == E["V22"].split("; "), E["V22"], act)
    act = [f"{r['w.name']} {r['s.available']}" for r in R["V23"]]
    rec("checks", "V23", "Part -> warehouse inventory", act == E["V23"].split("; "), E["V23"], act)
    rec("checks", "V24", "Excluded dealer zero-rows absent", R["V24"][0]["imported"] == 0, 0, R["V24"])
    rec("checks", "V25", "Part -> orders", (R["V25"][0]["parts_ordered"], R["V25"][0]["orders"]) == (14, 8), E["V25"], R["V25"])
    with_ship = sum(1 for r in R["V26"] if r["shipments"] > 0)
    rec("checks", "V26", "Order -> customer and shipments", len(R["V26"]) == 8 and with_ship == 4, E["V26"], f"{len(R['V26'])} rows; {with_ship} with shipments")
    rec("checks", "V27", "Shipment -> tracking events", (len(R["V27"]), sum(r["events"] for r in R["V27"])) == (9, 27), E["V27"], f"{len(R['V27'])} shipments, {sum(r['events'] for r in R['V27'])} events")
    r = R["V28"][0]
    rec("checks", "V28", "Service plan -> machine and parts", (r["plans"], r["machines"], r["parts"]) == (60, 15, 33), E["V28"], R["V28"])
    rec("checks", "V29", "No service jobs / alternatives / supersessions / risks", [r["c"] for r in R["V29"]] == [0, 0], "0, 0", R["V29"])
    ok30 = sorted(r["m.model_code"] for r in R["V30"]) == ["NV-3200", "NV-4500"] and all(r["service_plans"] == 4 for r in R["V30"])
    rec("checks", "V30", "Trace part -> machine -> order -> shipment -> service", ok30, E["V30"], R["V30"])
    r = R["V31"][0]
    rec("checks", "V31", "Impact analysis", (r["machines"], r["orders"], r["service_plans"]) == (2, 0, 1), E["V31"], R["V31"])
    act = sorted(f"{r['m.model_code']} {r['f.provenance_type']} {r['f.source_sheet']} {r['f.source_record_id']} {r['d.name']}" for r in R["V32"])
    rec("checks", "V32", "Provenance traversal", act == sorted(E["V32"].split("; ")), E["V32"], act)
    n, rl = A.totals(driver)
    rec("checks", "V33", "Totals (idempotency reference)", (n, rl) == (1840, 3812), "1840 and 3812", [n, rl])

    # ---------------- 2. coverage: every row of the matrix re-counted in AuraDB ----------------
    print("2. relationship coverage matrix re-counted in AuraDB")
    matrix = list(csv.DictReader((AUDITS / "relationship_coverage_matrix.csv").open(encoding="utf-8")))
    assert len(matrix) == len(CV)
    bad = 0
    absent_labels = ["ServiceJob", "Installation", "Request", "SourceRisk", "Configuration", "Allocation", "Fulfilment", "MachineUnit", "SerialNumberedMachine"]
    absent_types = ["ALTERNATIVE_TO", "SUPERSEDES", "SUPERSEDED_BY", "REPLACEMENT_FOR", "INTERCHANGEABLE_WITH", "HAS_RISK", "INSTALLED_ON", "REQUESTED_BY", "RELATED_TO", "CONNECTED_TO", "ASSOCIATED_WITH", "LINKED_TO", "HAS", "BELONGS_TO"]
    for (grp, domain, src, rel, tgt, status, keys, note, missing), row in zip(CV, matrix):
        count = 0
        for t, f, to in keys:
            count += s.run(f"MATCH (a:{f})-[r:{t}]->(b:{to}) RETURN count(r) AS c").single()["c"]
        ok = count == int(row["RECORD_COUNT"]) and (count > 0 if status.startswith("IMPLEMENTED") else count == 0)
        bad += not ok
        RESULTS["coverage"].append({"group": grp, "source": src, "relationship": rel, "target": tgt, "status": status, "offline_count": int(row["RECORD_COUNT"]), "aura_count": count, "match": ok})
    print(f"  {len(CV) - bad} of {len(CV)} coverage rows match the offline model ({sum(1 for r in RESULTS['coverage'] if r['group'] == 'REQUIRED')} required, {sum(1 for r in RESULTS['coverage'] if r['group'] == 'ADDITIONAL')} source-discovered)")
    rec("checks", "C01", "Every coverage-matrix row matches AuraDB", bad == 0, f"{len(CV)} of {len(CV)}", f"{len(CV) - bad} of {len(CV)}")
    new = {"HOME_PLANT": 3, "SUPPLIES_CATEGORY": 25, "COVERS_CATEGORY": 10, "SHIPS_TO_COUNTRY": 8}
    act = {t: s.run(f"MATCH ()-[r:{t}]->() RETURN count(r) AS c").single()["c"] for t in new}
    rec("checks", "C02", "Newly added relationships exist with the right counts", act == new, new, act)
    for t, a, b in (("HOME_PLANT", "BusinessUnit", "Plant"), ("SUPPLIES_CATEGORY", "Supplier", "Category"), ("COVERS_CATEGORY", "ComplianceRequirement", "Category"), ("SHIPS_TO_COUNTRY", "Warehouse", "Location")):
        c = s.run(f"MATCH (a:{a})-[r:{t}]->(b:{b}) RETURN count(r) AS c").single()["c"]
        rec("checks", f"C02-{t}", f"({a})-[:{t}]->({b}) endpoints correct", c == new[t], new[t], c)
    lab = {l: s.run(f"MATCH (n:{l}) RETURN count(n) AS c").single()["c"] for l in absent_labels}
    typ = {t: s.run(f"MATCH ()-[r:{t}]->() RETURN count(r) AS c").single()["c"] for t in absent_types}
    rec("checks", "C03", "Schema-only labels have no records", all(v == 0 for v in lab.values()), "all 0", lab)
    rec("checks", "C04", "Schema-only / generic relationship types have no records", all(v == 0 for v in typ.values()), "all 0", {k: v for k, v in typ.items() if v})

    # ---------------- 3. semantics ----------------
    print("3. semantic validation (nothing inferred)")
    one = lambda cy: s.run(cy).single()  # noqa: E731
    r = one("MATCH (su:Supplier)-[:SUPPLIES_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(p:Part) WHERE NOT (p)-[:SUPPLIED_BY]->(su) RETURN count(*) AS declared_only, count(DISTINCT su) AS suppliers")
    sup_total = one("MATCH (:Part)-[r:SUPPLIED_BY]->(:Supplier) RETURN count(r) AS c")["c"]
    rec("checks", "S01", "SUPPLIES_CATEGORY does not imply supplying every part: supplier-category-part triples with no SUPPLIED_BY exist, and SUPPLIED_BY is unchanged", r["declared_only"] > 0 and sup_total == 157, "declared_only > 0 and SUPPLIED_BY = 157", {"declared_only_pairs": r["declared_only"], "supplied_by": sup_total})
    types = [x["t"] for x in q(s, "MATCH (:Supplier)-[r]-(:Part) RETURN DISTINCT type(r) AS t")]
    rec("checks", "S02", "The only Supplier-Part relationship is SUPPLIED_BY (no supply inferred from category or location)", types == ["SUPPLIED_BY"], ["SUPPLIED_BY"], types)
    r = one("MATCH (c:ComplianceRequirement)-[:COVERS_CATEGORY]->(cat:Category)<-[:IN_CATEGORY]-(p:Part) WHERE NOT (p)-[:HAS_COMPLIANCE]->(c) RETURN count(*) AS declared_only")
    hc = one("MATCH (:Part)-[r:HAS_COMPLIANCE]->(:ComplianceRequirement) RETURN count(r) AS c, count(DISTINCT r.source_sheet) AS sheets, collect(DISTINCT r.source_sheet)[0] AS sheet")
    rec("checks", "S03", "COVERS_CATEGORY is separate from part-level HAS_COMPLIANCE (the latter only from SYN_part_compliance rows, 100)", hc["c"] == 100 and hc["sheet"] == "SYN_part_compliance", "100 from SYN_part_compliance", {"has_compliance": hc["c"], "sheet": hc["sheet"], "category_scope_without_explicit_part_link": r["declared_only"]})
    r = one("MATCH (w:Warehouse)-[:SHIPS_TO_COUNTRY]->(l:Location) MATCH (w)-[:LOCATED_AT_ADDRESS]->(a:Address) WHERE l.country_code <> a.country_code RETURN count(*) AS ships_to_other_country")
    only = [x["t"] for x in q(s, "MATCH (:Warehouse)-[r]->(:Location) RETURN DISTINCT type(r) AS t")]
    rec("checks", "S04", "SHIPS_TO_COUNTRY is not 'located in': warehouses ship to countries other than their own, and it is their only link to a Location", r["ships_to_other_country"] > 0 and only == ["SHIPS_TO_COUNTRY"], "> 0 and only SHIPS_TO_COUNTRY", {"ships_to_other_country": r["ships_to_other_country"], "warehouse_location_types": only})
    homes = {x["b"]: x["p"] for x in q(s, "MATCH (b:BusinessUnit)-[:HOME_PLANT]->(p:Plant) RETURN b.business_unit_id AS b, p.plant_id AS p")}
    rec("checks", "S05", "HOME_PLANT = the business unit's home plant", homes == {"BU-NOORDVELD": "PLT-001", "BU-KESSLER": "PLT-002", "BU-BAKKER": "PLT-003"}, "NOORDVELD->PLT-001, KESSLER->PLT-002, BAKKER->PLT-003", homes)
    r = one("MATCH (l:OrderLine) OPTIONAL MATCH (l)-[a:ALLOCATED_FROM]->() OPTIONAL MATCH (l)-[p:PLANNED_FULFILMENT_FROM]->() RETURN count(l) AS lines, sum(CASE WHEN a IS NOT NULL AND p IS NOT NULL THEN 1 ELSE 0 END) AS both, sum(CASE WHEN a IS NOT NULL AND NOT a.allocation_status IN ['RESERVED','SHIPPED'] THEN 1 ELSE 0 END) AS bad_alloc, sum(CASE WHEN p IS NOT NULL AND p.allocation_status IN ['RESERVED','SHIPPED'] THEN 1 ELSE 0 END) AS bad_plan")
    rec("checks", "S06", "PLANNED_FULFILMENT_FROM is never an allocation (no line has both; planned lines are not RESERVED/SHIPPED)", (r["both"], r["bad_alloc"], r["bad_plan"]) == (0, 0, 0), "0, 0, 0", dict(r))
    r = one("MATCH ()-[f:FITS {fitment_status:'CONDITIONAL'}]->() RETURN count(f) AS c, count(f.condition_note) AS with_note")
    rec("checks", "S07", "CONDITIONAL fitments stay conditional with their condition", (r["c"], r["with_note"]) == (3, 3), "3 conditional, 3 with condition_note", dict(r))
    r = one("MATCH ()-[r:SAME_NAME_GROUP_AS|RELATED_COMPONENT]->() RETURN count(r) AS c, sum(CASE WHEN r.interchangeability_status = 'UNKNOWN' THEN 1 ELSE 0 END) AS unknown")
    rec("checks", "S08", "SAME_NAME_GROUP_AS / RELATED_COMPONENT carry interchangeability_status UNKNOWN (11 of 11), not alternatives", (r["c"], r["unknown"]) == (11, 11), "11 of 11 UNKNOWN", dict(r))

    # ---------------- 4. synthetic + provenance ----------------
    print("4. synthetic and provenance classes")
    nodes = {r["status"]: r["c"] for r in q(s, "MATCH (n) RETURN n.data_status AS status, count(*) AS c")}
    rels = {r["status"]: r["c"] for r in q(s, "MATCH ()-[r]->() RETURN r.data_status AS status, count(*) AS c")}
    syn = nodes.get("SYNTHETIC_DEMO", 0) + rels.get("SYNTHETIC_DEMO", 0)
    rec("checks", "P01", "Synthetic records = 3,846, all SYNTHETIC_DEMO", syn == 3846, 3846, {"nodes": nodes.get("SYNTHETIC_DEMO"), "relationships": rels.get("SYNTHETIC_DEMO"), "total": syn})
    classes = {k: nodes.get(k, 0) + rels.get(k, 0) for k in ("SOURCE_DERIVED", "DERIVED", "USER_PROVIDED", "SYNTHETIC_DEMO")}
    rec("checks", "P02", "Provenance classes stay distinct and complete", classes == {"SOURCE_DERIVED": 1234, "DERIVED": 556, "USER_PROVIDED": 16, "SYNTHETIC_DEMO": 3846} and set(nodes) | set(rels) == set(classes), "SOURCE_DERIVED 1234, DERIVED 556, USER_PROVIDED (project brief) 16, SYNTHETIC_DEMO 3846", classes)
    r = one("MATCH (n) WHERE n.source_sheet STARTS WITH 'SYN_' AND n.data_status <> 'SYNTHETIC_DEMO' RETURN count(n) AS c")
    r2 = one("MATCH ()-[x]->() WHERE x.source_sheet STARTS WITH 'SYN_' AND x.data_status <> 'SYNTHETIC_DEMO' RETURN count(x) AS c")
    rec("checks", "P03", "No SYN_ record is unmarked", (r["c"], r2["c"]) == (0, 0), "0, 0", [r["c"], r2["c"]])
    r = one("MATCH (n) WHERE NOT n.source_sheet STARTS WITH 'SYN_' AND n.data_status = 'SYNTHETIC_DEMO' RETURN count(n) AS c")
    rec("checks", "P04", "No catalogue record is labelled synthetic", r["c"] == 0, 0, r["c"])
    keys = {k for x in q(s, "MATCH (p:Part) UNWIND keys(p) AS k RETURN DISTINCT k") for k in x.values()}
    leaked = keys & {"list_price_ex_vat", "availability_state", "orderable", "weight_kg", "warranty_months", "return_window_days", "image_path", "status_reason", "stock", "price"}
    rec("checks", "P05", "Catalogue Part carries no synthetic operational values (price, stock, availability...)", not leaked, "none", sorted(leaked))
    dom = {}
    for label in ("Supplier", "Dealer", "Warehouse", "Price", "Order", "Shipment", "ServicePlan", "ComplianceRequirement", "TrackingEvent", "OrderLine"):
        dom[label] = [x["status"] for x in q(s, f"MATCH (n:{label}) RETURN DISTINCT n.data_status AS status")]
    for rtype in ("AVAILABLE_AT", "STOCKED_BY", "SUPPLIED_BY", "HAS_COMPLIANCE", "HAS_SHIPMENT", "REQUIRES_PART"):
        dom[rtype] = [x["status"] for x in q(s, f"MATCH ()-[r:{rtype}]->() RETURN DISTINCT r.data_status AS status")]
    rec("checks", "P06", "Supplier, Dealer, Warehouse, Price, Order, Shipment, ServicePlan, Compliance, Tracking, stock and sourcing relationships all SYNTHETIC_DEMO", all(v == ["SYNTHETIC_DEMO"] for v in dom.values()), "all ['SYNTHETIC_DEMO']", {k: v for k, v in dom.items() if v != ["SYNTHETIC_DEMO"]})
    r = one("MATCH (p:Part)-[f:FITS]->() WHERE f.provenance_type <> 'SOURCE_DERIVED' RETURN count(f) AS c")
    rec("checks", "P07", "Every FITS relationship is SOURCE_DERIVED", r["c"] == 0, 0, r["c"])

    # ---------------- 5. missing data kept missing ----------------
    print("5. missing data preserved")
    r = one("MATCH (l:LegacyReference) WHERE l.legacy_part_number IS NULL RETURN count(l) AS c")
    rec("checks", "M01", "5 unresolved legacy references stay without a legacy number", r["c"] == 5, 5, r["c"])
    r = one("MATCH (w:Warehouse {warehouse_id:'WH-004'}) OPTIONAL MATCH (w)-[p:LOCATED_AT_PLANT]->() RETURN count(p) AS c")
    rec("checks", "M02", "WH-004 has no plant", r["c"] == 0, 0, r["c"])
    r = one("MATCH (l:Location) WHERE l.country_code = 'BE' RETURN count(l) AS c")
    r2 = one("MATCH ()-[r:SHIPS_TO_COUNTRY]->(l:Location) RETURN count(r) AS c, count(DISTINCT l.country_code) AS countries, collect(DISTINCT l.country_code) AS codes")
    rec("checks", "M03", "No Belgium location exists, and no shipping relationship was invented for it", r["c"] == 0 and sorted(r2["codes"]) == ["DE", "NL"] and r2["c"] == 8, "BE locations 0; SHIPS_TO_COUNTRY 8 to DE and NL", {"be_locations": r["c"], "ships_to": r2["c"], "codes": r2["codes"]})
    r = one("MATCH (m:Machine {model_code:'KFT-120'}) OPTIONAL MATCH (m)<-[f:FITS]-() RETURN count(f) AS c")
    rec("checks", "M04", "KFT-120 still has no parts", r["c"] == 0, 0, r["c"])
    r = one("MATCH (m:Machine) WHERE m.status IS NOT NULL OR m.introduction_year IS NOT NULL OR m.machine_category IS NOT NULL OR m.production_status IS NOT NULL OR m.description IS NOT NULL RETURN count(m) AS c")
    r2 = one("MATCH (p:Part) WHERE p.part_type IS NOT NULL OR p.oem_status IS NOT NULL OR p.criticality IS NOT NULL RETURN count(p) AS c")
    rec("checks", "M05", "Machine status / year / category / description and part type / OEM status / criticality stay unstated", (r["c"], r2["c"]) == (0, 0), "0, 0", [r["c"], r2["c"]])
    r = one("MATCH ()-[r]->() WHERE r.source_sheet STARTS WITH 'SYN_' AND r.source_record_id IS NULL RETURN count(r) AS c")
    rec("checks", "M06", "No relationship without a source record id", r["c"] == 0, 0, r["c"])

    # ---------------- 6. representative traversals ----------------
    print("6. representative traversals")
    T = [
        ("Machine -> FITS -> Part", "MATCH (m:Machine {model_code:'NV-4500'})<-[f:FITS]-(p:Part) RETURN m.model_code AS machine, p.part_number AS part, f.fitment_status AS status ORDER BY p.part_number LIMIT 3"),
        ("Part -> FITS -> Machine", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[f:FITS]->(m:Machine) RETURN p.part_number AS part, m.model_code AS machine, f.fitment_status AS status ORDER BY m.model_code"),
        ("Part -> IN_CATEGORY -> Category", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[:IN_CATEGORY]->(c:Category) RETURN p.part_number AS part, c.name AS category, c.level AS level"),
        ("Part -> IN_SUBCATEGORY -> Category", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[:IN_SUBCATEGORY]->(c:Category) RETURN p.part_number AS part, c.name AS subcategory, c.level AS level"),
        ("Part -> HAS_SPECIFICATION -> PartSpecification", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[:HAS_SPECIFICATION]->(sp:PartSpecification) RETURN sp.name AS spec, sp.value AS value, sp.unit AS unit ORDER BY sp.specification_id LIMIT 3"),
        ("Part -> HAS_LEGACY_REFERENCE -> LegacyReference", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[:HAS_LEGACY_REFERENCE]->(l:LegacyReference) RETURN l.legacy_part_number AS legacy, l.mapping_type AS mapping"),
        ("Part -> PART_OF -> Assembly", "MATCH (p:Part)-[r:PART_OF]->(a:Assembly) RETURN p.part_number AS part, a.name AS assembly, r.quantity AS qty ORDER BY p.part_number LIMIT 3"),
        ("Part -> SUPPLIED_BY -> Supplier", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[r:SUPPLIED_BY]->(su:Supplier) RETURN su.name AS supplier, r.is_primary AS primary, r.lead_time_days AS lead_days ORDER BY r.is_primary DESC"),
        ("Supplier -> SUPPLIES_CATEGORY -> Category", "MATCH (su:Supplier {supplier_id:'SUP-001'})-[:SUPPLIES_CATEGORY]->(c:Category) RETURN su.name AS supplier, c.name AS category ORDER BY c.name"),
        ("Part -> STOCKED_BY -> Dealer", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[r:STOCKED_BY]->(d:Dealer) RETURN d.name AS dealer, r.available AS available ORDER BY d.name"),
        ("Part -> AVAILABLE_AT -> Warehouse", "MATCH (p:Part {part_number:'NVM-1010-HY'})-[r:AVAILABLE_AT]->(w:Warehouse) RETURN w.name AS warehouse, r.available AS available ORDER BY w.name"),
        ("Warehouse -> SHIPS_TO_COUNTRY -> Country", "MATCH (w:Warehouse {warehouse_id:'WH-001'})-[:SHIPS_TO_COUNTRY]->(l:Location) RETURN w.name AS warehouse, l.name AS country ORDER BY l.name"),
        ("BusinessUnit -> HOME_PLANT -> Plant", "MATCH (b:BusinessUnit)-[:HOME_PLANT]->(p:Plant) RETURN b.name AS business_unit, p.name AS home_plant ORDER BY b.name"),
        ("ComplianceRequirement -> COVERS_CATEGORY -> Category", "MATCH (c:ComplianceRequirement)-[:COVERS_CATEGORY]->(cat:Category) RETURN c.requirement AS requirement, cat.name AS category ORDER BY c.compliance_id, cat.name LIMIT 4"),
        ("Order -> ORDERED_BY -> Customer", "MATCH (o:Order)-[:ORDERED_BY]->(c:Customer) RETURN o.order_id AS order_id, c.name AS customer ORDER BY o.order_id LIMIT 3"),
        ("Order -> CONTAINS_LINE -> OrderLine -> REFERENCES_PART -> Part", "MATCH (o:Order)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) RETURN o.order_id AS order_id, l.line_no AS line, p.part_number AS part ORDER BY o.order_id, l.line_no LIMIT 3"),
        ("Order -> HAS_SHIPMENT -> Shipment", "MATCH (o:Order)-[:HAS_SHIPMENT]->(sh:Shipment) RETURN o.order_id AS order_id, sh.shipment_id AS shipment, sh.shipment_status AS status ORDER BY sh.shipment_id LIMIT 3"),
        ("Shipment -> HAS_TRACKING_EVENT -> TrackingEvent", "MATCH (sh:Shipment {shipment_id:'SHP-0001'})-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) RETURN sh.shipment_id AS shipment, e.event_seq AS seq, e.event_status AS status ORDER BY e.event_seq"),
        ("ServicePlan -> FOR_MACHINE -> Machine", "MATCH (sp:ServicePlan)-[:FOR_MACHINE]->(m:Machine {model_code:'NV-4500'}) RETURN sp.name AS plan, sp.interval_hours AS hours, m.model_code AS machine ORDER BY sp.interval_hours"),
        ("ServicePlan -> REQUIRES_PART -> Part", "MATCH (sp:ServicePlan)-[r:REQUIRES_PART]->(p:Part) RETURN sp.service_plan_id AS plan, p.part_number AS part, r.quantity AS qty ORDER BY sp.service_plan_id LIMIT 3"),
        ("Part -> CO_ORDERED_WITH -> Part (undirected)", "MATCH (a:Part)-[r:CO_ORDERED_WITH]-(b:Part) WHERE a.part_number = 'NVM-1010-HY' RETURN a.part_number AS part, b.part_number AS co_ordered_with, r.interchangeability_status AS interchangeable LIMIT 3"),
        ("Part -> SAME_NAME_GROUP_AS -> Part (undirected)", "MATCH (a:Part)-[r:SAME_NAME_GROUP_AS]-(b:Part) WHERE a.part_number = 'NVM-1010-HY' RETURN a.part_number AS part, b.part_number AS same_name_group, r.interchangeability_status AS interchangeable"),
        ("Part -> RELATED_COMPONENT -> Part", "MATCH (a:Part)-[r:RELATED_COMPONENT]->(b:Part) RETURN a.part_number AS part, b.part_number AS related_component, r.interchangeability_status AS interchangeable ORDER BY a.part_number"),
    ]
    for name, cy in T:
        rows = q(s, cy)
        RESULTS["traversals"].append({"traversal": name, "rows": len(rows), "sample": rows[0] if rows else None, "status": "PASS" if rows else "FAIL"})
        print(f"  [{'PASS' if rows else 'FAIL'}] {name}: {len(rows)} row(s); {rows[0] if rows else ''}")
    s.close()
    driver.close()

    failed = [c for c in RESULTS["checks"] if c["status"] == "FAIL"] + [t for t in RESULTS["traversals"] if t["status"] == "FAIL"]
    RESULTS["summary"] = {"checks": len(RESULTS["checks"]), "passed": sum(c["status"] == "PASS" for c in RESULTS["checks"]), "failed": len(failed), "traversals": len(T), "coverage_rows": len(CV), "coverage_matching": sum(r["match"] for r in RESULTS["coverage"])}
    OUTFILE.write_text(A.scrub(json.dumps(RESULTS, indent=1, default=str)), encoding="utf-8")
    print(RESULTS["summary"])
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("ERROR:", A.scrub(f"{type(exc).__name__}: {exc}")[:600])
        sys.exit(2)
