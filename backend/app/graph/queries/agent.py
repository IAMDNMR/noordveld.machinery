"""Read-only, parameterised Cypher for Agentic Shopping. Every query is bounded."""

# Starter requests built from the graph itself: verified, orderable, in-stock parts that fit a machine, one per subcategory.
SEEDS = """
MATCH (c:PartCatalogProfile {part_status: 'VERIFIED', orderable: true, availability_state: 'IN_STOCK'})-[:PROFILES_PART]->(p:Part)-[:FITS]->(m:Machine)
WITH p, m ORDER BY p.part_number, m.model_code
WITH p.subcategory AS sub, head(collect({part: p.name, machine: m.model_code, price: head([(pr:Price)-[:PRICES_PART]->(p) | pr.list_price_ex_vat])})) AS pick
RETURN pick.part AS part, pick.machine AS machine, pick.price AS price, sub
ORDER BY sub
LIMIT 40
"""

# The quickest recorded delivery to a city from a warehouse that holds stock of the part (demo delivery estimates).
DELIVERY = """
MATCH (p:Part {part_id: $part_id})-[a:AVAILABLE_AT]->(w:Warehouse)<-[:FROM_WAREHOUSE]-(d:DeliveryEstimate)-[:TO_CUSTOMER|TO_DEALER]->(t)
WHERE coalesce(a.available, 0) > 0 AND toLower(t.city) = $city
RETURN w.warehouse_id AS warehouse_id, w.name AS warehouse, w.city AS warehouse_city, t.city AS city,
       d.standard_days AS standard_days, d.express_days AS express_days, d.data_status AS data_status
ORDER BY d.express_days, d.standard_days, w.warehouse_id
LIMIT 1
"""

CITIES = """
MATCH (d:DeliveryEstimate)-[:TO_CUSTOMER|TO_DEALER]->(t)
RETURN collect(DISTINCT t.city)[0..100] AS cities
"""
