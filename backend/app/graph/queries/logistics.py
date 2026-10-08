"""Read-only, parameterised Cypher for the shipment context. Every query is bounded; every value is a parameter. Nothing here writes."""

# an id of any kind of place: warehouse, terminal, dealer, supplier, plant or ship-to
PLACE_ID = "coalesce({v}.warehouse_id, {v}.terminal_id, {v}.supplier_id, {v}.dealer_id, {v}.plant_id, {v}.shipto_id)"

SHIPMENT = """
MATCH (s:Shipment {shipment_id: $id})
RETURN properties(s) AS p,
  head([(o:Order)-[:HAS_SHIPMENT]->(s) | o.order_id]) AS order_id,
  head([(s)-[:SHIPS_LINE]->(l:OrderLine) | l.order_line_id]) AS order_line_id,
  head([(s)-[:USES_ROUTE]->(r:TransportRoute) | r.route_id]) AS route_rel,
  head([(s)-[:DISPATCHED_FROM]->(x) | """ + PLACE_ID.format(v="x") + """]) AS origin,
  head([(s)-[:DELIVERS_TO_LOCATION]->(x) | """ + PLACE_ID.format(v="x") + """]) AS destination,
  head([(s)-[:CARRIED_BY]->(c:Carrier) | c.name]) AS carrier
"""

EVENTS = """
MATCH (s:Shipment {shipment_id: $id})-[:HAS_TRACKING_EVENT]->(e:TrackingEvent)
RETURN properties(e) AS p, head([(e)-[:AT_LOCATION]->(x) | """ + PLACE_ID.format(v="x") + """]) AS location_id
ORDER BY e.event_seq, e.event_date
LIMIT 200
"""

ROUTE = """
MATCH (r:TransportRoute {route_id: $id})
OPTIONAL MATCH (r)-[:PRICED_BY]->(f:FreightRate)
RETURN properties(r) AS p, f.total_transport_cost AS cost, f.currency AS currency
"""

LEGS = """
MATCH (:TransportRoute {route_id: $id})-[h:HAS_LEG]->(l:TransportLeg)
RETURN properties(l) AS p, h.sequence AS sequence
ORDER BY h.sequence
LIMIT 50
"""

# every route recorded between two places, whether it was seeded with depot/ship-to ids or carries location ids
ROUTES_BETWEEN = """
MATCH (r:TransportRoute)
WHERE (r.origin_location_id = $origin AND r.destination_location_id = $destination) OR (r.origin_depot_id = $origin AND r.destination_shipto_id = $destination)
OPTIONAL MATCH (r)-[:PRICED_BY]->(f:FreightRate)
RETURN properties(r) AS p, f.total_transport_cost AS cost, f.currency AS currency
ORDER BY r.route_id
LIMIT 40
"""

# one query per candidate label (the label and its key come from the registry, never from user input)
LOCATION = "MATCH (n:`{label}` {{`{key}`: $id}}) RETURN properties(n) AS p, labels(n) AS labels"

ORDER = """
MATCH (o:Order {order_id: $id})
RETURN properties(o) AS p, head([(o)-[:FOR_DEALER]->(d:Dealer) | d.dealer_id]) AS dealer_id, head([(o)-[:ORDERED_BY]->(c:Customer) | c.customer_id]) AS customer_id
"""

ORDER_PART = """
MATCH (l:OrderLine {order_line_id: $id})-[:REFERENCES_PART]->(p:Part)
RETURN p.part_id AS part_id, p.part_number AS part_number, p.name AS name, l.quantity AS quantity
"""

ORDER_LINES = """
MATCH (:Order {order_id: $id})-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part)
RETURN l.order_line_id AS order_line_id, p.part_id AS part_id, p.part_number AS part_number, p.name AS name, l.quantity AS quantity,
       coalesce(l.unit_price, l.unit_price_eur) AS unit_price, l.data_status AS data_status, l.source_record_id AS source_record_id
ORDER BY l.order_line_id
LIMIT 100
"""

SHIPMENT_IDS_OF_ORDER = "MATCH (:Order {order_id: $id})-[:HAS_SHIPMENT]->(s:Shipment) RETURN s.shipment_id AS id ORDER BY id LIMIT 50"

ORDER_IDS_OF_CUSTOMER = "MATCH (o:Order)-[:ORDERED_BY]->(:Customer {customer_id: $id}) RETURN o.order_id AS id ORDER BY id LIMIT 500"
