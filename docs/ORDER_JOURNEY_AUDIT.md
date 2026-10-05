# Parts Store ordering journey: as-built audit

> **Historical.** This audit describes the ordering journey as it was *before* the direct-order implementation (purchase requests, no customer details, delivery, dealer, transport or shipment). Its findings drove that work. For the flow as it is now built and tested, see [ORDER_FLOW.md](ORDER_FLOW.md).

Source of truth: the code in `frontend/src` and `backend/app`, and the live graph, read 2026-10-05. Nothing was changed. "Present" means found in code; "absent" means searched for and not found.

## 1. Current end-user journey (what actually exists)
```
Part detail / Agentic Shopping  ->  Add to cart (partId + qty only)  ->  Cart drawer  ->  /parts-store/checkout "Review your order"
   ->  [End User only] "Submit purchase request"  ->  POST /requests  ->  Order (status NEW, channel DEMO_APP_REQUEST)  ->  /orders/{id}
```
Everything after "Order NEW" is performed by an **Order Processor** clicking "Mark as <next status>". There is no payment, no placed order (the "Place order" button is permanently disabled and the page says "Order placement is not connected in this demo"), no dealer, ship-to, receiver, transport or cost step.

## 2. Step-by-step audit (the 14 requested steps)
| # | Step | Screen / API | Data captured | Verdict |
|---|---|---|---|---|
| 1 | Part selection | `PartDetailPage` (`GET /parts/{no}`), qty stepper (1–99) | part_id, part_number, name, price + `data_status` tag, availability badge, fitment list | Present. **Vehicle/machine model is shown as a fitment list but never selected or carried** |
| 2 | Customer information | none | none. Customer = sign-in (`AppUser -ACTS_FOR-> Customer`, 2 demo users) | **Missing.** No name/email/phone/company capture. AppUser name/email exist but are not copied to the order |
| 3 | Add to cart | `CartContext.add(partId, qty)`; `PUT /me/cart` (End User) or localStorage | part_id, qty (cap 99), `Cart -OPENED_BY-> Customer` | Present. Machine context and part number are not stored (re-derived by id); qty and removal work |
| 4 | Cart review | `CartContents` (`POST /cart/quote`) | prices from graph, per-line totals, subtotal excl. VAT and delivery | Present. Non-orderable lines excluded from subtotal; unpriced → subtotal "Not available" |
| 5 | Ship-to / delivery | none | none. Order gets `DELIVERS_TO_ADDRESS` = the customer's own company address (copied automatically) | **Missing.** Not captured; only city+country is shown, and only to the processor |
| 6 | Dealer / receiver | none | none | **Missing.** An order has no dealer or receiver relationship |
| 7 | Availability | part page: sum of warehouse stock; order page after creation | `AVAILABLE_AT.available`, `stock_status` | **Partial.** No quantity-vs-stock check at cart/checkout. No CONFIRMED/STALE/UNCONFIRMED/UNKNOWN states exist anywhere in code (searched). Vocabulary is IN_STOCK / LOW_STOCK / ON_ORDER / OUT_OF_STOCK / UNKNOWN |
| 8 | Fulfilment source | order page text "Planned from / Allocated from / Available from stock" | `ALLOCATED_FROM` / `PLANNED_FULFILMENT_FROM` warehouse (line level) | **Partial.** Only set at allocation, chosen as the warehouse with most stock, regardless of destination |
| 9 | Transportation | none | none. `TransportRoute/Leg/FreightRate` (EU foundation) are not referenced by any app code | **Missing.** No options, time, cost. Nothing is invented, which is correct, but nothing is shown |
| 10 | Order review | `CheckoutPage` | parts, qty, subtotal only | **Partial.** Lacks customer, ship-to, receiver, dealer, source, transport, charges, total, provenance |
| 11 | User confirmation | button "Submit purchase request" | – | **Partial.** Explicit click, no confirm summary/dialog. Labelled a "request", not an order |
| 12 | Allocation | processor action NEW→…→ALLOCATED; `ALLOCATE_LINE` | `ALLOCATED_FROM`, `allocation_status = RESERVED` | **Broken in principle.** Happens after the order exists, by the processor; stock is never decremented, so two orders can reserve the same units; no lock/retry |
| 13 | Order creation | `POST /requests` → `CREATE_REQUEST` | order_id (`ORD-R` + hash of user+key), customer, lines (qty, unit price, line total), subtotal, `USER_PROVIDED` provenance | **Partial.** Idempotent on key (below). No dealer, ship-to, source, transport, shipping, VAT or total persisted |
| 14 | Confirmation | redirect to `/orders/{id}` (`OrderDetailPage`) | order no., items, status, history | **Partial.** Shows order no., parts, qty, subtotal, status. End User does not see customer, delivery, dealer, source or total; no separate confirmation screen |

## 3. Current order-processing lifecycle (code: `services/orders.py`)
Implemented statuses: `NEW → CONFIRMED → PROCESSING → ALLOCATED → SHIPPED → DELIVERED` (6 `OrderStatus` nodes). One forward step at a time, processor only, optimistic check (`expected_status`), each step writes an `OrderStatusEvent`. Gates: CONFIRMED needs verified+orderable+priced; ALLOCATED needs a warehouse with enough stock; SHIPPED needs an existing `Shipment`; DELIVERED needs all shipments delivered.

| Requested stage | Status in the app |
|---|---|
| Order request / review / customer confirmation | collapsed into one: customer submits → `NEW` ("Pending review") |
| Allocation pending / Allocated | `ALLOCATED` exists; "pending" has no state; line-level `NOT_YET_ALLOCATED / RESERVED` |
| Order created / accepted | `NEW` is created; "accepted" ≈ `CONFIRMED` (processor) |
| Fulfilment | `PROCESSING` |
| Shipment created / Dispatched / In transit | **no creation path**; `Shipment` only from seed data (SHIPPED/DELIVERED), `TrackingEvent` read-only |
| Delivered | `DELIVERED` |
| Dealer received, service/installation, completed, closed | **absent** |
| Exceptions (rejected, allocation failed/released, cancelled, shipment cancelled/exception, delivery failed, service cancelled) | **all absent**: no status, no transition, no UI |

## 4. Broken steps and incorrect transitions
1. **Dead end:** a submitted request can reach `ALLOCATED` but never `SHIPPED`, because the gate requires a `Shipment` and there is no way to create one. Every app-created order stalls there. (Live: 2 app requests, at NEW and CONFIRMED.)
2. **UNKNOWN stock becomes 0.** `orders.py` `_warehouse_for`/`_line` use `(available or 0)`; `queries/orders.py` `coalesce(a.available, 0)`; `PartDetailPage` `w.available ?? 0` in the total. A UNKNOWN depot row therefore counts as zero and can make "Awaiting supplier"/"No warehouse holds enough stock". This breaks the "never convert UNKNOWN into zero" rule.
3. **Cart vs submit disagree:** the quote silently excludes non-orderable lines and shows a subtotal for the rest; `POST /requests` rejects the whole request (409 `not_orderable`) if any line is non-orderable or unpriced.
4. **Allocation does not reserve stock:** `ALLOCATE_LINE` only links a warehouse; availability is unchanged, so double allocation of the same units is possible, and the warehouse choice ignores destination, transport and the dealer.
5. **Order ≠ order:** the checkout and detail pages call it a request (not a paid order), and `payment` text says no order is placed, yet the lifecycle then calls it Confirmed/Shipped/Delivered.
6. **Idempotency is per page visit:** key = random per `CheckoutPage` mount + cart contents; a double click converges, but the same cart submitted after a reload gets a new key. Server-side the cart is cleared on success, which limits the exposure.
7. **Cart limits differ:** cart caps at 99 (`PUT /me/cart`), quote allows 999, request allows 99.
8. **Signed-out and non-End-User paths:** a signed-out user can fill a cart but cannot submit (sign-in prompt). Processors cannot submit.

## 5. Where information is lost
| From → to | Lost / guessed |
|---|---|
| Part page / Agentic Shopping → cart | machine/vehicle model, delivery place, the agent's chosen candidate (add takes `partId, qty` only) |
| Customer → order | contact name, email, phone (AppUser has them; not copied); the order only links to the account's customer |
| Cart → order | nothing about delivery, dealer or receiver (never captured). Delivery address is **assumed** = the customer's company address |
| Order → allocation | destination, dealer; depot picked by max stock |
| Order → shipment | no link from order to a route/option/cost; seeded shipments link order→customer and warehouse→carrier only |
| Shipment → dealer receipt → service → closure | no entities or relationships exist |
| Cost | request orders carry subtotal only; `shipping_ex_vat`, `vat_amount`, `order_total_incl_vat` exist only on the 14 seeded orders |

## 6. Synthetic vs real
All catalogue prices, stock, delivery estimates, carriers, shipments, tracking, dealers, suppliers, routes and rates are `SYNTHETIC_DEMO`; catalogue facts (parts, fitments, specs) are `SOURCE_DERIVED`/`DERIVED`. The only `USER_PROVIDED` data is what the app writes: carts, requests (2), their lines and status events. Nothing is connected to a real ERP, carrier, payment or inventory system. The EU transport layer (4,798 routes, 498 rates) is generated and is not used by any screen or API.

## 7. Recommended corrected flow (no design work done yet)
1. Part (+ chosen machine) → add to cart: cart line stores part_id, part_number, qty, machine context.
2. Requester details at checkout (name, email, phone, company), stored on the order itself, not a customer master.
3. Ship-to address and receiver contact captured on the order; dealer chosen from the dealer network (separate from receiver and depot).
4. Availability per depot as one of CONFIRMED / STALE / UNCONFIRMED / UNKNOWN (plus quantity vs stock); UNKNOWN stays UNKNOWN and blocks allocation.
5. Fulfilment source (depot) chosen from availability, then transport options for that depot→destination from the route model (mode, days, EUR cost, labelled synthetic), nothing shown if no route exists.
6. Full order review (requester, part, qty, ship-to, receiver, dealer, source, transport, part/transport/other charges, total, provenance) and a confirm step.
7. Atomic allocation that decrements/reserves stock with a stable idempotency key per cart; then order creation.
8. Extend lifecycle with shipment creation (so SHIPPED is reachable), dealer receipt, service, completed, closed, and the exception states: rejected, allocation failed/released, cancelled, shipment exception, delivery failed.
