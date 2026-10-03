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
  [(m)-[:MEMBER_OF_FAMILY]->(:MachineFamily)<-[:SERVES_FAMILY]-(d:Dealer) | d.name][..20] AS dealers_serving_family
"""

MACHINE_PARTS = """
MATCH (p:Part)-[f:FITS]->(m:Machine {machine_id: $machine_id})
WHERE $category IS NULL OR p.category = $category
WITH p, f ORDER BY p.category, p.part_number
WITH collect({part_id: p.part_id, part_number: p.part_number, name: p.name, category: p.category, subcategory: p.subcategory,
              fitment_status: f.fitment_status, condition_note: f.condition_note, data_status: f.data_status}) AS rows
RETURN size(rows) AS total, rows[0..$limit] AS rows
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
