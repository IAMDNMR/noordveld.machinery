"""Parameterised Cypher for accounts and the order workflow. Reads are bounded; writes touch only order-workflow records
(direct orders and their lines, status events, line allocations, a user's cart) and reuse the existing schema:
Order-CONTAINS_LINE->OrderLine-REFERENCES_PART->Part, Order-HAS_STATUS_EVENT->OrderStatusEvent-RECORDS_STATUS->OrderStatus,
OrderLine-ALLOCATED_FROM->Warehouse, Cart-CONTAINS_LINE->CartLine-REFERENCES_PART->Part.
A direct order belongs to the user who placed it (Order-PLACED_BY->AppUser) and carries its requester, delivery and dealer details itself; earlier demo orders
keep their Order-ORDERED_BY->Customer link. No customer record is created for an order. The order-placing and lifecycle writes are in checkout.py.
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

# one row per order. $all = true is the processor's queue; otherwise only the user's own orders: placed by them, or (earlier orders) made for their account's customer.
# `stock` sums the depot quantities that are KNOWN; a depot whose stock is UNKNOWN adds nothing and is counted in `stock_unknown` (never read as zero).
ORDER_LIST = """
MATCH (o:Order)
OPTIONAL MATCH (o)-[:ORDERED_BY]->(c:Customer)
OPTIONAL MATCH (o)-[:PLACED_BY]->(u:AppUser)
WITH o, c, u WHERE $all OR (c IS NOT NULL AND c.customer_id = $customer_id) OR (u IS NOT NULL AND u.user_id = $user_id)
OPTIONAL MATCH (o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part)
WITH o, c, l, p ORDER BY l.line_no
WITH o, c, collect(CASE WHEN l IS NULL THEN null ELSE {
    part_number: p.part_number, name: p.name, quantity: l.quantity, machine: l.machine_model,
    stock: reduce(n = 0, x IN [(p)-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.available IS NOT NULL | a.available] | n + x),
    stock_unknown: size([(p)-[a:AVAILABLE_AT]->(:Warehouse) WHERE a.available IS NULL | 1]),
    allocated: coalesce(l.allocation_status, '') IN ['RESERVED', 'SHIPPED'] OR size([(l)-[:ALLOCATED_FROM]->(:Warehouse) | 1]) > 0,
    fits: [(p)-[:FITS]->(m:Machine) | m.model_code]
  } END) AS lines
RETURN o.order_id AS order_id, o.order_date AS order_date, o.order_status AS status, o.currency AS currency,
       o.subtotal_ex_vat AS subtotal_ex_vat, o.order_total_incl_vat AS total_incl_vat, o.channel AS channel, o.data_status AS data_status,
       c.customer_id AS customer_id, coalesce(c.name, o.requester_company, o.requester_name) AS customer_name, o.requester_name AS requester_name, lines,
       o.allocation_status AS allocation_status, o.dealer_service_required AS service_required,
       head([(o)-[:FOR_DEALER]->(d:Dealer) | d.name]) AS dealer,
       head([(o)-[:FULFILLED_FROM]->(w:Warehouse) | w.name]) AS depot,
       [(o)-[:HAS_SHIPMENT]->(s:Shipment) | s.shipment_status] AS shipments
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 200
"""

# the order's owner and the small facts every action rule needs
ORDER_OWNER = """
MATCH (o:Order {order_id: $order_id})
OPTIONAL MATCH (o)-[:ORDERED_BY]->(c:Customer)
OPTIONAL MATCH (o)-[:PLACED_BY]->(u:AppUser)
RETURN o.order_status AS status, o.channel AS channel, c.customer_id AS customer_id, u.user_id AS user_id,
       coalesce(o.allocation_status, 'PENDING') AS allocation_status, coalesce(o.dealer_service_required, false) AS service_required,
       [(o)-[:HAS_SHIPMENT]->(s:Shipment) | s.shipment_status] AS shipment_statuses,
       head([(o)-[:HAS_SERVICE]->(sv:DealerService) | sv.service_status]) AS service_status
"""

ORDER_DETAIL = """
MATCH (o:Order {order_id: $order_id})
OPTIONAL MATCH (o)-[:ORDERED_BY]->(c:Customer)
OPTIONAL MATCH (o)-[:DELIVERS_TO_ADDRESS]->(adr:Address)
RETURN o{.order_id, .order_date, .order_status, .currency, .subtotal_ex_vat, .shipping_ex_vat, .vat_amount, .vat_rate, .order_total_incl_vat,
         .channel, .shipping_method, .data_status, .source_name, .pricing_note,
         .requester_name, .requester_email, .requester_phone, .requester_company,
         .delivery_street, .delivery_city, .delivery_postal_code, .delivery_country_code, .receiver_name, .receiver_phone,
         .dealer_service_required, .fulfilment_depot_id, .allocation_status, .allocation_updated_at,
         .transport_route_id, .transport_option_code, .transport_mode, .transport_distance_km, .transport_estimated_days, .transport_estimate_basis, .transport_data_status,
         .freight_estimate_amount, .freight_estimate_currency, .freight_estimate_status, .part_cost, .transport_cost, .order_total, .cost_status} AS o,
       CASE WHEN c IS NULL THEN null ELSE c{.customer_id, .name, .city, .country_code} END AS customer,
       CASE WHEN adr IS NULL THEN null ELSE adr{.city, .country_code} END AS address,
       head([(o)-[:FOR_DEALER]->(d:Dealer) | d{.dealer_id, .name, .city, .country_code, .dealer_type}]) AS dealer,
       head([(o)-[:FULFILLED_FROM]->(w:Warehouse) | w{.warehouse_id, .name, .city, .country_code}]) AS depot,
       head([(o)-[:SHIPS_TO]->(s:ShipTo) | s{.shipto_id}]) AS ship_to,
       head([(o)-[:HAS_SERVICE]->(sv:DealerService) | sv{.service_id, .service_status, .created_at, .part_received_at, .started_at, .installed_at, .completed_at, .cancelled_at, .data_status,
                                                          dealer: head([(sv)-[:PERFORMED_BY]->(d:Dealer) | d.name])}]) AS service,
       [(o)-[:CONTAINS_LINE]->(l:OrderLine)-[:REFERENCES_PART]->(p:Part) | {
          line_no: l.line_no, order_line_id: l.order_line_id, quantity: l.quantity, unit_price_eur: l.unit_price_eur, line_total_eur: l.line_total_eur,
          allocation_status: l.allocation_status, reserved_quantity: l.reserved_quantity, machine_model: l.machine_model,
          part_id: p.part_id, part_number: p.part_number, name: p.name, data_status: l.data_status,
          part_status: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.part_status]),
          orderable: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.orderable]),
          availability_state: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.availability_state]),
          inventory_data_status: head([(cp:PartCatalogProfile)-[:PROFILES_PART]->(p) | cp.data_status]),
          price: head([(pr:Price)-[:PRICES_PART]->(p) | pr{.list_price_ex_vat, .currency, .data_status}]),
          fitment: [(p)-[f:FITS]->(m:Machine) | {model_code: m.model_code, name: m.machine_type, status: f.fitment_status, data_status: f.data_status}],
          warehouses: [(p)-[a:AVAILABLE_AT]->(w:Warehouse) | {warehouse_id: w.warehouse_id, name: w.name, city: w.city, available: a.available, stock_status: a.stock_status, data_status: a.data_status}],
          suppliers: [(p)-[s:SUPPLIED_BY]->(su:Supplier) | {name: su.name, lead_time_days: s.lead_time_days, primary: s.is_primary, data_status: s.data_status}],
          allocated_from: [(l)-[ra:ALLOCATED_FROM]->(w:Warehouse) WHERE ra.released_at IS NULL | w.name],
          planned_from: [(l)-[:PLANNED_FULFILMENT_FROM]->(w:Warehouse) | w.name]
       }] AS lines,
       [(o)-[:HAS_SHIPMENT]->(s:Shipment) | {shipment_id: s.shipment_id, status: s.shipment_status, tracking_ref: s.tracking_ref, tracking_basis: s.tracking_basis, data_status: s.data_status,
          mode: s.transport_mode, estimated_days: s.estimated_days,
          dispatched_from: head([(s)-[:DISPATCHED_FROM]->(w:Warehouse) | w.name]),
          destination: head([(s)-[:SHIPS_TO]->(st:ShipTo) | st{.city, .country_code}]),
          option: head([(s)-[:USES_OPTION]->(op:TransportOption) | op.name]),
          carrier: head([(s)-[:CARRIED_BY]->(ca:Carrier) | ca.name]),
          events: [(s)-[:HAS_TRACKING_EVENT]->(e:TrackingEvent) | e{.event_seq, .event_status, .event_date, .event_location, .data_status}]}] AS shipments,
       [(o)-[:HAS_STATUS_EVENT]->(e:OrderStatusEvent) | e{.sequence, .order_status, .previous_status, .action, .actor_name, .actor_role, .occurred_at, .data_status}] AS history
"""

# ── writes ────────────────────────────────────────────────────────────────────────────────────────
PROVENANCE = """data_status: 'USER_PROVIDED', provenance_type: 'USER_PROVIDED', source_id: 'APP-SESSION', source_name: 'Noordveld app (demo session)',
  authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today"""

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

# Allocation of an earlier-channel order records which warehouse will supply a line. It reads recorded stock and never changes it
# (direct orders reserve stock through RESERVE in checkout.py).
ALLOCATE_LINE = """
MATCH (l:OrderLine {order_line_id: $order_line_id}), (w:Warehouse {warehouse_id: $warehouse_id})
WHERE NOT (l)-[:ALLOCATED_FROM]->(:Warehouse)
MERGE (l)-[a:ALLOCATED_FROM]->(w) ON CREATE SET a += {rel_id: 'ALLOCATED_FROM:' + $order_line_id, """ + PROVENANCE + """}
SET l.allocation_status = 'RESERVED', l.last_updated = $today
RETURN count(a) AS n
"""

CART_GET = """
MATCH (c:Cart {cart_id: $cart_id})-[:CONTAINS_LINE]->(l:CartLine)-[:REFERENCES_PART]->(p:Part)
RETURN p.part_id AS part_id, p.part_number AS part_number, p.name AS part_name, l.quantity AS quantity, l.machine_model AS machine ORDER BY l.cart_line_id
"""

# Placing an order removes the lines that were ordered (CART_REMOVE_LINES in checkout.py); CART_CLEAR empties a cart.
CART_CLEAR = """
MATCH (c:Cart {cart_id: $cart_id})-[:CONTAINS_LINE]->(l:CartLine)
DETACH DELETE l
RETURN count(l) AS cleared
"""

# The user's own cart replaces its lines; only this app-created cart (cart_id CRT-<user>) is ever touched.
# A line is a part for a machine: the machine the part was chosen for travels with it. No order is created here.
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
CREATE (l:CartLine {cart_line_id: $cart_id + '-' + line.key, source_record_id: $cart_id + '-' + line.key, quantity: line.quantity, machine_model: line.machine,
  part_number: p.part_number, part_name: p.name, """ + PROVENANCE + """})
CREATE (c)-[:CONTAINS_LINE {rel_id: 'CONTAINS_LINE:' + $cart_id + '-' + line.key, """ + PROVENANCE + """}]->(l)
CREATE (l)-[:REFERENCES_PART {rel_id: 'REFERENCES_PART:' + $cart_id + '-' + line.key, """ + PROVENANCE + """}]->(p)
RETURN count(l) AS n
"""
