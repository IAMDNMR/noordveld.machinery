# EU foundation cleanup: pre-deletion dependency report

Status: **historical pre-deletion audit.** It was written before anything was deleted, from the live graph on 2026-10-05; the outcome is in the section at the end. Batch `EUFOUND-2026-10-04` (8,021 nodes / 45,700 relationships, all `SYNTHETIC_DEMO`).

## 0. Two facts that change the premise
1. **The current checkout does not capture Name / Email / Phone / Company.** `CheckoutPage` has no form. The order's customer is the signed-in `AppUser -[:ACTS_FOR]-> Customer`, and the app has exactly two end users (`USR-EU-001` → CUS-008, `USR-EU-002` → CUS-001). The customer entered "at order time" does not exist yet (see ORDER_JOURNEY_AUDIT.md).
2. **94% of the EU transport network is addressed to the synthetic customer ship-tos.** All 4,798 routes end at a `ShipTo` through `TO_SHIP_TO`; 4,514 end at the 230 EU ship-tos. Deleting those ship-tos removes almost the whole route/leg/rate layer, which conflicts with "do not remove the transport network". This needs a decision (section 5).

## 1. Customer data created by the batch
| Item | Count | Referenced by orders / users / carts / shipments / delivery estimates / app code / Parts Intelligence |
|---|---|---|
| `Customer` (EU) | 120 | **0** (checked ORDERED_BY, ACTS_FOR, OPENED_BY, DELIVERS_TO_CUSTOMER, TO_CUSTOMER) |
| `CustomerContact` (EU) | 120 | 0 (only `HAS_CONTACT` from their customer) |
| `ShipTo` (EU) | 230 | 0 orders / shipments. Referenced only by routes, legs, distances, `HAS_SHIP_TO` |

Application code (`backend/app`, `frontend/src`) never references `ShipTo`, `TransportRoute`, `TransportLeg`, `FreightRate` or `CustomerContact`. The only code that does is `backend/scripts/eu_foundation/*` and `backend/tests/test_eu_foundation.py`.

Relationships that go with the 120 customers: HAS_CONTACT 120, HAS_SHIP_TO 230, IN_INDUSTRY 120, LOCATED_AT_ADDRESS 120, LOCATED_IN 120, OPERATES_MACHINE 293 (the 15 machines are untouched). Their 120 customer-only `Address` nodes would be orphaned.

## 2. Customer data to KEEP (not part of the batch)
- The 10 original customers CUS-001…010 and their 10 `CustomerContact` + 20 `ShipTo` (batch `OPS-2026-10-04`). They are used by the 16 orders, 2 AppUsers, 5 carts, 6 customer requests, 11 shipments and 40 DeliveryEstimate→Customer links, and by the site film (CUS-008).
- All 16 existing orders, order lines, status events, shipments and tracking events.

## 3. ShipTo classification
| Class | Meaning | Count | Action |
|---|---|---|---|
| A | EU, owned by a synthetic customer, no order dependency | 230 | candidate (see section 5) |
| B | Generic logistics destinations | 0 as modelled | none exist: every EU ship-to is customer-owned |
| C | Source-derived / user-provided ship-tos | 0 | none |
| D | Referenced by orders / operational data | 20 (the OPS-batch ship-tos of CUS-001…010, 284 routes) | keep |

**Model issue to report, not silently change:** the batch models every delivery destination as a customer-owned ship-to. The requirement (dealer / receiver / ship-to as separate things) needs generic destinations, but there is no such entity today. The batch also deliberately never links a dealer to a ship-to.

## 4. Transport dependencies of the 230 EU ship-tos
| Item | Total | Depends only on the 230 ship-tos | Retained |
|---|---|---|---|
| Routes | 4,798 | 4,514 | 284 (to the 20 OPS ship-tos) |
| Legs | 1,277 | 1,200 | 77 (73 retained-only + 4 shared) |
| Freight-rate records (batch) | 498 | 368 | 130 (shared with retained routes) |
| `DISTANCE_TO` into ship-tos | 1,868 batch | 1,563 (833 from depots, 730 from terminals) | 305 batch terminal↔terminal/depot↔terminal + 80 original |
| Terminals | 48 | 43 | 3 (2 unused today) |

Not touched in any case: 14 depots, 93 dealers, 40 suppliers, 30 carriers, 22 transport options, 155 original rate cards, inventory (`AVAILABLE_AT`), dealer/supplier part links, the 100 parts / 15 machines / 219 fitments / 279 specs / 3 plants.

## 5. Decision needed before any ship-to / route deletion
- **Option 1 (recommended): delete customer master only.** Remove the 120 EU customers, 120 contacts and their customer-only relationships and addresses (zero dependencies). Keep the 230 EU ship-tos as unowned destinations with their 4,514 routes/legs/rates, and report that they are customer-style destinations, not a real destination model. Fully reversible by re-running the existing seed (it is deterministic), and nothing else changes.
- **Option 2: also delete the 230 ship-tos.** This removes 4,514 routes, 1,200 legs, 368 rates, 1,563 distances and 43 terminals, leaving 284 routes and 3 terminals. The "valid transport network" then no longer covers the EU, and a destination-neutral model would have to be designed and seeded to replace it (new data, which you ruled out).

## 6. Cleanup safeguards (applies to either option)
Delete only `n.enrichment_batch = 'EUFOUND-2026-10-04'` nodes in an allow-listed set of labels, run in batches, idempotent, with a before/after source-checksum check (`audit_before.source_checksum`), a JSON export of the deleted ids and properties first (for restore), and `eu_foundation/validate.py` and `test_eu_foundation.py` updated to stop expecting customers (100–200) and ship-tos (200–300).

## 7. Outcome (executed 2026-10-05)
Option 1 was chosen and executed with `scripts/eu_foundation/cleanup_customers.py` (idempotent; a second run found nothing):
* Deleted: 120 `Customer`, 120 `CustomerContact`, 120 customer-only `Address`, plus 8 `Industry`, 4 `Location` and 2 `Region` nodes of this batch that only they kept alive: **374 nodes and 1,131 relationships**.
* Kept: the 10 original customers, their 10 contacts and 20 ship-tos, all 16 orders, shipments and tracking, the 230 EU ship-tos (now unowned destinations) and the whole transport network (4,798 routes, 1,277 legs, 498 batch freight rates, 1,948 distances, 48 terminals), dealers, suppliers, depots and inventory.
* The source/derived checksum was unchanged before and after. Every deleted node and relationship (labels, properties, endpoints) is in `backend/data/eu_foundation/cleanup_backup_1791183770.json`, which is the restore point.
* The generator was changed so a re-seed cannot bring the customers back; the plan matches the live graph (7,647 nodes / 44,569 relationships).
