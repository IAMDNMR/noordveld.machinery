"""Cypher for the parts catalogue. Read-only.

Relationships used are the validated ones: FITS, IN_CATEGORY, HAS_LEGACY_REFERENCE, HAS_SPECIFICATION, and the synthetic
demo layers (PROFILES_PART, PRICES_PART, AVAILABLE_AT, STOCKED_BY, SUPPLIED_BY, HAS_COMPLIANCE...). Nothing is inferred.
"""

# What a card needs. Commercial values come from the synthetic demo layer and keep their data_status.
_SUMMARY = """
  p.part_id AS part_id, p.part_number AS part_number, p.name AS name, p.category AS category, p.subcategory AS subcategory,
  [(p)-[f:FITS]->(m:Machine) | {model_code: m.model_code, fitment_status: f.fitment_status}] AS fitment,
  head([(pr:Price)-[:PRICES_PART]->(p) | {amount: pr.list_price_ex_vat, currency: pr.currency, data_status: pr.data_status}]) AS price,
  head([(c:PartCatalogProfile)-[:PROFILES_PART]->(p) | {availability_state: c.availability_state, orderable: c.orderable, part_status: c.part_status, data_status: c.data_status}]) AS profile,
  CASE WHEN size([(p)-[:AVAILABLE_AT]->(:Warehouse) | 1]) = 0 THEN null
       ELSE reduce(n = 0, a IN [(p)-[s:AVAILABLE_AT]->(:Warehouse) | s.available] | n + a) END AS total_available
"""

# Free text matches the part number (with or without dashes), name, category, spec note, legacy numbers,
# search aliases and the machine models the part fits. Every word has to be found somewhere.
LIST_PARTS = """
MATCH (p:Part)
WHERE ($category IS NULL OR p.category = $category)
  AND ($machine IS NULL OR EXISTS { (p)-[:FITS]->(:Machine {model_code: $machine}) })
WITH p,
  toLower(p.part_number + ' ' + p.name + ' ' + coalesce(p.category, '') + ' ' + coalesce(p.subcategory, '') + ' ' + coalesce(p.spec_note_source, '') + ' '
    + reduce(s = '', x IN [(p)-[:HAS_LEGACY_REFERENCE]->(l:LegacyReference) WHERE l.legacy_part_number IS NOT NULL | l.legacy_part_number] | s + ' ' + x) + ' '
    + reduce(s = '', x IN [(p)-[:HAS_ALIAS]->(a:SearchAlias) | a.alias] | s + ' ' + x) + ' '
    + reduce(s = '', x IN [(p)-[:FITS]->(m:Machine) | m.model_code] | s + ' ' + x)) AS hay
WHERE ALL(t IN $tokens WHERE hay CONTAINS t OR replace(replace(hay, '-', ''), ' ', '') CONTAINS replace(t, '-', ''))
OPTIONAL MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p)
WITH p, c
WHERE ($availability IS NULL OR c.availability_state IN $availability)
  AND ($orderable IS NULL OR c.orderable = $orderable)
OPTIONAL MATCH (pr:Price)-[:PRICES_PART]->(p)
WITH p, pr,
  CASE WHEN $q = '' THEN 3
       WHEN toLower(p.part_number) = $q OR replace(toLower(p.part_number), '-', '') = replace($q, '-', '') THEN 0
       WHEN toLower(p.part_number) STARTS WITH $q THEN 1
       WHEN toLower(p.name) CONTAINS $q THEN 2 ELSE 3 END AS relevance
ORDER BY
  CASE $sort WHEN 'relevance' THEN relevance END,
  CASE $sort WHEN 'price_asc' THEN pr.list_price_ex_vat END ASC,
  CASE $sort WHEN 'price_desc' THEN pr.list_price_ex_vat END DESC,
  CASE $sort WHEN 'name' THEN toLower(p.name) END,
  p.category, p.part_number
WITH collect(p) AS found
RETURN size(found) AS total, [p IN found[$offset..($offset + $limit)] | p.part_id] AS part_ids
"""

PART_SUMMARIES = (
    """
UNWIND range(0, size($part_ids) - 1) AS i
MATCH (p:Part {part_id: $part_ids[i]})
RETURN i, """
    + _SUMMARY
    + """
ORDER BY i
"""
)

# A part by unified part number or by part id. One round trip: the page needs every section.
PART_DETAIL = """
MATCH (p:Part) WHERE p.part_number = $key OR p.part_id = $key
RETURN
  p{.part_id, .part_number, .name, .category, .subcategory, .brand, .origin_plant, .spec_note_source, .part_nature, .review_flags, .data_status, .source_sheet, .source_record_id, .confidence} AS part,
  [(p)-[f:FITS]->(m:Machine) | {machine_id: m.machine_id, model_code: m.model_code, name: m.name, machine_type: m.machine_type, origin_plant: m.origin_plant,
      fitment_status: f.fitment_status, condition_note: f.condition_note, review_flags: f.review_flags, data_status: f.data_status, source_record_id: f.source_record_id}] AS fitment,
  [(p)-[:HAS_SPECIFICATION]->(s:PartSpecification) | s{.specification_id, .group, .name, .value, .unit, .source_text, data_status: s.data_status}] AS specifications,
  [(p)-[:HAS_LEGACY_REFERENCE]->(l:LegacyReference) | l{.legacy_part_number, .legacy_business, .legacy_plant, .mapping_type, .legacy_source_note, .mapping_confidence, data_status: l.data_status}] AS legacy,
  head([(pr:Price)-[:PRICES_PART]->(p) | pr{.list_price_ex_vat, .currency, .valid_from, .valid_to, .price_status, data_status: pr.data_status}]) AS price,
  head([(c:PartCatalogProfile)-[:PROFILES_PART]->(p) | c{.availability_state, .orderable, .part_status, .status_reason, .weight_kg, .warranty_months, .return_window_days, data_status: c.data_status}]) AS profile,
  [(p)-[s:AVAILABLE_AT]->(w:Warehouse) | {warehouse_id: w.warehouse_id, name: w.name, city: w.city, country_code: w.country_code, available: s.available, stock_status: s.stock_status, data_status: s.data_status}] AS warehouses,
  [(p)-[s:STOCKED_BY]->(d:Dealer) | {dealer_id: d.dealer_id, name: d.name, city: d.city, country_code: d.country_code, pickup_allowed: d.pickup_allowed, available: s.available, stocking_status: s.stocking_status, data_status: s.data_status}] AS dealers,
  [(p)-[s:SUPPLIED_BY]->(su:Supplier) | {supplier_id: su.supplier_id, name: su.name, city: su.city, country_code: su.country_code, is_primary: s.is_primary, lead_time_days: s.lead_time_days, min_order_qty: s.min_order_qty, supplier_part_number: s.supplier_part_number, data_status: s.data_status}] AS suppliers,
  [(p)-[:HAS_COMPLIANCE]->(c:ComplianceRequirement) | c{.compliance_id, .requirement, .standard, .certification, .certificate_status, .valid_until, data_status: c.data_status}] AS compliance,
  [(p)-[r:PART_OF]->(a:Assembly) | {assembly_id: a.assembly_id, name: a.name, quantity: r.quantity, bom_status: a.bom_status, data_status: r.data_status}] AS assemblies,
  [(p)-[r:SAME_NAME_GROUP_AS|RELATED_COMPONENT|CO_ORDERED_WITH]-(o:Part) | {part_id: o.part_id, part_number: o.part_number, name: o.name, category: o.category, relation: type(r),
      interchangeability_status: r.interchangeability_status, data_status: r.data_status}] AS related,
  [(ir:IdentificationRequirement)-[:FOR_PART]->(p) | {model_code: head([(ir)-[:FOR_MACHINE]->(m:Machine) | m.model_code]), reason: ir.reason, identification_needed: ir.identification_needed,
      variants: [(ir)-[:ADMITS_VARIANT]->(v:MachineVariant) | v{.variant_name, .serial_from, .serial_to}], data_status: ir.data_status}] AS identification
"""
