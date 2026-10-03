# Cypher import plan

GRAPH_READINESS = PASS. Nothing has been executed against any database.

## Order

0. `graph/validation/preflight_inspection.cypher` (read-only). If the database is not empty: STOP and report.
1. `00_constraints.cypher`
2. `01_reference_nodes.cypher`
3. `02_machines.cypher`
4. `03_parts.cypher`
5. `04_categories.cypher`
6. `05_plants.cypher`
7. `06_locations.cypher`
8. `07_fitment.cypher`
9. `08_assemblies.cypher`
10. `09_suppliers.cypher`
11. `10_dealers.cypher`
12. `11_inventory.cypher`
13. `12_pricing.cypher`
14. `13_customers.cypher`
15. `15_orders.cypher`
16. `16_order_lines.cypher`
17. `17_allocations.cypher`
18. `18_fulfilment.cypher`
19. `19_shipments.cypher`
20. `20_tracking_events.cypher`
21. `21_service.cypher`
22. `22_part_relationships.cypher`
23. `23_compliance.cypher`
24. `25_provenance.cypher`
25. `99_validation.cypher`, compared with `graph/validation/validation_expected_results.md`.

Not created (no data): `14_requests.cypher` (REQUESTS: no request data exists (carts are not requests).), `24_risk.cypher` (RISK: no risk data exists.)

## Idempotency

Nodes `MERGE` on their canonical id and relationships `MERGE` on `rel_id` between matched endpoints, then `SET +=`.
Running every file twice leaves 1840 nodes and 3812 relationships.

## Size

1840 nodes, 3812 relationships, 38 unique node constraints and 61 relationship
uniqueness constraints (`rel_id`). Statements are batched in UNWIND blocks of up to 150 rows.
