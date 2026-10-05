"""Parameterised Cypher for the direct-order flow: checkout reads (destinations, dealers, depot stock, routes) and the order-lifecycle writes
(place order, reserve and release stock, shipments, tracking, dealer service). Reads are bounded. Writes touch only order-workflow records and the
depot inventory row of a part that an order has reserved: they never change a catalogue, fitment, price, supplier or transport fact.
Every created relationship carries a unique rel_id, as the rest of the graph does."""
from app.graph.queries.orders import PROVENANCE

# ── reads ────────────────────────────────────────────────────────────────────────────────────────
COUNTRIES = """
MATCH (s:ShipTo) WHERE s.country_code IS NOT NULL AND EXISTS { (:TransportRoute)-[:TO_SHIP_TO]->(s) }
RETURN s.country_code AS country_code, count(s) AS destinations ORDER BY country_code LIMIT 40
"""

DESTINATIONS = """
MATCH (s:ShipTo) WHERE s.country_code = $country_code AND EXISTS { (:TransportRoute)-[:TO_SHIP_TO]->(s) }
RETURN s.shipto_id AS shipto_id, s.street_address AS street, s.city AS city, s.postal_code AS postal_code, s.country_code AS country_code,
       s.receiving_hours AS receiving_hours, s.vehicle_restrictions AS vehicle_restrictions, s.data_status AS data_status
ORDER BY s.city, s.shipto_id LIMIT 300
"""

SHIPTO = """
MATCH (s:ShipTo {shipto_id: $shipto_id}) WHERE EXISTS { (:TransportRoute)-[:TO_SHIP_TO]->(s) }
RETURN s.shipto_id AS shipto_id, s.street_address AS street, s.city AS city, s.postal_code AS postal_code, s.country_code AS country_code,
       s.receiving_hours AS receiving_hours, s.data_status AS data_status
"""

DEALERS = """
MATCH (d:Dealer) WHERE coalesce(d.dealer_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE' AND ($country_code IS NULL OR d.country_code = $country_code)
RETURN d.dealer_id AS dealer_id, d.name AS name, d.city AS city, d.country_code AS country_code, d.dealer_type AS dealer_type, d.data_status AS data_status
ORDER BY d.country_code, d.city, d.name LIMIT 150
"""

DEALER = """
MATCH (d:Dealer {dealer_id: $dealer_id}) WHERE coalesce(d.dealer_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE'
RETURN d.dealer_id AS dealer_id, d.name AS name, d.city AS city, d.country_code AS country_code, d.dealer_type AS dealer_type, d.data_status AS data_status
"""

DEALER_INSTALLS = """
UNWIND $part_ids AS pid
OPTIONAL MATCH (d:Dealer {dealer_id: $dealer_id})-[:INSTALLS_PART]->(p:Part {part_id: pid})
RETURN pid AS part_id, p IS NOT NULL AS installs
"""

MACHINE_FITS = """
UNWIND $pairs AS pair
OPTIONAL MATCH (p:Part {part_id: pair.part_id})-[f:FITS]->(m:Machine {model_code: pair.machine})
RETURN pair.part_id AS part_id, pair.machine AS machine, m IS NOT NULL AS fits, f.fitment_status AS fitment_status
"""

DEPOT_STOCK = """
UNWIND $part_ids AS pid
MATCH (p:Part {part_id: pid})-[a:AVAILABLE_AT]->(w:Warehouse)
RETURN p.part_id AS part_id, w.warehouse_id AS warehouse_id, w.name AS name, w.city AS city, w.country_code AS country_code,
       a.stock_status AS stock_status, a.available AS available, a.data_status AS data_status
ORDER BY w.warehouse_id LIMIT 1500
"""

ROUTES = """
MATCH (w:Warehouse)<-[:FROM_DEPOT]-(r:TransportRoute)-[:TO_SHIP_TO]->(s:ShipTo {shipto_id: $shipto_id})
WHERE w.warehouse_id IN $depots AND coalesce(r.route_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE'
MATCH (r)-[:USES_OPTION]->(o:TransportOption)
MATCH (r)-[:PRICED_BY]->(f:FreightRate)
RETURN w.warehouse_id AS depot_id, s.shipto_id AS shipto_id, r.route_id AS route_id, o.transport_option_id AS option_id, o.name AS option_name,
       r.option_code AS option_code, r.transport_mode AS mode, r.service_level AS service_level, r.total_distance_km AS distance_km,
       r.total_estimated_days AS days, r.estimate_basis AS estimate_basis, r.legs_count AS legs, r.data_status AS data_status,
       f.freight_rate_id AS rate_id, f.total_transport_cost AS freight_total, f.currency AS freight_currency, f.data_status AS rate_data_status
ORDER BY w.warehouse_id, r.total_estimated_days, r.total_distance_km, r.route_id LIMIT 400
"""

ROUTE_ONE = """
MATCH (w:Warehouse)<-[:FROM_DEPOT]-(r:TransportRoute {route_id: $route_id})-[:TO_SHIP_TO]->(s:ShipTo)
WHERE coalesce(r.route_status, 'ACTIVE_DEMO') STARTS WITH 'ACTIVE'
MATCH (r)-[:USES_OPTION]->(o:TransportOption)
MATCH (r)-[:PRICED_BY]->(f:FreightRate)
RETURN w.warehouse_id AS depot_id, s.shipto_id AS shipto_id, r.route_id AS route_id, o.transport_option_id AS option_id, o.name AS option_name,
       r.option_code AS option_code, r.transport_mode AS mode, r.service_level AS service_level, r.total_distance_km AS distance_km,
       r.total_estimated_days AS days, r.estimate_basis AS estimate_basis, r.legs_count AS legs, r.data_status AS data_status,
       f.freight_rate_id AS rate_id, f.total_transport_cost AS freight_total, f.currency AS freight_currency, f.data_status AS rate_data_status
"""

ORDER_BY_KEY = """
MATCH (o:Order {idempotency_key: $key}) RETURN o.order_id AS order_id
"""

# ── place order ──────────────────────────────────────────────────────────────────────────────────
# The next number comes from one counter node; MERGE + SET takes its write lock, so two orders never get the same number.
NEXT_ORDER_NUMBER = """
MERGE (c:OrderSequence {name: 'direct'}) ON CREATE SET c.value = 0
SET c.value = c.value + 1
RETURN c.value AS n
"""

CREATE_ORDER = """
MATCH (u:AppUser {user_id: $user_id})
MATCH (s:ShipTo {shipto_id: $shipto_id})
MATCH (d:Dealer {dealer_id: $dealer_id})
MATCH (w:Warehouse {warehouse_id: $depot_id})
MATCH (r:TransportRoute {route_id: $route_id})
CREATE (o:Order {order_id: $order_id, idempotency_key: $key, order_date: $today, order_status: 'NEW', channel: 'DIRECT_ORDER', currency: 'EUR',
  requester_name: $requester.name, requester_email: $requester.email, requester_phone: $requester.phone, requester_company: $requester.company,
  delivery_street: s.street_address, delivery_city: s.city, delivery_postal_code: s.postal_code, delivery_country_code: s.country_code,
  receiver_name: $receiver.name, receiver_phone: $receiver.phone,
  dealer_service_required: $service_required, fulfilment_depot_id: w.warehouse_id, allocation_status: 'PENDING',
  transport_route_id: r.route_id, transport_option_code: r.option_code, transport_mode: r.transport_mode, transport_distance_km: r.total_distance_km,
  transport_estimated_days: r.total_estimated_days, transport_estimate_basis: r.estimate_basis, transport_data_status: 'SYNTHETIC_DEMO',
  freight_estimate_amount: $freight.amount, freight_estimate_currency: $freight.currency, freight_estimate_status: 'SYNTHETIC_DEMO_ESTIMATE',
  part_cost: null, transport_cost: null, order_total: null, cost_status: 'NOT_AVAILABLE',
  created_by_user_id: $user_id, source_record_id: $order_id, """ + PROVENANCE + """})
CREATE (o)-[:PLACED_BY {rel_id: 'PLACED_BY:' + $order_id, """ + PROVENANCE + """}]->(u)
CREATE (o)-[:SHIPS_TO {rel_id: 'SHIPS_TO:' + $order_id, """ + PROVENANCE + """}]->(s)
CREATE (o)-[:FOR_DEALER {rel_id: 'FOR_DEALER:' + $order_id, """ + PROVENANCE + """}]->(d)
CREATE (o)-[:FULFILLED_FROM {rel_id: 'FULFILLED_FROM:' + $order_id, """ + PROVENANCE + """}]->(w)
CREATE (o)-[:USES_TRANSPORT {rel_id: 'USES_TRANSPORT:' + $order_id, """ + PROVENANCE + """}]->(r)
WITH o
UNWIND $lines AS line
MATCH (p:Part {part_id: line.part_id})
CREATE (l:OrderLine {order_line_id: line.order_line_id, line_no: line.line_no, quantity: line.quantity, part_number: p.part_number, part_name: p.name,
  machine_model: line.machine, unit_price_eur: null, line_total_eur: null, allocation_status: 'NOT_YET_ALLOCATED', source_record_id: line.order_line_id, """ + PROVENANCE + """})
CREATE (o)-[:CONTAINS_LINE {rel_id: 'CONTAINS_LINE:' + line.order_line_id, """ + PROVENANCE + """}]->(l)
CREATE (l)-[:REFERENCES_PART {rel_id: 'REFERENCES_PART:' + line.order_line_id, """ + PROVENANCE + """}]->(p)
RETURN count(l) AS lines
"""

# ── guard + status event (inside every lifecycle transaction) ────────────────────────────────────
# Taking the order's write lock first makes the check-then-change atomic: two callers cannot both move the same order.
GUARD = """
MATCH (o:Order {order_id: $order_id}) WHERE o.order_status = $previous
SET o.last_updated = $today
RETURN o.order_id AS order_id, coalesce(o.allocation_status, 'PENDING') AS allocation_status, o.fulfilment_depot_id AS depot_id
"""

# ── stock: lock, reserve, release ────────────────────────────────────────────────────────────────
# Run as its OWN statement before RESERVE / RELEASE / CONSUME: writing the inventory rows (always in part order, so two orders cannot deadlock each other)
# takes their write locks, and the next statement then reads the latest committed quantity. Reading and locking in one statement would not guarantee that order.
LOCK_STOCK = """
MATCH (o:Order {order_id: $order_id})-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part)
MATCH (p)-[a:AVAILABLE_AT]->(w:Warehouse {warehouse_id: o.fulfilment_depot_id})
WITH a, p ORDER BY p.part_id
SET a.last_reservation_at = $at
RETURN count(a) AS locked
"""

# ── stock: reserve / release ─────────────────────────────────────────────────────────────────────
# Per line: write the row first (that takes its lock, so the next read sees the committed value), then reserve only if the status is IN_STOCK or LOW_STOCK,
# the quantity is known and enough. UNKNOWN, ON_ORDER and OUT_OF_STOCK never match. The caller compares `reserved` with the number of lines and rolls back otherwise.
RESERVE = """
MATCH (o:Order {order_id: $order_id}) WHERE o.allocation_status <> 'RESERVED'
MATCH (o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part)
MATCH (p)-[a:AVAILABLE_AT]->(w:Warehouse {warehouse_id: o.fulfilment_depot_id})
SET a.last_reservation_at = $at
WITH o, l, a, w, a.available AS before, l.quantity AS qty
WHERE a.stock_status IN ['IN_STOCK', 'LOW_STOCK'] AND before IS NOT NULL AND before >= qty
SET a.available = before - qty, a.reserved = coalesce(a.reserved, 0) + qty,
    a.stock_status = CASE WHEN before - qty <= 0 THEN 'OUT_OF_STOCK' WHEN before - qty <= $low THEN 'LOW_STOCK' ELSE 'IN_STOCK' END,
    l.allocation_status = 'RESERVED', l.reserved_quantity = qty, l.last_updated = $today
MERGE (l)-[r:ALLOCATED_FROM]->(w) ON CREATE SET r += {rel_id: 'ALLOCATED_FROM:' + l.order_line_id, """ + PROVENANCE + """}
SET r.quantity = qty, r.allocated_at = $at, r.released_at = null
RETURN count(DISTINCT l) AS reserved
"""

MARK_ALLOCATION = """
MATCH (o:Order {order_id: $order_id}) SET o.allocation_status = $status, o.allocation_updated_at = $at RETURN o.allocation_status AS status
"""

RELEASE = """
MATCH (o:Order {order_id: $order_id}) WHERE o.allocation_status = 'RESERVED'
MATCH (o)-[:CONTAINS_LINE]->(l:OrderLine {allocation_status: 'RESERVED'})-[:REFERENCES_PART]->(p:Part)
MATCH (p)-[a:AVAILABLE_AT]->(w:Warehouse {warehouse_id: o.fulfilment_depot_id})
SET a.last_reservation_at = $at
WITH o, l, a, coalesce(a.available, 0) + l.reserved_quantity AS back, l.reserved_quantity AS qty
SET a.available = back, a.reserved = CASE WHEN coalesce(a.reserved, 0) - qty < 0 THEN 0 ELSE coalesce(a.reserved, 0) - qty END,
    a.stock_status = CASE WHEN back <= 0 THEN 'OUT_OF_STOCK' WHEN back <= $low THEN 'LOW_STOCK' ELSE 'IN_STOCK' END,
    l.allocation_status = 'RELEASED', l.last_updated = $today
WITH o, l
OPTIONAL MATCH (l)-[r:ALLOCATED_FROM]->(:Warehouse)
SET r.released_at = $at
RETURN count(DISTINCT l) AS released
"""

# Leaving the depot: the units were reserved (not available); now they are no longer on hand either.
CONSUME = """
MATCH (o:Order {order_id: $order_id})-[:CONTAINS_LINE]->(l:OrderLine {allocation_status: 'RESERVED'})-[:REFERENCES_PART]->(p:Part)
MATCH (p)-[a:AVAILABLE_AT]->(w:Warehouse {warehouse_id: o.fulfilment_depot_id})
SET a.last_reservation_at = $at
WITH l, a, l.reserved_quantity AS qty
SET a.on_hand = CASE WHEN coalesce(a.on_hand, 0) - qty < 0 THEN 0 ELSE coalesce(a.on_hand, 0) - qty END,
    a.reserved = CASE WHEN coalesce(a.reserved, 0) - qty < 0 THEN 0 ELSE coalesce(a.reserved, 0) - qty END,
    l.allocation_status = 'SHIPPED', l.last_updated = $today
RETURN count(l) AS consumed
"""

# ── shipment, tracking, dealer service ───────────────────────────────────────────────────────────
CREATE_SHIPMENT = """
MATCH (o:Order {order_id: $order_id})-[:FULFILLED_FROM]->(w:Warehouse)
MATCH (o)-[:SHIPS_TO]->(s:ShipTo)
MATCH (o)-[:USES_TRANSPORT]->(r:TransportRoute)-[:USES_OPTION]->(opt:TransportOption)
CREATE (sh:Shipment {shipment_id: $shipment_id, shipment_status: 'CREATED', tracking_ref: $tracking_ref, tracking_basis: 'SYNTHETIC_DEMO',
  est_road_km: r.total_distance_km, transport_mode: r.transport_mode, estimated_days: r.total_estimated_days, source_record_id: $shipment_id, """ + PROVENANCE + """})
CREATE (o)-[:HAS_SHIPMENT {rel_id: 'HAS_SHIPMENT:' + $shipment_id, """ + PROVENANCE + """}]->(sh)
CREATE (sh)-[:DISPATCHED_FROM {rel_id: 'DISPATCHED_FROM:' + $shipment_id, """ + PROVENANCE + """}]->(w)
CREATE (sh)-[:SHIPS_TO {rel_id: 'SHIPS_TO:' + $shipment_id, """ + PROVENANCE + """}]->(s)
CREATE (sh)-[:USES_ROUTE {rel_id: 'USES_ROUTE:' + $shipment_id, """ + PROVENANCE + """}]->(r)
CREATE (sh)-[:USES_OPTION {rel_id: 'USES_OPTION:' + $shipment_id, """ + PROVENANCE + """}]->(opt)
RETURN sh.shipment_id AS shipment_id
"""

SHIPMENT_LINES = """
MATCH (sh:Shipment {shipment_id: $shipment_id}) MATCH (:Order {order_id: $order_id})-[:CONTAINS_LINE]->(l:OrderLine)
MERGE (sh)-[r:SHIPS_LINE]->(l) ON CREATE SET r += {rel_id: 'SHIPS_LINE:' + $shipment_id + ':' + l.order_line_id, """ + PROVENANCE + """}
RETURN count(l) AS lines
"""

# Tracking is demonstration data: no carrier is connected, so every event is labelled synthetic.
SHIPMENT_STATUS = """
MATCH (:Order {order_id: $order_id})-[:HAS_SHIPMENT]->(sh:Shipment {shipment_id: $shipment_id}) WHERE sh.shipment_status = $previous
SET sh.shipment_status = $status, sh.last_updated = $today
WITH sh
OPTIONAL MATCH (sh)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent)
WITH sh, coalesce(max(e.event_seq), 0) + 1 AS seq
CREATE (ev:TrackingEvent {tracking_event_id: $shipment_id + '-E' + toString(seq), event_seq: seq, event_status: $status, event_date: $today, event_location: $location,
  event_basis: 'SYNTHETIC_DEMO_TRACKING', source_record_id: $shipment_id + '-E' + toString(seq), data_status: 'SYNTHETIC_DEMO', provenance_type: 'SYNTHETIC_DEMO',
  source_id: 'APP-SESSION', source_name: 'Noordveld app (demo tracking, no carrier connected)', authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today})
CREATE (sh)-[:HAS_TRACKING_EVENT {rel_id: 'HAS_TRACKING_EVENT:' + $shipment_id + '-E' + toString(seq), data_status: 'SYNTHETIC_DEMO', provenance_type: 'SYNTHETIC_DEMO',
  source_id: 'APP-SESSION', source_name: 'Noordveld app (demo tracking, no carrier connected)', authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today}]->(ev)
RETURN seq
"""

CREATE_SERVICE = """
MATCH (o:Order {order_id: $order_id})-[:FOR_DEALER]->(d:Dealer)
CREATE (sv:DealerService {service_id: $service_id, service_status: 'CREATED', created_at: $at, source_record_id: $service_id, """ + PROVENANCE + """})
CREATE (o)-[:HAS_SERVICE {rel_id: 'HAS_SERVICE:' + $service_id, """ + PROVENANCE + """}]->(sv)
CREATE (sv)-[:PERFORMED_BY {rel_id: 'PERFORMED_BY:' + $service_id, """ + PROVENANCE + """}]->(d)
RETURN sv.service_id AS service_id
"""

SERVICE_STATUS = """
MATCH (:Order {order_id: $order_id})-[:HAS_SERVICE]->(sv:DealerService) WHERE sv.service_status = $previous
SET sv.service_status = $status, sv.last_updated = $today
FOREACH (_ IN CASE WHEN $status = 'PART_RECEIVED' THEN [1] ELSE [] END | SET sv.part_received_at = $at)
FOREACH (_ IN CASE WHEN $status = 'STARTED' THEN [1] ELSE [] END | SET sv.started_at = $at)
FOREACH (_ IN CASE WHEN $status = 'INSTALLED' THEN [1] ELSE [] END | SET sv.installed_at = $at)
FOREACH (_ IN CASE WHEN $status = 'COMPLETED' THEN [1] ELSE [] END | SET sv.completed_at = $at)
FOREACH (_ IN CASE WHEN $status = 'CANCELLED' THEN [1] ELSE [] END | SET sv.cancelled_at = $at)
RETURN sv.service_id AS service_id
"""

CANCEL_OPEN_SHIPMENT = """
MATCH (:Order {order_id: $order_id})-[:HAS_SHIPMENT]->(sh:Shipment) WHERE sh.shipment_status = 'CREATED'
SET sh.shipment_status = 'CANCELLED', sh.last_updated = $today
RETURN count(sh) AS cancelled
"""

# ── cart (adds the machine the part was chosen for) ──────────────────────────────────────────────
CART_REMOVE_LINES = """
MATCH (c:Cart {cart_id: $cart_id})-[:CONTAINS_LINE]->(l:CartLine)-[:REFERENCES_PART]->(p:Part)
WHERE any(k IN $keys WHERE k.part_id = p.part_id AND coalesce(k.machine, '') = coalesce(l.machine_model, ''))
DETACH DELETE l
RETURN count(l) AS removed
"""
