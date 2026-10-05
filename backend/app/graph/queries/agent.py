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

# ── destinations, routes and service coverage (depot inventory -> route -> transport option -> ship-to) ──────────────
# Recorded delivery destinations: a ship-to counts only when at least one transport route ends there.
DESTINATIONS = """
MATCH (s:ShipTo) WHERE s.city IS NOT NULL AND EXISTS { (:TransportRoute)-[:TO_SHIP_TO]->(s) }
RETURN s.shipto_id AS shipto_id, s.city AS city, s.country_code AS country_code
ORDER BY s.country_code, s.city, s.shipto_id LIMIT 400
"""

# Routes from the given depots to the given ship-tos, each with its transport option and freight record (a synthetic demo estimate).
ROUTES_TO = """
MATCH (w:Warehouse)<-[:FROM_DEPOT]-(r:TransportRoute)-[:TO_SHIP_TO]->(s:ShipTo)
WHERE w.warehouse_id IN $depots AND s.shipto_id IN $shipto_ids AND coalesce(r.route_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE'
MATCH (r)-[:USES_OPTION]->(o:TransportOption)
MATCH (r)-[:PRICED_BY]->(f:FreightRate)
RETURN w.warehouse_id AS depot_id, s.shipto_id AS shipto_id, r.route_id AS route_id, o.transport_option_id AS option_id, o.name AS option_name,
       r.option_code AS option_code, r.transport_mode AS mode, r.service_level AS service_level, r.total_distance_km AS distance_km,
       r.total_estimated_days AS days, r.estimate_basis AS estimate_basis, r.legs_count AS legs, r.data_status AS data_status,
       f.total_transport_cost AS freight_total, f.currency AS freight_currency, f.data_status AS rate_data_status
ORDER BY w.warehouse_id, r.total_estimated_days, r.total_distance_km, r.route_id LIMIT 600
"""

# Dealers in a country that are recorded as installing the part (service evidence only: a dealer is never taken to be the destination).
DEALERS_INSTALLING = """
MATCH (d:Dealer)-[:INSTALLS_PART]->(p:Part {part_id: $part_id})
WHERE coalesce(d.dealer_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE' AND d.country_code = $country_code
RETURN d.dealer_id AS dealer_id, d.name AS name, d.city AS city, d.data_status AS data_status
ORDER BY d.city, d.name LIMIT 5
"""
