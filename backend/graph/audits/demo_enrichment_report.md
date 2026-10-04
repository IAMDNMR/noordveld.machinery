# Noordveld graph: synthetic demo enrichment

Batch `ENRICH-2026-10-03`, data source `SRC-004` ("Demo enrichment script (seed 20261003)"), script `backend/scripts/enrich_graph_demo_data.py`.
Everything added here is **synthetic demonstration data**. It is not real company, supplier, inventory, order or shipment data, and it is labelled as such on every record.

Machine-readable versions: `demo_enrichment_audit.json` (before), `demo_enrichment_report.json` (after + validation), `demo_enrichment_runs.json` (every run), `pi_question_suite.json`.

## A–C. Counts (measured)

| | Nodes | Relationships |
|---|---|---|
| Before (audit, read-only) | 1,840 | 3,812 |
| After | 1,922 | 4,002 |
| Added (all `SYNTHETIC_DEMO`, all tagged with the batch) | 82 | 190 |

Existing nodes given extra synthetic fields (only where empty, recorded in `enriched_fields`): 104 (100 `PartCatalogProfile`, 4 `Warehouse`, both already synthetic records).

## D. What was enriched

| Domain | Added | How |
|---|---|---|
| Machines | 15 `MachineProfile` + 15 `PROFILES_MACHINE` | Application, operating context, lifecycle status, introduction year, description. Descriptive only: no weights, capacities, pressures or ratings. Mirrors the existing `PartCatalogProfile → PROFILES_PART` pattern, so source-derived `Machine` nodes stay untouched. |
| Parts | `application`, `maintenance_class`, `criticality` on the 100 synthetic catalogue profiles | Rule-based from category and subcategory (for example Brakes → HIGH, a hose or seal → WEAR_PART). The source-derived `Part` nodes are unchanged. |
| Assemblies | 15 `Assembly` (ASM-101…115) + 55 `PART_OF` (quantity, basis `DEMO_BOM_CATEGORY_AND_FAMILY`) | Groups of 2–6 unassigned parts of one category that fit machines of the same family. Single parts were left unassigned on purpose. |
| Warehouses | `warehouse_type`, `operating_status` on the 4 warehouses | Central DC versus regional depot. No new warehouse ↔ plant links. |
| Customer requests | 6 `CustomerRequest` (REQ-DEMO-001…006) + `OPENED_BY` / `FOR_MACHINE` / `REQUIRES_PART` | Each is only for a part that the catalogue already says FITS the machine. Two are for non-verified parts, to show the identification flow. |
| Orders | 6 `Order` (ORD-0009…0014), one in each workflow state | Existing relationship vocabulary: `ORDERED_BY`, `DELIVERS_TO_ADDRESS`, `CONTAINS_LINE`, `REFERENCES_PART`, `ALLOCATED_FROM` (allocated or later), `PLANNED_FULFILMENT_FROM` (processing). Only VERIFIED, orderable parts with recorded stock, the same order gate as the cart. NVM-1010-HY appears in two orders. Totals are computed from the demo list price. |
| Order lines | 11 `OrderLine` | Allocation status follows the order state. |
| Status history | 21 `OrderStatusEvent` + `RECORDS_STATUS` | One per status reached, in sequence. |
| Shipments | 2 `Shipment` (shipped and delivered orders only) | `DISPATCHED_FROM` the allocating warehouse, the existing fictional carrier, `DELIVERS_TO_CUSTOMER`, `SHIPS_LINE`; tracking reference `DEMO-TRACK-…`. |
| Tracking | 5 `TrackingEvent` | PICKED → IN_TRANSIT (→ DELIVERED). Dates increase with the sequence. |
| Fitment | **none** | No `FITS` relationship was created. |
| Suppliers, dealers, compliance, service plans, inventory | **none** | They were already connected for every part (suppliers 100/100, inventory 100/100, compliance 100/100, dealers 99/100). |

New schema (documented and constrained): labels `MachineProfile` (`machine_profile_id` unique) and `CustomerRequest` (`request_id` unique), and relationship `PROFILES_MACHINE` (`rel_id` unique). Every other relationship reuses an existing type in its existing direction.

## E. Provenance after enrichment

| data_status | Nodes | Relationships |
|---|---|---|
| SOURCE_DERIVED | 456 (unchanged) | 778 (unchanged) |
| DERIVED | 165 (unchanged) | 391 (unchanged) |
| USER_PROVIDED | 10 (unchanged) | 6 (unchanged) |
| SYNTHETIC_DEMO | 1,291 (+82) | 2,827 (+190) |
| REAL / UNKNOWN / NOT_CONNECTED as a stored value | 0 | 0 |

Unconnected information is represented by the absence of a relationship and reported by Parts Intelligence as "not connected". It is never stored as a zero.

A SHA-256 fingerprint of every SOURCE_DERIVED, DERIVED and USER_PROVIDED node and relationship, with all their properties, is **identical before and after**.

## F. Validation (after, whole graph)

| Check | Result |
|---|---|
| Duplicate nodes (by id) / duplicate relationship ids | 0 / 0 |
| Duplicate fitments / supplier links / dealer links / assembly links / order lines | 0 / 0 / 0 / 0 / 0 |
| Broken references: order lines without part, orders without customer, shipments without order | 0 / 0 / 0 |
| Batch records missing provenance (nodes / relationships) | 0 / 0 |
| Invalid `data_status` values | 0 |
| Synthetic fitments created | 0 |
| Requests for a part that does not fit the machine | 0 |
| Batch orders containing a non-verified part | 0 |
| Contradictory inventory (0 available but IN_STOCK) | 0 |
| Contradictory order / shipment state; shipped orders without a shipment; status-history gaps; tracking out of order; delivered without a DELIVERED event | 0 each |
| Orphan nodes | 13: 8 `ShippingRate` (pre-existing rate table) and 5 `DataSource` (reference nodes by design, including the new SRC-004). No orphan from this batch. |

## G. Idempotency

| Run | Nodes created | Relationships created | Properties set |
|---|---|---|---|
| 1 | 82 | 190 | 4,406 |
| 2 (first attempt) | 3 | 0 | stopped by a unique-`rel_id` constraint |
| 3 and 4 (after the fix) | 0 | 0 | 0 |

The first re-run planned against the graph *including* this batch: it saw the new assemblies, planned three more (ASM-116…118) and stopped on the `rel_id` constraint before linking them. The plan now ignores the batch's own records, so a re-run reproduces the identical plan. The three empty assembly nodes were removed. They were the only records deleted: tagged with this batch, no relationships, created minutes earlier by the failed run. Runs 3 and 4 created and changed nothing.

## H. Parts Intelligence question suite

See `pi_question_suite.md`. Every question ran through the real pipeline: Gemini scope + intent → approved registry → Neo4j → evidence → grounded wording. New approved intents for the enriched data: `PART_TO_SERVICE_PLAN`, `PART_TO_ORDERS`, `LOW_STOCK_PARTS`, `SHARED_PARTS`, plus machine profile facts on `MACHINE_GRAPH`.

## I. Coverage matrix

| Domain | Existing | Synthetic added | Still missing | Status |
|---|---|---|---|---|
| Machines | 15 source-derived | 15 profiles | KFT-120 has no fitted parts in the catalogue | PASS |
| Parts | 100 source-derived | 3 profile fields × 100 | none | PASS |
| Fitment | 219 source-derived | 0 | none created by design | PASS |
| Assemblies | 15 / 35 links | 15 / 55 links | 17 parts in no assembly (on purpose) | PARTIAL |
| Suppliers | 12 / 157 links | 0 | none | PASS |
| Dealers | 15 / 315 links | 0 | 1 part has no dealer | PASS |
| Warehouses | 4 | 2 fields each | no new plant links (not inferred) | PASS |
| Inventory | 400 rows (every part × every warehouse) | 0 | variation would need deletions, which are not allowed | PASS (uniform) |
| Orders | 8 | 6 | none | PASS |
| Shipments / tracking | 9 / 27 | 2 / 5 | none | PASS |
| Service plans | 60 / 71 part links | 0 | 62 parts in no service plan | PARTIAL |
| Compliance | 8 / 100 links | 0 | no certificates beyond the demo ones | PASS |
| Locations | 5 + 44 addresses | 0 | none | PASS |
| Customers | 10 | 0 | none | PASS |
| Requests | none | 6 | none | PASS |
| Configurations | 30 `MachineVariant` (existing variant layer) | 0 | no separate configuration label created | PASS (variants) |

## Deliberately left unpopulated

- **Fitment:** no synthetic `FITS`. Fitment is engineering-critical, and the catalogue is the only authority.
- **Inventory variation:** all 100 parts are already stocked at all 4 warehouses (existing synthetic data). Making some "not connected" would mean deleting relationships, which is not allowed. Variation comes from quantities and availability states instead (9 parts are Limited or Backorder).
- **Configurations:** the graph already models variants (`MachineVariant` → `VARIANT_OF`). A second configuration model would duplicate it.
- **Engineering data:** no horsepower, capacity, weight, pressure, dimensions, safety ratings, certifications or interchangeability.
- **Dealer on orders:** the schema has no order ↔ dealer relationship, and none was invented.
- **CO_ORDERED_WITH:** not extended from the new orders, to avoid over-synthesising. The existing 75 links stay as they were.
- **Inventory reservations:** allocated order lines do not reduce the existing `AVAILABLE_AT` quantities. That would overwrite existing synthetic values.
