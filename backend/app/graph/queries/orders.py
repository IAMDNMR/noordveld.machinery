"""Parameterised Cypher for accounts and the order workflow. Reads are bounded; writes touch only order-workflow records
(purchase requests, their lines, status events, line allocations, a user's cart) and reuse the existing schema:
Order-ORDERED_BY->Customer, Order-CONTAINS_LINE->OrderLine-REFERENCES_PART->Part, Order-HAS_STATUS_EVENT->OrderStatusEvent-RECORDS_STATUS->OrderStatus,
OrderLine-ALLOCATED_FROM->Warehouse, Cart-OPENED_BY->Customer, Cart-CONTAINS_LINE->CartLine-REFERENCES_PART->Part.
Every relationship carries a unique rel_id, as in the original import."""

USER = """
MATCH (u:AppUser {user_id: $user_id})
OPTIONAL MATCH (u)-[:ACTS_FOR]->(c:Customer)
RETURN u.user_id AS id, u.name AS name, u.email AS email, u.role AS role, c.customer_id AS customer_id, c.name AS customer_name
"""

USERS = """
MATCH (u:AppUser)
OPTIONAL MATCH (u)-[:ACTS_FOR]->(c:Customer)
RETURN u.user_id AS id, u.name AS name, u.email AS email, u.role AS role, c.name AS customer_name
ORDER BY u.role, u.user_id LIMIT 20
"""

# one row per order; $customer_id = null means every order (the processor's queue)
ORDER_LIST = """
MATCH (o:Order)-[:ORDERED_BY]->(c:Customer)
WHERE $customer_id IS NULL OR c.customer_id = $customer_id
OPTIONAL MATCH (o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part)
WITH o, c, l, p ORDER BY l.line_no
WITH o, c, collect(CASE WHEN l IS NULL THEN null ELSE {
    part_number: p.part_number, name: p.name, quantity: l.quantity,
    stock: reduce(n = 0, x IN [(p)-[a:AVAILABLE_AT]->(:Warehouse) | coalesce(a.available, 0)] | n + x),
    allocated: size([(l)-[:ALLOCATED_FROM]->(:Warehouse) | 1]) > 0,
    fits: [(p)-[:FITS]->(m:Machine) | m.model_code]
  } END) AS lines
RETURN o.order_id AS order_id, o.order_date AS order_date, o.order_status AS status, o.currency AS currency,
       o.subtotal_ex_vat AS subtotal_ex_vat, o.order_total_incl_vat AS total_incl_vat, o.channel AS channel, o.data_status AS data_status,
       c.customer_id AS customer_id, c.name AS customer_name, lines,
       [(o)-[:HAS_SHIPMENT]->(s:Shipment) | s.shipment_status] AS shipments
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 200
"""

ORDER_OWNER = """
MATCH (o:Order {order_id: $order_id})-[:ORDERED_BY]->(c:Customer)
RETURN o.order_status AS status, c.customer_id AS customer_id
"""

ORDER_DETAIL = """
MATCH (o:Order {order_id: $order_id})-[:ORDERED_BY]->(c:Customer)
OPTIONAL MATCH (o)-[:DELIVERS_TO_ADDRESS]->(adr:Address)
RETURN o{.order_id, .order_date, .order_status, .currency, .subtotal_ex_vat, .shipping_ex_vat, .vat_amount, .vat_rate, .order_total_incl_vat,
         .channel, .shipping_method, .data_status, .source_name, .pricing_note} AS o,
       c{.customer_id, .name, .city, .country_code} AS customer,
       CASE WHEN adr IS NULL THEN null ELSE adr{.city, .country_code} END AS address,
       [(o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) | {
          line_no: l.line_no, order_line_id: l.order_line_id, quantity: l.quantity, unit_price_eur: l.unit_price_eur, line_total_eur: l.line_total_eur,
          allocation_status: l.allocation_status, part_id: p.part_id, part_number: p.part_number, name: p.name, data_status: l.data_status,
          part_status: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.part_status]),
          orderable: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.orderable]),
          availability_state: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.availability_state]),
          inventory_data_status: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.data_status]),
          price: head([(pr:Price)-[:PRICES_PART]->(p) | pr{.list_price_ex_vat, .currency, .data_status}]),
          fitment: [(p)-[f:FITS]->(m:Machine) | {model_code: m.model_code, name: m.machine_type, status: f.fitment_status, data_status: f.data_status}],
          warehouses: [(p)-[a:AVAILABLE_AT]->(w:Warehouse) | {warehouse_id: w.warehouse_id, name: w.name, city: w.city, available: a.available, data_status: a.data_status}],
          suppliers: [(p)-[s:SUPPLIED_BY]->(su:Supplier) | {name: su.name, lead_time_days: s.lead_time_days, primary: s.is_primary, data_status: s.data_status}],
          allocated_from: [(l)-[:ALLOCATED_FROM]->(w:Warehouse) | w.name],
          planned_from: [(l)-[:PLANNED_FULFILMENT_FROM]->(w:Warehouse) | w.name]
       }] AS lines,
       [(o)-[:HAS_SHIPMENT]->(s:Shipment) | {shipment_id: s.shipment_id, status: s.shipment_status, tracking_ref: s.tracking_ref, data_status: s.data_status,
          dispatched_from: head([(s)-[:DISPATCHED_FROM]->(w:Warehouse) | w.name]),
          carrier: head([(s)-[:CARRIED_BY]->(ca:Carrier) | ca.name]),
          events: [(s)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) | e{.event_seq, .event_status, .event_date, .event_location}]}] AS shipments,
       [(o)-[:HAS_STATUS_EVENT]->(e:OrderStatusEvent) | e{.sequence, .order_status, .previous_status, .action, .actor_name, .actor_role, .occurred_at, .data_status}] AS history
"""

# ── writes ────────────────────────────────────────────────────────────────────────────────────────
PROVENANCE = """data_status: 'USER_PROVIDED', provenance_type: 'USER_PROVIDED', source_id: 'APP-SESSION', source_name: 'Noordveld app (demo session)',
  authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today"""

# A purchase request, idempotent on its order id (derived from the client's idempotency key): submitting twice changes nothing.
CREATE_REQUEST = """
MATCH (c:Customer {customer_id: $customer_id})
MERGE (o:Order {order_id: $order_id})
ON CREATE SET o += {order_date: $today, order_status: 'NEW', channel: 'DEMO_APP_REQUEST', currency: 'EUR', subtotal_ex_vat: $subtotal,
  pricing_note: 'Subtotal from recorded list prices, excluding VAT and delivery. No payment is taken and order placement is not connected in this demo.',
  created_by_user_id: $user_id, source_record_id: $order_id, """ + PROVENANCE + """}
MERGE (o)-[ob:ORDERED_BY]->(c) ON CREATE SET ob += {rel_id: 'ORDERED_BY:' + $order_id, """ + PROVENANCE + """}
WITH o, c
OPTIONAL MATCH (c)-[:LOCATED_AT_ADDRESS]->(adr:Address)
FOREACH (a IN CASE WHEN adr IS NULL THEN [] ELSE [adr] END |
  MERGE (o)-[d:DELIVERS_TO_ADDRESS]->(a) ON CREATE SET d += {rel_id: 'DELIVERS_TO_ADDRESS:' + $order_id, """ + PROVENANCE + """})
WITH o
UNWIND $lines AS line
MATCH (p:Part {part_id: line.part_id})
MERGE (l:OrderLine {order_line_id: line.order_line_id})
ON CREATE SET l += {line_no: line.line_no, quantity: line.quantity, unit_price_eur: line.unit_price, line_total_eur: line.line_total,
  allocation_status: 'NOT_YET_ALLOCATED', source_record_id: line.order_line_id, """ + PROVENANCE + """}
MERGE (o)-[cl:CONTAINS_LINE]->(l) ON CREATE SET cl += {rel_id: 'CONTAINS_LINE:' + line.order_line_id, """ + PROVENANCE + """}
MERGE (l)-[rp:REFERENCES_PART]->(p) ON CREATE SET rp += {rel_id: 'REFERENCES_PART:' + line.order_line_id, """ + PROVENANCE + """}
RETURN count(l) AS lines
"""

# One audited status event; the order's current status moves only if it is still what the caller saw (no lost updates).
STATUS_EVENT = """
MATCH (o:Order {order_id: $order_id}) WHERE o.order_status = $previous
MATCH (s:OrderStatus {order_status_code: $status})
WITH o, s, coalesce(reduce(m = 0, x IN [(o)-[:HAS_STATUS_EVENT]->(e:OrderStatusEvent) | coalesce(e.sequence, 0)] | CASE WHEN x > m THEN x ELSE m END), 0) + 1 AS seq
CREATE (e:OrderStatusEvent {status_event_id: $order_id + '-SE-' + toString(seq), source_record_id: $order_id + '-SE-' + toString(seq), sequence: seq,
  order_status: $status, previous_status: $previous, action: $action, actor_user_id: $user_id, actor_name: $user_name, actor_role: $role,
  occurred_at: $at, """ + PROVENANCE + """})
CREATE (o)-[:HAS_STATUS_EVENT {rel_id: 'HAS_STATUS_EVENT:' + e.status_event_id, """ + PROVENANCE + """}]->(e)
CREATE (e)-[:RECORDS_STATUS {rel_id: 'RECORDS_STATUS:' + e.status_event_id, """ + PROVENANCE + """}]->(s)
SET o.order_status = $status, o.last_updated = $today
RETURN seq
"""

# Allocation records which warehouse will supply a line. It reads recorded stock and never changes it.
ALLOCATE_LINE = """
MATCH (l:OrderLine {order_line_id: $order_line_id}), (w:Warehouse {warehouse_id: $warehouse_id})
WHERE NOT (l)-[:ALLOCATED_FROM]->(:Warehouse)
MERGE (l)-[a:ALLOCATED_FROM]->(w) ON CREATE SET a += {rel_id: 'ALLOCATED_FROM:' + $order_line_id, """ + PROVENANCE + """}
SET l.allocation_status = 'RESERVED', l.last_updated = $today
RETURN count(a) AS n
"""

CART_GET = """
MATCH (c:Cart {cart_id: $cart_id})-[:CONTAINS_LINE]->(l:CartLine)-[:REFERENCES_PART]->(p:Part)
RETURN p.part_id AS part_id, l.quantity AS quantity ORDER BY l.cart_line_id
"""

# Submitting a purchase request consumes the cart: its lines go, the cart node stays (and never touches an order, which has its own lines).
CART_CLEAR = """
MATCH (c:Cart {cart_id: $cart_id})-[:CONTAINS_LINE]->(l:CartLine)
DETACH DELETE l
RETURN count(l) AS cleared
"""

# The user's own cart replaces its lines; only this app-created cart (cart_id CRT-<user>) is ever touched.
CART_PUT = """
MERGE (c:Cart {cart_id: $cart_id})
ON CREATE SET c += {cart_status: 'OPEN', owner_user_id: $user_id, source_record_id: $cart_id, """ + PROVENANCE + """}
WITH c
OPTIONAL MATCH (cu:Customer {customer_id: $customer_id})
FOREACH (x IN CASE WHEN cu IS NULL THEN [] ELSE [cu] END |
  MERGE (c)-[ob:OPENED_BY]->(x) ON CREATE SET ob += {rel_id: 'OPENED_BY:' + $cart_id, """ + PROVENANCE + """})
WITH c
OPTIONAL MATCH (c)-[:CONTAINS_LINE]->(old:CartLine)
DETACH DELETE old
WITH DISTINCT c
UNWIND $lines AS line
MATCH (p:Part {part_id: line.part_id})
CREATE (l:CartLine {cart_line_id: $cart_id + '-' + line.part_id, source_record_id: $cart_id + '-' + line.part_id, quantity: line.quantity, """ + PROVENANCE + """})
CREATE (c)-[:CONTAINS_LINE {rel_id: 'CONTAINS_LINE:' + $cart_id + '-' + line.part_id, """ + PROVENANCE + """}]->(l)
CREATE (l)-[:REFERENCES_PART {rel_id: 'REFERENCES_PART:' + $cart_id + '-' + line.part_id, """ + PROVENANCE + """}]->(p)
RETURN count(l) AS n
"""
