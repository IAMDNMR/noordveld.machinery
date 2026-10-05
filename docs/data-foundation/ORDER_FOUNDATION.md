# Order / fulfilment foundation

**Implemented.** The relationship contract first written here (when the order flow was not built yet) is realised by the direct-order flow; the full description is in [../ORDER_FLOW.md](../ORDER_FLOW.md). What became of each contract item:

| Contract item | As built |
|---|---|
| `(Order)-[:SHIPS_TO]->(ShipTo)` | implemented (the order also keeps street, postal code, city and country as typed values) |
| `(Order)-[:USES_TRANSPORT]->(TransportRoute)` | implemented, with mode, option, distance, estimated days, `transport_data_status = SYNTHETIC_DEMO` |
| `(OrderLine)-[:FULFILLED_FROM]->(Warehouse)` | implemented at order level as `(Order)-[:FULFILLED_FROM]->(Warehouse)`; each reserved line additionally has `(OrderLine)-[:ALLOCATED_FROM {quantity}]->(Warehouse)` |
| `(Order)-[:RECEIVED_BY]->(Customer)` | **not used.** There is no customer master: the requester's name, email, phone and company are properties of the order, and the owner is `(Order)-[:PLACED_BY]->(AppUser)` |

New relationships introduced by the flow: `FOR_DEALER`, `HAS_SERVICE` / `PERFORMED_BY` (dealer service), `USES_ROUTE` (shipment). Cost is shown as part cost, transportation cost and total, all "Not available" (no pricing source is connected); the freight figure is context only and is labelled synthetic. Delivery is shown as ESTIMATED.

Unchanged principles: a dealer is never inferred to be a ship-to, a supplier never linked to a machine, and distance never implies service coverage. The 16 earlier demo orders are untouched and keep their own forward-only flow.
