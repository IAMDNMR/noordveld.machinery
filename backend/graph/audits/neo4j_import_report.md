# Neo4j AuraDB import report

Generated from the run logs (`graph/audits/aura_run_log.json`, `graph/audits/aura_validation_results.json`). No credentials appear in
this report or in the logs.

## FINAL STATUS

| | |
|---|---|
| **AURADB_IMPORT** | **SUCCESS** |
| **GRAPH_VALIDATION** | **PASS** (62 of 62 checks, 23 of 23 traversals) |
| **RELATIONSHIP_COVERAGE** | **PASS** (100 of 100 coverage rows match AuraDB) |
| **IDEMPOTENCY** | **PASS** (second run: 0 nodes and 0 relationships created, delta 0 / 0) |

Final graph in AuraDB: **1840 nodes, 3812 relationships** (expected 1,840 / 3,812).

## Pre-flight (read-only, before any write)

> **Record keeping:** the machine-readable log of the pre-flight and the first import was deleted when the Cypher package was rebuilt to fix two validation queries (the rebuild cleared `graph/audits/`). Those two entries were re-created from the console output printed during the run; every figure below is exactly what the run printed. The second-run log and all validation results were produced after that and are original. `graph_build.py` now preserves `aura_*.json`.


| | |
|---|---|
| Target instance | fd5aaf87 (Aura free instance; database id B18808B9F591...) |
| Server | Neo4j Kernel 5.27-aura enterprise |
| Time | 2026-10-03 (time not preserved) |
| Nodes | 0 |
| Relationships | 0 |
| Labels | none |
| Relationship types | none |
| Constraints | 0 |
| Indexes | 2: LOOKUP, LOOKUP (the two default token-lookup indexes every new Aura database has; no user data) |
| Database state | **EMPTY**, so the import was allowed to proceed |

Connection note: TLS verification stayed ON throughout. This machine's certificate store lacks the SSL.com root that Aura's
certificate chains to, so the driver was pointed at the Mozilla root bundle shipped with `certifi` instead of disabling
verification (`neo4j+ssc`). Nothing was deleted, reset or overwritten at any point.

## Import

First import: 2026-10-03 (time not preserved). Files executed in order, stopping at the first error (none occurred).

| file | statements | nodes created | relationships created | constraints created |
|---|---|---|---|---|
| 00_constraints.cypher | 99/99 | 0 | 0 | 99 |
| 01_reference_nodes.cypher | 6/6 | 35 | 3 | 0 |
| 02_machines.cypher | 8/8 | 128 | 158 | 0 |
| 03_parts.cypher | 18/18 | 1072 | 1072 | 0 |
| 04_categories.cypher | 4/4 | 101 | 291 | 0 |
| 05_plants.cypher | 5/5 | 3 | 121 | 0 |
| 06_locations.cypher | 7/7 | 63 | 53 | 0 |
| 07_fitment.cypher | 6/6 | 6 | 241 | 0 |
| 08_assemblies.cypher | 3/3 | 15 | 50 | 0 |
| 09_suppliers.cypher | 8/8 | 16 | 202 | 0 |
| 10_dealers.cypher | 6/6 | 15 | 360 | 0 |
| 11_inventory.cypher | 7/7 | 4 | 415 | 0 |
| 12_pricing.cypher | 2/2 | 100 | 100 | 0 |
| 13_customers.cypher | 7/7 | 19 | 25 | 0 |
| 15_orders.cypher | 6/6 | 40 | 80 | 0 |
| 16_order_lines.cypher | 3/3 | 14 | 28 | 0 |
| 17_allocations.cypher | 2/2 | 0 | 14 | 0 |
| 18_fulfilment.cypher | 4/4 | 100 | 200 | 0 |
| 19_shipments.cypher | 7/7 | 10 | 45 | 0 |
| 20_tracking_events.cypher | 2/2 | 27 | 27 | 0 |
| 21_service.cypher | 3/3 | 60 | 131 | 0 |
| 22_part_relationships.cypher | 3/3 | 0 | 86 | 0 |
| 23_compliance.cypher | 3/3 | 8 | 110 | 0 |
| 25_provenance.cypher | 1/1 | 4 | 0 | 0 |

Totals: 220 statements, 220 succeeded, 0 failed; created 1840 nodes,
3812 relationships and 99 constraints (38 node-id uniqueness constraints and 61
relationship `rel_id` uniqueness constraints). Files `14_requests` and `24_risk` do not exist because those domains have no data.

## Validation (`graph/cypher/99_validation.cypher` against `graph/validation/validation_expected_results.md`)

| id | check | result |
|---|---|---|
| V01 | Total nodes | PASS |
| V02 | Total relationships | PASS |
| V03 | Nodes per label | PASS |
| V04 | Relationships per type | PASS |
| V05 | Counts per data_status | PASS |
| V06 | Duplicate canonical ids | PASS |
| V07 | Duplicate relationships | PASS |
| V08 | Missing provenance | PASS |
| V09 | Synthetic sheets not marked | PASS |
| V10 | Wrong endpoint labels | PASS |
| V11 | Forbidden relationship types | PASS |
| V12 | Interchangeability asserted | PASS |
| V13 | Fitment status | PASS |
| V14 | Conditional fitments | PASS |
| V15 | Mirrored co-order pairs | PASS |
| V16 | Co-order relationships | PASS |
| V17 | Part -> machines | PASS |
| V18 | Machine -> parts (NV-4500) | PASS |
| V19 | Machine with no parts | PASS |
| V20 | Part -> category, sub-category, legacy | PASS |
| V21 | Part -> suppliers | PASS |
| V22 | Part -> dealers | PASS |
| V23 | Part -> warehouse inventory | PASS |
| V24 | Excluded dealer zero-rows absent | PASS |
| V25 | Part -> orders | PASS |
| V26 | Order -> customer and shipments | PASS |
| V27 | Shipment -> tracking events | PASS |
| V28 | Service plan -> machine and parts | PASS |
| V29 | No service jobs / alternatives / supersessions / risks | PASS |
| V30 | Trace part -> machine -> order -> shipment -> service | PASS |
| V31 | Impact analysis | PASS |
| V32 | Provenance traversal | PASS |
| V33 | Totals (idempotency reference) | PASS |

Note on V08 and V10: the first run of these two queries returned no rows, which the comparison read as a failure. The cause was
the query, not the graph: a constant label in the RETURN next to `count()` makes Cypher return no row at all when nothing
matches. The queries were rewritten to return an explicit count per row (`WITH count(...) AS c RETURN ...`) and re-run; both pass
and the graph was not touched in between.

### Quality

| Check | Result |
|---|---|
| Duplicate nodes (V06) | 0 |
| Duplicate relationships (V07) | 0 |
| Orphans / missing provenance (V08) | 0 nodes, 0 relationships |
| Broken references | 0 (every import statement matched both endpoints; counts equal the offline model) |
| Relationship violations: wrong endpoint labels (V10) | 0 across all 61 types |
| Forbidden or generic relationship types (V11, C04) | 0 |
| Interchangeability asserted (V12) | 0 |

## Coverage

|  | total | implemented with data | implemented synthetic | schema only | not applicable | blocked |
|---|---|---|---|---|---|---|
| Required relationship rows | 50 | 10 | 27 | 13 | 0 | 0 |
| Source-discovered rows | 50 | 11 | 32 | 0 | 5 | 2 |

Every row of `relationship_coverage_matrix.csv` was re-counted in AuraDB and matches the offline model (100 of 100).
Rows marked schema-only, not applicable or blocked have 0 records in AuraDB.

Newly added by the coverage audit (verified in AuraDB): `HOME_PLANT` 3, `SUPPLIES_CATEGORY` 25, `COVERS_CATEGORY` 10, `SHIPS_TO_COUNTRY` 8.

Schema-only (no records, none invented): Order to Allocation, Order to Fulfilment, ServiceJob to Machine / Part / Dealer, Part to Risk,
ALTERNATIVE_TO, SUPERSEDES, Machine to Configuration, Customer to Request, Request to Part, Installation to Machine / Part.

Blocked by missing data: WH-004 (Zwolle) has no plant; the workbook says warehouses ship to Belgium but the catalogue has no Belgium location.

## Semantics (nothing inferred)

| id | check | result |
|---|---|---|
| S01 | SUPPLIES_CATEGORY does not imply supplying every part: supplier-category-part triples with no SUPPLIED_BY exist, and SUPPLIED_BY is unchanged | PASS |
| S02 | The only Supplier-Part relationship is SUPPLIED_BY (no supply inferred from category or location) | PASS |
| S03 | COVERS_CATEGORY is separate from part-level HAS_COMPLIANCE (the latter only from SYN_part_compliance rows, 100) | PASS |
| S04 | SHIPS_TO_COUNTRY is not 'located in': warehouses ship to countries other than their own, and it is their only link to a Location | PASS |
| S05 | HOME_PLANT = the business unit's home plant | PASS |
| S06 | PLANNED_FULFILMENT_FROM is never an allocation (no line has both; planned lines are not RESERVED/SHIPPED) | PASS |
| S07 | CONDITIONAL fitments stay conditional with their condition | PASS |
| S08 | SAME_NAME_GROUP_AS / RELATED_COMPONENT carry interchangeability_status UNKNOWN (11 of 11), not alternatives | PASS |
| M01 | 5 unresolved legacy references stay without a legacy number | PASS |
| M02 | WH-004 has no plant | PASS |
| M03 | No Belgium location exists, and no shipping relationship was invented for it | PASS |
| M04 | KFT-120 still has no parts | PASS |
| M05 | Machine status / year / category / description and part type / OEM status / criticality stay unstated | PASS |
| M06 | No relationship without a source record id | PASS |

## Provenance and synthetic data

| id | check | result | actual |
|---|---|---|---|
| P01 | Synthetic records = 3,846, all SYNTHETIC_DEMO | PASS | {"nodes": 1209, "relationships": 2637, "total": 3846} |
| P02 | Provenance classes stay distinct and complete | PASS | {"SOURCE_DERIVED": 1234, "DERIVED": 556, "USER_PROVIDED": 16, "SYNTHETIC_DEMO": 3846} |
| P03 | No SYN_ record is unmarked | PASS |  |
| P04 | No catalogue record is labelled synthetic | PASS |  |
| P05 | Catalogue Part carries no synthetic operational values (price, stock, availability...) | PASS |  |
| P06 | Supplier, Dealer, Warehouse, Price, Order, Shipment, ServicePlan, Compliance, Tracking, stock and sourcing relationships all SYNTHETIC_DEMO | PASS |  |
| P07 | Every FITS relationship is SOURCE_DERIVED | PASS |  |

The four classes stay distinct: SOURCE_DERIVED 1,234, DERIVED 556, USER_PROVIDED (the project brief) 16, SYNTHETIC_DEMO 3,846 (nodes plus relationships).
The project-brief class is stored as `USER_PROVIDED`, the allowed provenance category for it.

## Traversals

| traversal | rows | sample | result |
|---|---|---|---|
| Machine -> FITS -> Part | 3 | {"machine": "NV-4500", "part": "NVM-1010-AT", "status": "CONFIRMED"} | PASS |
| Part -> FITS -> Machine | 2 | {"part": "NVM-1010-HY", "machine": "NV-3200", "status": "CONFIRMED"} | PASS |
| Part -> IN_CATEGORY -> Category | 1 | {"part": "NVM-1010-HY", "category": "Hydraulics", "level": 1} | PASS |
| Part -> IN_SUBCATEGORY -> Category | 1 | {"part": "NVM-1010-HY", "subcategory": "Hydraulic hose", "level": 2} | PASS |
| Part -> HAS_SPECIFICATION -> PartSpecification | 3 | {"spec": "Spec Note", "value": "3/4 in, 2-wire braid, 900mm", "unit": null} | PASS |
| Part -> HAS_LEGACY_REFERENCE -> LegacyReference | 1 | {"legacy": "AS-771", "mapping": "CODE_ONLY"} | PASS |
| Part -> PART_OF -> Assembly | 3 | {"part": "NVM-1010-CB", "assembly": "Seat belt assembly", "qty": 2} | PASS |
| Part -> SUPPLIED_BY -> Supplier | 2 | {"supplier": "Veldstra Hydraulics (demo)", "primary": true, "lead_days": 28} | PASS |
| Supplier -> SUPPLIES_CATEGORY -> Category | 2 | {"supplier": "Veldstra Hydraulics (demo)", "category": "Hydraulics"} | PASS |
| Part -> STOCKED_BY -> Dealer | 3 | {"dealer": "Brabant Heavy Parts (demo)", "available": 8} | PASS |
| Part -> AVAILABLE_AT -> Warehouse | 4 | {"warehouse": "Bakker Parts Depot Coevorden (demo)", "available": 9} | PASS |
| Warehouse -> SHIPS_TO_COUNTRY -> Country | 2 | {"warehouse": "Noordveld Central Warehouse Assen (demo)", "country": "Germany"} | PASS |
| BusinessUnit -> HOME_PLANT -> Plant | 3 | {"business_unit": "Bakker", "home_plant": "Coevorden (NL)"} | PASS |
| ComplianceRequirement -> COVERS_CATEGORY -> Category | 4 | {"requirement": "Machinery safety (demo)", "category": "Attachments"} | PASS |
| Order -> ORDERED_BY -> Customer | 3 | {"order_id": "ORD-0001", "customer": "De Linde Verhuur (demo)"} | PASS |
| Order -> CONTAINS_LINE -> OrderLine -> REFERENCES_PART -> Part | 3 | {"order_id": "ORD-0001", "line": 1, "part": "NVM-1080-CB"} | PASS |
| Order -> HAS_SHIPMENT -> Shipment | 3 | {"order_id": "ORD-0001", "shipment": "SHP-0001", "status": "SHIPPED"} | PASS |
| Shipment -> HAS_TRACKING_EVENT -> TrackingEvent | 3 | {"shipment": "SHP-0001", "seq": 1, "status": "PICKED"} | PASS |
| ServicePlan -> FOR_MACHINE -> Machine | 4 | {"plan": "Basic service (demo)", "hours": 250, "machine": "NV-4500"} | PASS |
| ServicePlan -> REQUIRES_PART -> Part | 3 | {"plan": "SVC-1000-001", "part": "NVM-1020-HY", "qty": 1} | PASS |
| Part -> CO_ORDERED_WITH -> Part (undirected) | 2 | {"part": "NVM-1010-HY", "co_ordered_with": "NVM-1040-HY", "interchangeable": "UNKNOWN"} | PASS |
| Part -> SAME_NAME_GROUP_AS -> Part (undirected) | 1 | {"part": "NVM-1010-HY", "same_name_group": "NVM-1020-HY", "interchangeable": "UNKNOWN"} | PASS |
| Part -> RELATED_COMPONENT -> Part | 2 | {"part": "NVM-1020-FL", "related_component": "NVM-1010-FL", "interchangeable": "UNKNOWN"} | PASS |

## Idempotency

| | First run | Second run |
|---|---|---|
| Statements | 220 | 220 (failed 0) |
| Nodes created | 1840 | 0 |
| Relationships created | 3812 | 0 |
| Constraints created | 99 | 0 |
| Database totals after | 1840 nodes, 3812 relationships | 1840 nodes, 3812 relationships |
| Node delta / relationship delta | | 0 / 0 |

## Reminder

The Aura password was exposed earlier in the conversation. **Rotate it in the Aura console** (and update `.env`). `.env` is listed in `.gitignore`.
