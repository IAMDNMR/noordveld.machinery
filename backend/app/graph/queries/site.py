"""Read-only Cypher for the company website (machines, plants, brands, catalogue size) and the Agentic E-Commerce launch film."""

SITE_MACHINES = """
MATCH (m:Machine)
OPTIONAL MATCH (m)-[:MEMBER_OF_FAMILY]->(f:MachineFamily)
OPTIONAL MATCH (m)-[:BRANDED_AS]->(bu:BusinessUnit)
OPTIONAL MATCH (m)-[:MANUFACTURED_AT]->(pl:Plant)
RETURN m.machine_id AS machine_id, m.model_code AS model_code, m.name AS name, m.machine_type AS machine_type, m.data_status AS data_status,
  f.name AS family, bu.name AS brand, bu.acquired_year AS acquired_year, pl.plant_id AS plant_id, pl.name AS plant, pl.city AS plant_city,
  pl.country_code AS plant_country_code,
  [(p:Part)-[:FITS]->(m) | {part_number: p.part_number, name: p.name, category: p.category, spec_note: p.spec_note_source, data_status: p.data_status}] AS parts,
  head([(m)<-[:PROFILES_MACHINE]-(mp:MachineProfile) | mp{.application, .operating_context, .lifecycle_status, .introduction_year, .data_status}]) AS profile
ORDER BY m.model_code
LIMIT 200
"""

SITE_PLANTS = """
MATCH (pl:Plant)
OPTIONAL MATCH (pl)-[:OWNED_BY]->(bu:BusinessUnit)
OPTIONAL MATCH (pl)-[:LOCATED_IN]->(:Location)-[:IN_COUNTRY]->(c:Location)
RETURN pl.plant_id AS plant_id, pl.name AS name, pl.city AS city, pl.country_code AS country_code, c.name AS country,
  bu.name AS brand, bu.acquired_year AS acquired_year, size([(m:Machine)-[:MANUFACTURED_AT]->(pl) | 1]) AS machine_count, pl.data_status AS data_status
ORDER BY coalesce(bu.acquired_year, 0), pl.name
LIMIT 50
"""

SITE_CATALOGUE = """
MATCH (p:Part)
WITH count(p) AS parts, collect(p.category) AS categories
RETURN parts, [c IN apoc.coll.toSet(categories) WHERE c IS NOT NULL | {name: c, count: size([x IN categories WHERE x = c])}] AS categories
LIMIT 1
"""

# ── launch film: one machine, one part, one customer, and the records that connect them ──────────────
FILM = """
MATCH (m:Machine {model_code: $model}) MATCH (p:Part {part_id: $part}) MATCH (cu:Customer {customer_id: $customer})
OPTIONAL MATCH (p)<-[:PROFILES_PART]-(prof:PartCatalogProfile)
OPTIONAL MATCH (p)<-[:PRICES_PART]-(price:Price)
OPTIONAL MATCH (p)-[:HAS_LEGACY_REFERENCE]->(lr:LegacyReference)
OPTIONAL MATCH (lr)-[:ISSUED_BY_BUSINESS_UNIT]->(lbu:BusinessUnit)
RETURN m{.machine_id, .model_code, .name, .machine_type, .origin_plant, .country} AS machine,
  size([(x:Part)-[:FITS]->(m) | 1]) AS parts_fitted,
  size([(x:Part)-[:FITS]->(m) WHERE exists { (x)<-[:PROFILES_PART]-(:PartCatalogProfile {availability_state: 'IN_STOCK'}) } | 1]) AS in_stock,
  size([(x:Part)-[:FITS]->(m) WHERE exists { (x)-[:HAS_LEGACY_REFERENCE]->() } | 1]) AS legacy_mapped,
  [(sp:ServicePlan)-[:FOR_MACHINE]->(m) | {name: sp.name, hours: sp.interval_hours, id: sp.service_plan_id}] AS services,
  [(sp2:ServicePlan)-[:FOR_MACHINE]->(m) WHERE (sp2)-[:REQUIRES_PART]->(p) | sp2.service_plan_id] AS service_plans_with_part,
  p{.part_id, .part_number, .name, .category, .subcategory, .origin_plant, .compatible_models_source, .spec_note_source} AS part,
  prof{.weight_kg, .part_status, .availability_state} AS profile, price.list_price_ex_vat AS price_ex_vat,
  lr.legacy_part_number AS legacy_no, lbu.name AS legacy_business,
  [(x:Part)-[:FITS]->(m) WHERE x.category = p.category | {no: x.part_number, name: x.name}] AS siblings,
  [(p)-[s:SUPPLIED_BY]->(su:Supplier) | {id: su.supplier_id, name: su.name, city: su.city, primary: s.is_primary, lead: s.lead_time_days, part_no: s.supplier_part_number}] AS suppliers,
  [(p)-[a:AVAILABLE_AT]->(w:Warehouse) | {id: w.warehouse_id, kind: 'warehouse', name: w.name, city: w.city, available: a.available, pickup: w.pickup_allowed}] AS warehouses,
  [(p)-[a:STOCKED_BY]->(d:Dealer) | {id: d.dealer_id, kind: 'dealer', name: d.name, city: d.city, available: a.available, pickup: d.pickup_allowed}] AS dealers,
  cu{.customer_id, .name, .city} AS customer
LIMIT 1
"""

FILM_DELIVERY = """
MATCH (d:DeliveryEstimate)-[:TO_CUSTOMER]->(:Customer {customer_id: $customer})
MATCH (d)-[:FROM_WAREHOUSE]->(w:Warehouse)
WHERE w.warehouse_id IN $warehouses
RETURN w.warehouse_id AS warehouse_id, d.est_road_km AS km, d.standard_days AS standard_days, d.express_days AS express_days,
  d.standard_price_ex_vat AS standard_price, d.express_price_ex_vat AS express_price
ORDER BY d.est_road_km
LIMIT 1
"""

FILM_COUNTS = """
CALL { MATCH (m:Machine) RETURN count(m) AS machines }
CALL { MATCH (p:Part) RETURN count(p) AS parts }
CALL { MATCH (:Part)-[f:FITS]->(:Machine) RETURN count(f) AS fitments }
CALL { MATCH (s:PartSpecification) RETURN count(s) AS specifications }
RETURN machines, parts, fitments, specifications
LIMIT 1
"""
