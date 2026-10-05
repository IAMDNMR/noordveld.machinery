"""Controlled Cypher for Parts Intelligence.

Every query here is read-only (no CREATE/MERGE/SET/DELETE/REMOVE; tests enforce it), parameterised, bounded by LIMIT, and
uses only labels and relationships that exist in the validated graph. An intent maps to exactly one of these; an LLM never
supplies Cypher. Edge-level `data_status` is returned beside every relationship so provenance is never dropped.
"""

# ── entity resolution ─────────────────────────────────────────────────────────────────────────────
# $norm = alphanumerics only, lower-case ("NVM 1010-HY" -> "nvm1010hy"); $text = lower-case text as typed.
# tier 0 = exact key, 1 = exact alias / legacy number, 2 = partial. The service decides whether a tier is unambiguous.
RESOLVE = """
CALL {
  MATCH (p:Part)
  WITH p, replace(replace(toLower(p.part_number), '-', ''), ' ', '') AS key
  WITH p, key,
    CASE WHEN key = $norm THEN 0
         WHEN EXISTS { (p)-[:HAS_LEGACY_REFERENCE]->(l:LegacyReference) WHERE replace(replace(toLower(l.legacy_part_number), '-', ''), ' ', '') = $norm } THEN 1
         WHEN EXISTS { (p)-[:HAS_ALIAS]->(a:SearchAlias) WHERE replace(replace(toLower(a.alias), '-', ''), ' ', '') = $norm } THEN 1
         WHEN size($text) >= 4 AND toLower(p.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'PART' AS kind, p.part_id AS id, p.part_number AS label, p.name AS detail, p.data_status AS data_status, tier
  UNION
  MATCH (m:Machine)
  WITH m, replace(replace(toLower(m.model_code), '-', ''), ' ', '') AS key
  WITH m, key,
    CASE WHEN key = $norm THEN 0
         WHEN EXISTS { (m)-[:HAS_ALIAS]->(a:SearchAlias) WHERE replace(replace(toLower(a.alias), '-', ''), ' ', '') = $norm } THEN 1
         WHEN size($norm) >= 3 AND key CONTAINS $norm THEN 2
         WHEN size($text) >= 4 AND toLower(m.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'MACHINE' AS kind, m.machine_id AS id, m.model_code AS label, m.name AS detail, m.data_status AS data_status, tier
  UNION
  MATCH (s:Supplier)
  WITH s, CASE WHEN toLower(s.name) = $text THEN 0 WHEN size($text) >= 4 AND toLower(s.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'SUPPLIER' AS kind, s.supplier_id AS id, s.name AS label, s.city AS detail, s.data_status AS data_status, tier
  UNION
  MATCH (d:Dealer)
  WITH d, CASE WHEN toLower(d.name) = $text THEN 0 WHEN size($text) >= 4 AND toLower(d.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'DEALER' AS kind, d.dealer_id AS id, d.name AS label, d.city AS detail, d.data_status AS data_status, tier
  UNION
  MATCH (a:Assembly)
  WITH a, CASE WHEN toLower(a.name) = $text THEN 0 WHEN size($text) >= 4 AND toLower(a.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'ASSEMBLY' AS kind, a.assembly_id AS id, a.name AS label, null AS detail, a.data_status AS data_status, tier
  UNION
  MATCH (w:Warehouse)
  WITH w, CASE WHEN replace(replace(toLower(w.warehouse_id), '-', ''), ' ', '') = $norm OR toLower(w.name) = $text THEN 0
               WHEN size($text) >= 4 AND toLower(w.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'WAREHOUSE' AS kind, w.warehouse_id AS id, w.name AS label, w.city AS detail, w.data_status AS data_status, tier
  UNION
  MATCH (o:Order) WHERE replace(replace(toLower(o.order_id), '-', ''), ' ', '') = $norm
  RETURN 'ORDER' AS kind, o.order_id AS id, o.order_id AS label, o.order_status AS detail, o.data_status AS data_status, 0 AS tier
  UNION
  MATCH (c:Category) WHERE c.level = 1
  WITH c, CASE WHEN toLower(c.name) = $text THEN 0 WHEN size($text) >= 4 AND toLower(c.name) CONTAINS $text THEN 2 END AS tier
  WHERE tier IS NOT NULL
  RETURN 'CATEGORY' AS kind, c.category_id AS id, c.name AS label, null AS detail, c.data_status AS data_status, tier
}
RETURN kind, id, label, detail, data_status, tier
ORDER BY tier, kind, label
LIMIT 30
"""

# ── part facets (all take $part_id, resolved beforehand) ─────────────────────────────────────────
PART_CORE = """
MATCH (p:Part) WHERE p.part_number = $key OR p.part_id = $key
RETURN p{.part_id, .part_number, .name, .category, .subcategory, .brand, .origin_plant, .spec_note_source, .data_status, .provenance_type,
         .authoritative_flag, .source_name, .source_file, .source_sheet, .source_record_id, .confidence, .last_updated} AS part,
  head([(c:PartCatalogProfile)-[:PROFILES_PART]->(p) | c{.part_status, .orderable, .availability_state, .status_reason, .data_status}]) AS profile,
  [(p)-[:FITS]->(:Machine)-[:MEMBER_OF_FAMILY]->(f:MachineFamily) | f.name] AS families,
  [(ir:IdentificationRequirement)-[:FOR_PART]->(p) | {model_code: head([(ir)-[:FOR_MACHINE]->(m:Machine) | m.model_code]), reason: ir.reason, needed: ir.identification_needed, data_status: ir.data_status}] AS identification
LIMIT 1
"""

PART_FITMENT = """
MATCH (p:Part {part_id: $part_id})-[f:FITS]->(m:Machine)
RETURN m.machine_id AS machine_id, m.model_code AS model_code, m.name AS name, m.machine_type AS machine_type,
  head([(m)-[:MEMBER_OF_FAMILY]->(fam:MachineFamily) | fam.name]) AS family,
  f.fitment_status AS fitment_status, f.condition_note AS condition_note, f.data_status AS data_status, f.source_record_id AS source_record_id
ORDER BY m.model_code LIMIT 100
"""

PART_RELATED = """
MATCH (p:Part {part_id: $part_id})-[r:RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(o:Part)
RETURN DISTINCT o.part_id AS part_id, o.part_number AS part_number, o.name AS name, o.category AS category,
  type(r) AS relation, r.interchangeability_status AS interchangeability_status, r.data_status AS data_status
ORDER BY relation, part_number LIMIT 50
"""

PART_ASSEMBLIES = """
MATCH (p:Part {part_id: $part_id})-[r:PART_OF]->(a:Assembly)
RETURN a.assembly_id AS assembly_id, a.name AS name, a.bom_status AS bom_status, r.quantity AS quantity, r.data_status AS data_status,
  head([(a)-[:IDENTIFIED_BY_PART]->(ip:Part) | ip.part_number]) AS identified_by,
  [(a)<-[cr:PART_OF]-(c:Part) WHERE c.part_id <> $part_id | {part_number: c.part_number, name: c.name, quantity: cr.quantity}][..20] AS components,
  size([(a)<-[:PART_OF]-(:Part) | 1]) AS component_count
ORDER BY a.name LIMIT 20
"""

PART_SUPPLIERS = """
MATCH (p:Part {part_id: $part_id})-[s:SUPPLIED_BY]->(su:Supplier)
RETURN su.supplier_id AS supplier_id, su.name AS name, su.city AS city, su.country_code AS country_code, su.supplier_status AS status,
  s.is_primary AS is_primary, s.lead_time_days AS lead_time_days, s.min_order_qty AS min_order_qty, s.supplier_part_number AS supplier_part_number,
  [(su)-[:SUPPLIES_CATEGORY]->(c:Category) | c.name] AS categories, s.data_status AS data_status
ORDER BY s.is_primary DESC, su.name LIMIT 50
"""

PART_DEALERS = """
MATCH (p:Part {part_id: $part_id})-[s:STOCKED_BY]->(d:Dealer)
RETURN d.dealer_id AS dealer_id, d.name AS name, d.city AS city, d.country_code AS country_code, d.dealer_type AS dealer_type,
  d.pickup_allowed AS pickup_allowed, s.available AS available, s.stocking_status AS stocking_status, s.data_status AS data_status
ORDER BY d.country_code, d.city, d.name LIMIT 50
"""

PART_WAREHOUSES = """
MATCH (p:Part {part_id: $part_id})-[s:AVAILABLE_AT]->(w:Warehouse)
RETURN w.warehouse_id AS warehouse_id, w.name AS name, w.city AS city, w.country_code AS country_code,
  s.available AS available, s.stock_status AS stock_status, s.data_status AS data_status
ORDER BY w.name LIMIT 20
"""

# Starts at the warehouse and follows only its own AVAILABLE_AT records. "In stock" is a recorded quantity above zero; a recorded zero is
# reported as out of stock and a record with no quantity as not stated (unknown is never zero).
WAREHOUSE_STOCK = """
MATCH (w:Warehouse {warehouse_id: $id})
OPTIONAL MATCH (p:Part)-[r:AVAILABLE_AT]->(w)
WITH w, p, r ORDER BY coalesce(r.available, 0) DESC, p.part_number
WITH w, collect(CASE WHEN p IS NULL THEN null ELSE {part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category,
  available: r.available, stock_status: r.stock_status, data_status: r.data_status} END) AS found
WITH [x IN found WHERE x IS NOT NULL] AS recs
RETURN size(recs) AS recorded, size([x IN recs WHERE x.available > 0]) AS in_stock, size([x IN recs WHERE x.available = 0]) AS out_of_stock,
  size([x IN recs WHERE x.available IS NULL]) AS not_stated, [x IN recs WHERE x.available > 0][0..$limit] AS rows
"""

PART_COMPLIANCE = """
MATCH (p:Part {part_id: $part_id})-[r:HAS_COMPLIANCE]->(c:ComplianceRequirement)
RETURN c.compliance_id AS compliance_id, c.requirement AS requirement, c.standard AS standard, c.certification AS certification,
  c.certificate_status AS certificate_status, c.valid_until AS valid_until, c.categories_covered AS categories_covered,
  [(c)-[:COVERS_CATEGORY]->(cat:Category) | cat.name] AS covers, r.data_status AS data_status
ORDER BY c.requirement LIMIT 20
"""

# The kind of every relationship touching the part and where it came from (edge-level data_status).
PART_RELATIONSHIPS = """
MATCH (p:Part {part_id: $part_id})-[r]-(x)
RETURN type(r) AS relationship, labels(x)[0] AS other_label, coalesce(r.data_status, 'UNKNOWN') AS data_status, count(*) AS n
ORDER BY relationship, other_label LIMIT 60
"""

PART_COUNTS = """
MATCH (p:Part {part_id: $part_id})
RETURN size([(p)-[:FITS]->(:Machine) | 1]) AS machines,
  size([(p)-[:RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(:Part) | 1]) AS related_parts,
  size([(p)-[:PART_OF]->(:Assembly) | 1]) AS assemblies,
  size([(p)-[:SUPPLIED_BY]->(:Supplier) | 1]) AS suppliers,
  size([(p)-[:STOCKED_BY]->(:Dealer) | 1]) AS dealers,
  size([(p)-[:AVAILABLE_AT]->(:Warehouse) | 1]) AS warehouses,
  size([(p)-[:HAS_COMPLIANCE]->(:ComplianceRequirement) | 1]) AS compliance,
  size([(p)-[:HAS_LEGACY_REFERENCE]->(:LegacyReference) | 1]) AS legacy_references,
  size([(p)-[:HAS_SPECIFICATION]->(:PartSpecification) | 1]) AS specifications,
  size([(:Price)-[:PRICES_PART]->(p) | 1]) AS prices,
  size([(p)-[:FITS]->(m:Machine) WHERE EXISTS { (m)-[:MEMBER_OF_FAMILY]->(:MachineFamily) } | 1]) AS machines_with_family
"""

# ── part -> category ──────────────────────────────────────────────────────────────────────────────
PART_CATEGORY = """
MATCH (p:Part {part_id: $part_id})
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c:Category)
OPTIONAL MATCH (p)-[:IN_SUBCATEGORY]->(sc:Category)
RETURN c.name AS category, c.category_id AS category_id, sc.name AS subcategory, c.data_status AS data_status
LIMIT 1
"""

# ── machine side ──────────────────────────────────────────────────────────────────────────────────
MACHINE_CORE = """
MATCH (m:Machine {machine_id: $machine_id})
RETURN m{.machine_id, .model_code, .name, .machine_type, .origin_plant, .country, .data_status} AS machine,
  head([(m)-[:MEMBER_OF_FAMILY]->(f:MachineFamily) | f.name]) AS family,
  head([(m)-[:BRANDED_AS]->(b:BusinessUnit) | b.name]) AS business_unit,
  head([(m)-[:MANUFACTURED_AT]->(pl:Plant) | pl.name]) AS plant,
  size([(m)<-[:FITS]-(:Part) | 1]) AS part_count,
  size([(m)<-[:FOR_MACHINE]-(:ServicePlan) | 1]) AS service_plans,
  size([(m)-[:HAS_MACHINE_SPECIFICATION]->(:MachineSpecification) | 1]) AS specifications,
  [(m)-[:MEMBER_OF_FAMILY]->(:MachineFamily)<-[:SERVES_FAMILY]-(d:Dealer) | d.name][..20] AS dealers_serving_family,
  head([(m)<-[:PROFILES_MACHINE]-(mp:MachineProfile) | mp{.application, .operating_context, .lifecycle_status, .introduction_year, .data_status}]) AS profile
"""

MACHINE_LIST = """
MATCH (m:Machine)
OPTIONAL MATCH (m)-[:MANUFACTURED_AT]->(pl:Plant)
WITH m, pl WHERE $place IS NULL OR toLower(pl.city) = $place OR toLower(pl.name) CONTAINS $place OR toLower(pl.country_code) = $place
OPTIONAL MATCH (m)-[:BRANDED_AS]->(bu:BusinessUnit)
WITH m, pl, bu WHERE $brand IS NULL OR toLower(bu.name) = $brand
RETURN m{.machine_id, .model_code, .name, .machine_type, .country, .data_status} AS machine,
  head([(m)-[:MEMBER_OF_FAMILY]->(f:MachineFamily) | f.name]) AS family,
  head([(m)-[:MANUFACTURED_AT]->(pl:Plant) | pl.name]) AS plant,
  bu.name AS brand,
  size([(m)<-[:FITS]-(:Part) | 1]) AS part_count
ORDER BY m.model_code
LIMIT 200
"""

SHARED_PARTS = """
MATCH (p:Part)-[:FITS]->(m:Machine)
WITH p, collect(m.model_code) AS machines
WHERE size(machines) >= 2 AND ($machine IS NULL OR $machine IN machines)
WITH p, machines ORDER BY size(machines) DESC, p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, data_status: p.data_status, machines: machines}) AS found
RETURN size(found) AS total, found[0..$limit] AS rows
"""

PART_SERVICE_PLANS = """
MATCH (sp:ServicePlan)-[r:REQUIRES_PART]->(:Part {part_id: $id})
OPTIONAL MATCH (sp)-[:FOR_MACHINE]->(m:Machine)
RETURN sp{.service_plan_id, .name, .interval_hours, .interval_status, .data_status} AS plan, m.model_code AS machine, r.quantity AS quantity, r.data_status AS link_status
ORDER BY machine, plan.service_plan_id
LIMIT 60
"""

PART_ORDERS = """
MATCH (o:Order)-[:CONTAINS_LINE]->(l:OrderLine)-[r:REFERENCES_PART]->(:Part {part_id: $id})
RETURN o{.order_id, .order_status, .order_date, .data_status} AS order, l.quantity AS quantity, l.allocation_status AS allocation, r.data_status AS link_status,
  [(o)-[:HAS_SHIPMENT]->(s:Shipment) | s.shipment_status] AS shipments
ORDER BY order.order_id
LIMIT 60
"""

LOW_STOCK_PARTS = """
MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p:Part)
WHERE c.availability_state IN ['LIMITED', 'BACKORDER']
WITH p, c, reduce(s = 0, x IN [(p)-[a:AVAILABLE_AT]->(:Warehouse) | coalesce(a.available, 0)] | s + x) AS units,
     size([(p)-[:AVAILABLE_AT]->(:Warehouse) | 1]) AS warehouses
WITH p, c, units, warehouses ORDER BY CASE c.availability_state WHEN 'BACKORDER' THEN 0 ELSE 1 END, units, p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, data_status: c.data_status, state: c.availability_state,
              units: units, warehouses: warehouses}) AS found
RETURN size(found) AS total, found[0..$limit] AS rows
"""

MACHINE_PARTS = """
MATCH (p:Part)-[f:FITS]->(m:Machine {machine_id: $machine_id})
WHERE $category IS NULL OR p.category = $category
WITH p, f ORDER BY p.category, p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, subcategory: p.subcategory,
              fitment_status: f.fitment_status, condition_note: f.condition_note, data_status: f.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
"""

# Top-level categories, for typo-tolerant matching of a category word the user misspelled ("hydralic").
CATEGORY_NAMES = """
MATCH (c:Category) WHERE c.level = 1
RETURN c.category_id AS id, c.name AS label, c.data_status AS data_status LIMIT 50
"""

# Other models of the same family that do have parts in a category (used when the chosen machine has none).
MACHINES_WITH_CATEGORY = """
MATCH (m:Machine {machine_id: $machine_id})-[:MEMBER_OF_FAMILY]->(:MachineFamily)<-[:MEMBER_OF_FAMILY]-(o:Machine)
WHERE o <> m AND EXISTS { (:Part {category: $category})-[:FITS]->(o) }
RETURN o.model_code AS model_code, size([(p:Part {category: $category})-[:FITS]->(o) | 1]) AS parts ORDER BY o.model_code LIMIT 20
"""

# ── supplier / dealer / assembly side ────────────────────────────────────────────────────────────
SUPPLIER_CORE = """
MATCH (s:Supplier {supplier_id: $id})
RETURN s{.supplier_id, .name, .city, .country_code, .supplier_status, .supplier_type, .data_status} AS supplier,
  [(s)-[:SUPPLIES_CATEGORY]->(c:Category) | c.name] AS categories,
  head([(s)-[:LOCATED_AT_ADDRESS]->(a:Address)-[:IN_REGION]->(r:Region) | r.name]) AS region,
  size([(s)<-[:SUPPLIED_BY]-(:Part) | 1]) AS part_count
"""

SUPPLIER_PARTS = """
MATCH (p:Part)-[r:SUPPLIED_BY]->(s:Supplier {supplier_id: $id})
WITH p, r ORDER BY p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, is_primary: r.is_primary,
              lead_time_days: r.lead_time_days, data_status: r.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
"""

DEALER_CORE = """
MATCH (d:Dealer {dealer_id: $id})
RETURN d{.dealer_id, .name, .city, .country_code, .dealer_type, .dealer_status, .pickup_allowed, .data_status} AS dealer,
  [(d)-[:SERVES_FAMILY]->(f:MachineFamily) | f.name] AS families,
  size([(d)<-[:STOCKED_BY]-(:Part) | 1]) AS part_count
"""

DEALER_PARTS = """
MATCH (p:Part)-[r:STOCKED_BY]->(d:Dealer {dealer_id: $id})
WITH p, r ORDER BY p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, available: r.available,
              stocking_status: r.stocking_status, data_status: r.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
"""

ASSEMBLY_CORE = """
MATCH (a:Assembly {assembly_id: $id})
RETURN a{.assembly_id, .name, .bom_status, .data_status} AS assembly,
  head([(a)-[:IDENTIFIED_BY_PART]->(ip:Part) | ip.part_number]) AS identified_by
LIMIT 1
"""

ASSEMBLY_PARTS = """
MATCH (p:Part)-[r:PART_OF]->(a:Assembly {assembly_id: $id})
WITH p, r ORDER BY p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, quantity: r.quantity, data_status: r.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
"""

CATEGORY_PARTS = """
MATCH (p:Part) WHERE p.category = $name
WITH p ORDER BY p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, subcategory: p.subcategory, data_status: p.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
"""

# ── data quality and KPIs (deterministic counts) ─────────────────────────────────────────────────
DATA_QUALITY = """
MATCH (p:Part)
WITH count(p) AS parts,
  sum(CASE WHEN EXISTS { (p)-[:FITS]->(:Machine) } THEN 0 ELSE 1 END) AS without_fitment,
  sum(CASE WHEN EXISTS { (p)-[:SUPPLIED_BY]->(:Supplier) } THEN 0 ELSE 1 END) AS without_supplier,
  sum(CASE WHEN EXISTS { (p)-[:AVAILABLE_AT]->(:Warehouse) } THEN 0 ELSE 1 END) AS without_warehouse_stock,
  sum(CASE WHEN EXISTS { (p)-[:STOCKED_BY]->(:Dealer) } THEN 0 ELSE 1 END) AS without_dealer_stock,
  sum(CASE WHEN EXISTS { (p)-[:HAS_COMPLIANCE]->(:ComplianceRequirement) } THEN 0 ELSE 1 END) AS without_compliance,
  sum(CASE WHEN EXISTS { (p)-[:PART_OF]->(:Assembly) } THEN 0 ELSE 1 END) AS without_assembly,
  sum(CASE WHEN EXISTS { (p)-[:HAS_LEGACY_REFERENCE]->(:LegacyReference) } THEN 0 ELSE 1 END) AS without_legacy_reference,
  sum(CASE WHEN EXISTS { (:IdentificationRequirement)-[:FOR_PART]->(p) } THEN 1 ELSE 0 END) AS needing_identification
RETURN *
"""

KPIS = """
CALL { MATCH (p:Part) RETURN count(p) AS parts }
CALL { MATCH (m:Machine) RETURN count(m) AS machines }
CALL { MATCH (:Part)-[f:FITS]->(:Machine) RETURN count(f) AS fitments }
CALL { MATCH (s:Supplier) RETURN count(s) AS suppliers }
CALL { MATCH (d:Dealer) RETURN count(d) AS dealers }
CALL { MATCH (a:Assembly) RETURN count(a) AS assemblies }
CALL { MATCH ()-[r]->() RETURN count(r) AS relationships, sum(CASE WHEN r.data_status IS NULL THEN 0 ELSE 1 END) AS relationships_with_provenance }
CALL { MATCH (n) RETURN count(n) AS nodes, sum(CASE WHEN n.data_status IS NULL THEN 0 ELSE 1 END) AS nodes_with_provenance }
CALL { MATCH (n) WHERE n.data_status = 'SYNTHETIC_DEMO' RETURN count(n) AS synthetic_nodes }
RETURN *
"""

# ── graph view of one part (single round trip, every list capped; PART_COUNTS tells the caller what was cut) ──
PART_GRAPH_VIEW = """
MATCH (p:Part {part_id: $part_id})
RETURN
  [(p)-[r:FITS]->(m:Machine) | {id: m.machine_id, label: m.model_code, type: 'FITS', ds: r.data_status}][..15] AS machines,
  [(p)-[r:PART_OF]->(a:Assembly) | {id: a.assembly_id, label: a.name, type: 'PART_OF', ds: r.data_status}][..10] AS assemblies,
  [(p)-[r:SUPPLIED_BY]->(s:Supplier) | {id: s.supplier_id, label: s.name, type: 'SUPPLIED_BY', ds: r.data_status}][..10] AS suppliers,
  [(p)-[r:STOCKED_BY]->(d:Dealer) | {id: d.dealer_id, label: d.name, type: 'STOCKED_BY', ds: r.data_status}][..10] AS dealers,
  [(p)-[r:AVAILABLE_AT]->(w:Warehouse) | {id: w.warehouse_id, label: w.name, type: 'AVAILABLE_AT', ds: r.data_status}][..6] AS warehouses,
  [(p)-[r:HAS_COMPLIANCE]->(c:ComplianceRequirement) | {id: c.compliance_id, label: c.requirement, type: 'HAS_COMPLIANCE', ds: r.data_status}][..6] AS compliance,
  [(p)-[r:RELATED_COMPONENT|CO_ORDERED_WITH|SAME_NAME_GROUP_AS]-(o:Part) | {id: o.part_id, label: o.part_number, type: type(r), ds: r.data_status}][..10] AS related,
  head([(p)-[r:IN_CATEGORY]->(c:Category) | {id: c.category_id, label: c.name, type: 'IN_CATEGORY', ds: r.data_status}]) AS category
"""

# One example of each entity kind, picked by the graph itself, so suggested questions never name anything the graph lacks.
SUGGESTION_SEEDS = """
CALL { MATCH (p:Part)-[:PART_OF]->(:Assembly)
       WHERE EXISTS { (p)-[:SUPPLIED_BY]->(:Supplier) } AND EXISTS { (p)-[:STOCKED_BY]->(:Dealer) } AND EXISTS { (p)-[:HAS_COMPLIANCE]->(:ComplianceRequirement) }
       RETURN p.part_number AS part ORDER BY part LIMIT 1 }
CALL { MATCH (m:Machine)<-[f:FITS]-(:Part) RETURN m.model_code AS machine, count(f) AS cm ORDER BY cm DESC, machine LIMIT 1 }
CALL { MATCH (s:Supplier)<-[r:SUPPLIED_BY]-(:Part) RETURN s.name AS supplier, count(r) AS cs ORDER BY cs DESC, supplier LIMIT 1 }
CALL { MATCH (d:Dealer)<-[r:STOCKED_BY]-(:Part) RETURN d.name AS dealer, count(r) AS cd ORDER BY cd DESC, dealer LIMIT 1 }
CALL { MATCH (a:Assembly)<-[r:PART_OF]-(:Part) RETURN a.name AS assembly, count(r) AS ca ORDER BY ca DESC, assembly LIMIT 1 }
RETURN part, machine, supplier, dealer, assembly
"""


# ── paths between two entities (shortest, over business relationships only, at most 4 steps) ──────
_path_rels = "FITS|PART_OF|SUPPLIED_BY|STOCKED_BY|AVAILABLE_AT|HAS_COMPLIANCE|CO_ORDERED_WITH|RELATED_COMPONENT|SAME_NAME_GROUP_AS|IN_CATEGORY|MEMBER_OF_FAMILY|SERVES_FAMILY"
_key = "coalesce({n}.part_number, {n}.model_code, {n}.name, {n}.requirement, {n}.order_id)"
_path_return = (
    "RETURN [n IN nodes(p) | {label: labels(n)[0], key: " + _key.format(n="n") + "}] AS nodes, "
    "[r IN relationships(p) | {type: type(r), source: " + _key.format(n="startNode(r)") + ", target: " + _key.format(n="endNode(r)") + ", ds: r.data_status}] AS rels"
)
PATH_BETWEEN = (
    "MATCH (a) WHERE $a_label IN labels(a) AND a[$a_prop] = $a_id "
    "MATCH (b) WHERE $b_label IN labels(b) AND b[$b_prop] = $b_id AND a <> b "
    "MATCH p = shortestPath((a)-[:" + _path_rels + "*..4]-(b)) " + _path_return + " LIMIT 1"
)
# to the nearest entities of a kind ("what links this part and a supplier")
PATH_TO_KIND = (
    "MATCH (a) WHERE $a_label IN labels(a) AND a[$a_prop] = $a_id "
    "MATCH (b) WHERE $b_label IN labels(b) AND a <> b "
    "MATCH p = shortestPath((a)-[:" + _path_rels + "*..4]-(b)) WITH p ORDER BY length(p) LIMIT 5 " + _path_return
)

# ── orders (read-only status; customer and address are deliberately not returned) ─────────────────
ORDER_STATUS = """
MATCH (o:Order {order_id: $id})
RETURN o{.order_id, .order_status, .order_date, .channel, .shipping_method, .data_status} AS order,
  [(o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) | {line_no: l.line_no, part_number: p.part_number, name: p.name, quantity: l.quantity,
      allocation_status: l.allocation_status, data_status: l.data_status}] AS lines,
  [(o)-[:HAS_SHIPMENT]->(s:Shipment) | {shipment_id: s.shipment_id, status: s.shipment_status, tracking_ref: s.tracking_ref, data_status: s.data_status,
      carrier: head([(s)-[:CARRIED_BY]->(c:Carrier) | c.name]),
      events: [(s)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) | e{.event_seq, .event_status, .event_date, .event_location}]}] AS shipments
LIMIT 1
"""

# ── locations: stated city and country of dealers, suppliers and warehouses (no coordinates exist in the graph) ──
PLACES = """
CALL {
  MATCH (d:Dealer) RETURN d.city AS city, d.country_code AS cc
  UNION MATCH (s:Supplier) RETURN s.city AS city, s.country_code AS cc
  UNION MATCH (w:Warehouse) RETURN w.city AS city, w.country_code AS cc
}
WITH collect(DISTINCT {city: city, cc: cc}) AS cities
CALL { MATCH (r:Region) RETURN collect(DISTINCT {name: r.country, cc: r.country_code}) AS countries }
RETURN cities[0..200] AS cities, countries[0..50] AS countries
LIMIT 1
"""

_located = """
WHERE ($city IS NULL OR toLower(n.city) = $city) AND ($cc IS NULL OR n.country_code = $cc)
RETURN n.{id} AS id, n.name AS name, n.city AS city, n.country_code AS cc, n.data_status AS ds
ORDER BY cc, city, name LIMIT 60
"""
DEALERS_IN = "MATCH (n:Dealer) " + _located.replace("{id}", "dealer_id")
SUPPLIERS_IN = "MATCH (n:Supplier) " + _located.replace("{id}", "supplier_id")
WAREHOUSES_IN = "MATCH (n:Warehouse) " + _located.replace("{id}", "warehouse_id")


# ── one entity's detail, for a graph node (fixed query per kind; never a label taken from user input) ─────────
WAREHOUSE_CORE = """
MATCH (w:Warehouse {warehouse_id: $id})
RETURN w{.warehouse_id, .name, .city, .country_code, .pickup_allowed, .ships_to, .data_status} AS warehouse,
  size([(w)<-[:AVAILABLE_AT]-(:Part) | 1]) AS part_count
LIMIT 1
"""

COMPLIANCE_CORE = """
MATCH (c:ComplianceRequirement {compliance_id: $id})
RETURN c{.compliance_id, .requirement, .standard, .certification, .certificate_status, .valid_until, .data_status} AS compliance,
  [(c)-[:COVERS_CATEGORY]->(cat:Category) | cat.name] AS covers, size([(c)<-[:HAS_COMPLIANCE]-(:Part) | 1]) AS part_count
LIMIT 1
"""

CATEGORY_CORE = """
MATCH (c:Category {category_id: $id})
RETURN c{.category_id, .name, .level, .data_status} AS category, size([(c)<-[:IN_CATEGORY|IN_SUBCATEGORY]-(:Part) | 1]) AS part_count
LIMIT 1
"""

# ── answer subject: the identity of the entity a question is anchored on (one small row; no lists) ──────────────
SUBJECT = {
    "PART": """
MATCH (p:Part {part_id: $id})
RETURN p.part_number AS label, p.name AS name, p.data_status AS data_status, p.source_name AS source,
  head([(p)-[:IN_CATEGORY]->(c:Category) | c.name]) AS category,
  head([(p)-[:IN_SUBCATEGORY]->(c:Category) | c.name]) AS subcategory,
  head([(c:PartCatalogProfile)-[:PROFILES_PART]->(p) | c.part_status]) AS part_status
LIMIT 1
""",
    "MACHINE": """
MATCH (m:Machine {machine_id: $id})
RETURN m.model_code AS label, m.name AS name, m.data_status AS data_status, m.machine_type AS machine_type,
  head([(m)-[:MEMBER_OF_FAMILY]->(f:MachineFamily) | f.name]) AS family
LIMIT 1
""",
    "SUPPLIER": "MATCH (s:Supplier {supplier_id: $id}) RETURN s.name AS label, s.name AS name, s.data_status AS data_status, s.city AS city, s.country_code AS country LIMIT 1",
    "DEALER": "MATCH (d:Dealer {dealer_id: $id}) RETURN d.name AS label, d.name AS name, d.data_status AS data_status, d.city AS city, d.country_code AS country LIMIT 1",
    "ASSEMBLY": """
MATCH (a:Assembly {assembly_id: $id})
RETURN a.name AS label, a.name AS name, a.data_status AS data_status, a.bom_status AS bom_status,
  head([(a)-[:IDENTIFIED_BY_PART]->(ip:Part) | ip.part_number]) AS identified_by
LIMIT 1
""",
    "WAREHOUSE": "MATCH (w:Warehouse {warehouse_id: $id}) RETURN w.name AS label, w.name AS name, w.data_status AS data_status, w.city AS city, w.country_code AS country, w.warehouse_type AS warehouse_type, w.operating_status AS operating_status LIMIT 1",
    "ORDER": "MATCH (o:Order {order_id: $id}) RETURN o.order_id AS label, null AS name, o.data_status AS data_status, o.order_status AS order_status LIMIT 1",
}
