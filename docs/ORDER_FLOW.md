# Parts Store direct-order flow (as built)

Cart → Customer details → Cart review → Delivery & dealer → Availability → Fulfilment option → Review & place order → Order confirmation →
Allocation → Fulfilment → Shipment → Tracking → Dealer service (when asked for) → Completed. There is no quote request and no second ordering path.
Every rule is enforced in FastAPI (`backend/app/services/checkout.py`, `orders.py`, `order_flow.py`, `fulfilment.py`); the browser only collects choices and
shows the state the API returns. Order state is read from AuraDB on every load.

## Who and what an order keeps (never merged)
| Concept | Stored as |
|---|---|
| Requester (name, email, phone, company) | properties on the `Order`, as typed at checkout. No `Customer` is created or linked. The account only offers defaults. |
| Owner | `(Order)-[:PLACED_BY]->(AppUser)` |
| Ship-to (delivery site) | `(Order)-[:SHIPS_TO]->(ShipTo)`; street, postal code, city, country are copied onto the order |
| Receiver | `receiver_name`, `receiver_phone` on the order |
| Dealer | `(Order)-[:FOR_DEALER]->(Dealer)`; `dealer_service_required` |
| Fulfilment depot | `(Order)-[:FULFILLED_FROM]->(Warehouse)` |
| Transport | `(Order)-[:USES_TRANSPORT]->(TransportRoute)` + mode, option, distance, estimated days, `transport_data_status = SYNTHETIC_DEMO` |
| Machine context | `OrderLine.machine_model` (and `CartLine.machine_model`) |
| Cost | `part_cost`, `transport_cost`, `order_total` absent; `cost_status = NOT_AVAILABLE`. The freight figure is context only (`freight_estimate_*`, synthetic) |

Order numbers are `HCME-ORD-000001`…, from one counter node (`OrderSequence`); `Order.idempotency_key` is unique, so a retried or double-submitted place-order creates one order.

## Availability, depot, transport
* Stock is known only for `IN_STOCK` / `LOW_STOCK` rows that carry a quantity. `UNKNOWN` stays UNKNOWN: it is shown as unknown, is never read as zero, and is never allocated.
* A depot is selectable only if every line has known stock ≥ quantity **and** a recorded route to the chosen ship-to (route + freight-rate record). The depot is not chosen by "most stock": it is ranked by the estimated transit and distance of its standard road route; the user confirms depot and option.
* Options are the existing `TransportRoute` nodes `(Warehouse)<-[:FROM_DEPOT]-(r)-[:TO_SHIP_TO]->(ShipTo)` with `USES_OPTION` and `PRICED_BY`; nothing is invented, and a depot without a route offers nothing.

## Allocation
After the order exists, one transaction takes the inventory rows' write locks (in part order), reserves each line only if `available >= quantity` for a known status, decrements `available`, increments `reserved`, records `ALLOCATED_FROM` with the quantity, marks the lines and order `RESERVED` and writes the audit event. If any line cannot be reserved the whole transaction rolls back and the order is recorded as `ALLOCATION_FAILED`. Two orders cannot reserve the same units (tested with 2 and 4 simultaneous allocations against the live graph). Dispatch consumes the reserved units (`on_hand` and `reserved` fall); cancelling or releasing before dispatch puts them back.

## Lifecycle (one status vocabulary: `OrderStatus` nodes)
`NEW` (order placed) → `ALLOCATED` → `FULFILMENT_PENDING` → `FULFILLING` → `READY_TO_SHIP` → `SHIPPED` → `DELIVERED` → `COMPLETED`.
Shipment (own node): `CREATED → DISPATCHED → IN_TRANSIT → DELIVERED`, with synthetic tracking events. Dealer service (own node, only when requested): `CREATED → PART_RECEIVED → STARTED → INSTALLED → COMPLETED`; completing it completes the order; an order without service completes directly after delivery.
Exceptions: `REJECTED`, `ALLOCATION_FAILED`, `ALLOCATION_RELEASED`, `CANCELLED`, `SHIPMENT_EXCEPTION`, `DELIVERY_FAILED`, `SERVICE_CANCELLED`.
Transitions are **actions** (`POST /orders/{id}/actions`), each valid only from specific statuses and shipment/service states, checked on the server and applied with the stock change and the audit event in one transaction. An End User may cancel while the order is still early; everything else is the Order Processor's (dealer steps are recorded by the processor on the dealer's behalf: there is no dealer login).

Earlier demo orders (`DEMO_WEB_STORE`, `DEMO_APP_REQUEST`) keep their forward-only flow and are never changed by this flow.
