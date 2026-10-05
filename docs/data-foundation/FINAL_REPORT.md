# Noordveld Machinery B.V. — European operational data foundation: final report

Scope: data foundation and knowledge graph only, in Neo4j AuraDB. No UI, Quote Request, Agentic Shopping, Parts Store redesign or Parts Intelligence intent change. Not pushed to GitHub.
Batch `EUFOUND-2026-10-04`, data source `SRC-005`. Every number below was read from the live graph (`backend/data/eu_foundation/validation.json`, `audit_before.json`, `scenarios.json`, `seed_run_*.json`).

> **Status, 2026-10-05: read this first.** This report describes the foundation as it was first seeded. Three later changes altered it; every figure they affect below is marked *(superseded)* and the current figures are in the table at the end of this block.
> 1. **The synthetic customer master was removed.** The 120 EU customers, their 120 contacts and 120 customer-only addresses, plus 14 batch industries, locations and regions that only they kept alive, were deleted (374 nodes, 1,131 relationships). The 230 EU ship-tos, all routes, legs, freight rates, distances, dealers, suppliers, depots and inventory were kept. The 230 ship-tos are therefore **unowned delivery destinations** now (the `HAS_SHIP_TO` links to the removed customers are gone). Recovery file: `backend/data/eu_foundation/cleanup_backup_1791183770.json`. Details: [CLEANUP_DEPENDENCY_REPORT.md](CLEANUP_DEPENDENCY_REPORT.md). The generator no longer creates customers (`build_entities.build_customers` now only generates the ship-to destinations).
> 2. **Second-source suppliers.** 8 explicit `SUPPLIED_BY` relationships (batch `SUPPLY-2026-10-05`, `scripts/eu_foundation/supplier_top_up.py`) give common verified parts a second supplier. No supplier was added. Parts with a single supplier: 11 → 3 (PRT-018, PRT-027, PRT-097, machine-specific assemblies kept single-source on purpose). Record: `supplier_top_up_result.json`.
> 3. **Validation and checksum.** `validate.py` now runs **72 checks** (it was 65), including a *SOURCE/DERIVED DATA INTEGRITY CHECKSUM* that covers SOURCE_DERIVED, DERIVED and the supplied (non-app-written) USER_PROVIDED seed records, and excludes records the running app writes (`source_id = 'APP-SESSION'`: orders, carts, order statuses). `scripts/eu_foundation/inspect_*.py` were one-off helpers and have been removed.
>
> | Current figure (live graph, 2026-10-05) | Value |
> |---|---|
> | Nodes / relationships (whole graph, includes app-written order and cart records) | 9,822 / 49,239 |
> | Batch `EUFOUND-2026-10-04` | 7,647 nodes / 44,569 relationships (was 8,021 / 45,700) |
> | Dealers (service centres) / suppliers | 93 (84) / 40, with 355 supplier→part links |
> | Customers | 10 (the original ones only) |
> | Ship-tos | 250 (20 original, 230 EU), unowned destinations |
> | Depots / carriers / transport options / terminals | 14 / 30 / 22 / 48 |
> | Routes / legs / freight-rate records / distances | 4,798 / 1,277 / 653 (498 from this batch) / 1,948 |
> | Depot inventory rows (`AVAILABLE_AT`) | 876 |
> | Provenance, nodes | SOURCE_DERIVED 456 · DERIVED 165 · USER_PROVIDED 32 · SYNTHETIC_DEMO 9,169 |
> | Provenance, relationships | SOURCE_DERIVED 778 · DERIVED 391 · USER_PROVIDED 26 · SYNTHETIC_DEMO 48,044 |
>
> The direct-order flow that now uses this network is described in [../ORDER_FLOW.md](../ORDER_FLOW.md).

## 1. Research summary
See [RESEARCH.md](RESEARCH.md). In short: EU27 only (no US, no UK); NL and DE are densest because they are home markets and the densest dealer/industrial regions; road is the default mode (it carries most EU inland freight); rail, inland waterway, short-sea and air are offered only where terminals and a plausible corridor exist and where the detour against the direct road route is at most 1.5×.

## 2. Existing graph before (audit)
| | Before |
|---|---|
| Nodes / relationships | 2,164 / 4,662 |
| Parts / machines / fitments / part specifications | 100 / 15 / 219 / 279 (plus 83 machine specifications) |
| Dealers / suppliers / customers | 15 / 12 / 10 |
| Depots (Warehouse) / ship-tos / carriers | 4 / 20 / 5 |
| Transport options / freight rates / shipping rate cards | 8 / 155 / 8 |
| Orders / order statuses | 16 / 6 (NEW … DELIVERED) |
| Locations / regions | 5 / 14 |
| Earlier batches present | `ENRICH-2026-10-03`, `OPS-2026-10-04` |

Reused, not duplicated: `Carrier` (providers), `TransportOption`, `FreightRate` + `ShippingRate` rate cards, `DISTANCE_TO`, `ShipTo`/`HAS_SHIP_TO`, contacts, `Warehouse` (depot), `AVAILABLE_AT` (depot stock), the Order status vocabulary and the Price nodes.

## 3. Data added
8,021 nodes and 45,700 relationships (all `SYNTHETIC_DEMO`); graph then 10,185 nodes / 50,362 relationships *(superseded: see the status block)*. Second and third `seed.py apply` runs created 0 nodes and 0 relationships.

| Entity | Added | Total now |
|---|---|---|
| Dealers (with service centres 84, contacts 78) | 78 | 93 |
| Suppliers (contacts 42) | 28 | 40 |
| Customers (contacts 120, 13 industries) *(superseded: removed 2026-10-05)* | 120 | 10 |
| Ship-tos (own entity; *were* owned by one customer, now unowned destinations) | 230 | 250 |
| Depots | 10 | 14 (plant ≠ depot; WH-005 … WH-014) |
| Transport providers (`Carrier`) | 25 | 30 |
| Transport options | 14 | 22 |
| Terminals (14 sea ports, 8 inland ports, 12 rail, 12 air cargo, 2 cross-docks) | 48 | 48 |
| Routes / legs / freight-rate records | 4,798 / 1,277 / 498 | — |
| Depot inventory rows (`AVAILABLE_AT`) | 476 | — |
| Dealer–part links | STOCKED_BY 928, CAN_ORDER_PART 2,595, INSTALLS_PART 2,605, SERVICES_PART 1,090 | — |
| Supplier–part links (explicit `SUPPLIED_BY`) | 190 | — |
| Dealer territories (`SERVES_TERRITORY`, explicit) | 317 | — |

## 4. Coverage by country
Dealers (total): NL 14, DE 14, FR 7, IT 6, PL 6, BE 5, ES 5, AT 4, CZ 4, DK 3, SE 3, FI 2, GR 2, HU 2, PT 2, RO 2, SK 2, BG, CY, EE, HR, IE, LT, LU, LV, MT, SI 1 each — all 27 member states.
Ship-tos: NL 52, DE 49, BE 23, FR 19, PL 17, IT 16, ES 11, AT 7, CZ 7, SE 5, DK 5, FI 4, HU 4, PT 4, RO 4, CY 3, HR 3, then 1–2 for the rest — all 27 states.
Suppliers (11 countries): DE 11, NL 9, BE 3, FR 3, IT 3, PL 3, AT 2, CZ 2, ES 2, DK 1, SE 1.
Customers: *(superseded: the synthetic customers were removed)*. Depots: NL 4, DE 3 (incl. WH-002), BE, FR 2, PL, CZ, AT, IT.

## 5. Transport
Routes by main mode: ROAD 3,582 · RAIL 318 · INLAND_WATERWAY 74 · SHORT_SEA 76 · AIR 443 · MULTIMODAL 305. Every route has ordered legs (road first mile → terminal → trunk → terminal → road final mile → ship-to) and a rate record. Legs by mode: ROAD 1,221, RAIL 13, INLAND_WATERWAY 9, SHORT_SEA 13, AIR 21.
Distances (`DISTANCE_TO`: 1,868 new + 80 existing = 1,948; by type: ROAD 1,840, AIR 66, SEA 19, RAIL 14, WATERWAY 9, all `SYNTHETIC_*_ESTIMATE`) — always haversine × per-mode circuity (road 1.30, rail 1.20, waterway 1.35, sea 1.15, air 1.0), with `straight_line_km` kept separately. Never presented as measured.
Rates: 498 `FreightRate` nodes, bands LOCAL 80 · REGIONAL 96 · NATIONAL 101 · LONG_DISTANCE 111 · CONTINENTAL 87 · TRANS_EUROPEAN 23. Part, transport (`total_transport_cost`), handling and total are separate fields, in EUR, all labelled synthetic; nothing is a real tariff. Delivery estimates carry `estimate_basis = ESTIMATED`.
Road-only or limited-mode destinations (no plausible rail/water/sea corridor in the model): BG, LV, PT, SI (road only); EE, FI (road, air); islands CY, IE, MT (sea/multimodal).

## 6. Provenance counts (live graph)
| Class | Nodes | Relationships |
|---|---|---|
| SOURCE_DERIVED | 456 | 778 |
| DERIVED | 165 | 391 |
| USER_PROVIDED *(then 21 / 26; now 32 / 26 because the app writes orders and carts)* | 32 | 26 |
| SYNTHETIC_DEMO (= SYNTHETIC_DEMO_DATA) *(then 9,543 / 49,167)* | 9,169 | 48,044 |
| UNKNOWN / NOT_CONNECTED | 0 | 0 |
Everything added in this batch (8,021 / 45,700) is SYNTHETIC_DEMO. The source-data checksum (hash of all SOURCE_DERIVED / DERIVED / USER_PROVIDED nodes and relationships; today the SOURCE/DERIVED DATA INTEGRITY CHECKSUM, see the status block) was identical before and after every seed run. See [CLASSIFICATION.md](CLASSIFICATION.md).

## 7. Integrity counts (65 checks at first seeding, 65 passed; 72 checks and 72 passed today)
Zero for each of: dealers without location / family support / territory; suppliers without parts; customers without ship-to; ship-tos without owner or route; depots without location; routes without depot, ship-to, option, rate or legs; legs not attached to a route; multimodal routes with fewer than two modes; negative stock; UNKNOWN stock with a quantity; OUT_OF_STOCK with stock; IN_STOCK without stock; duplicate ids or `rel_id`; rate totals not equal to components; new fitment/supersession/interchange relationships; new Part/Machine/Specification/Plant nodes; supplier→machine or dealer→ship-to links; customer distance links. Catalogue unchanged: 100 parts, 15 machines, 219 fitments, 279 part specs, 3 plants, 3 business units.
Depot stock now: IN_STOCK 682, LOW_STOCK 20, ON_ORDER 44, OUT_OF_STOCK 122, UNKNOWN 8 (of which this batch: 377 / 20 / 44 / 27 / 8).

## 8. End-to-end scenarios (14 / 14 pass)
Each checks stock at the depot → connected leg chain → distances sum to route → EUR cost components add up → ESTIMATED delivery → road default exists → destination dealer configured → ship-to owned by a customer.
| Scenario | Depot → ship-to | Option | km | days | EUR freight |
|---|---|---|---|---|---|
| NL domestic | WH-001 → SHT-001-1 | STANDARD_ROAD_EU | 80.7 | 2 | 12.96 |
| DE domestic | WH-002 → SHT-002-2 | STANDARD_ROAD_EU | 85.5 | 2 | 12.96 |
| NL → DE | WH-001 → SHT-007-1 | STANDARD_ROAD_EU | 77.1 | 2 | 24.96 |
| DE → FR | WH-002 → SHT-060-1 | STANDARD_ROAD_EU | 490.8 | 2 | 43.32 |
| NL → BE | WH-005 → SHT-069-3 | STANDARD_ROAD_EU | 115.4 | 2 | 32.52 |
| NL → PL | WH-001 → SHT-083-2 | STANDARD_ROAD_EU | 990.2 | 3 | 60.60 |
| DE → AT | WH-007 → SHT-097-2 | STANDARD_ROAD_EU | 317.8 | 2 | 43.32 |
| DE → CZ | WH-007 → SHT-102-1 | STANDARD_ROAD_EU | 224.4 | 2 | 32.52 |
| NL → FR multimodal | WH-001 → SHT-062-3 | ROAD_WATER_ROAD | 494.9 | 5 | 66.13 |
| Urgent air NL → ES (fastest) | WH-001 → SHT-092-2 | AIR_CRITICAL | 1,868.0 | 2 | 949.04 |
| Urgent air DE → IT (fastest) | WH-002 → SHT-077-1 | AIR_CRITICAL | 950.3 | 2 | 616.40 |
| Rail DE → IT | WH-002 → SHT-075-1 | RAIL_STANDARD | 1,283.1 | 6 | 107.39 |
| Inland waterway NL → DE | WH-001 → SHT-017-2 | INLAND_WATERWAY | 932.9 | 6 | 77.80 |
| Short-sea NL → SE | WH-001 → SHT-108-2 | SHORT_SEA | 889.3 | 5 | 84.93 |

## 9. Files changed / added
Added: `backend/scripts/eu_foundation/` (common, geo, names, model, build_entities, build_supply, build_transport, build, seed, validate, scenarios, audit_before; plus `cleanup_customers` and `supplier_top_up` added later), `backend/data/eu_foundation/` (audit, plan, seed-run, validation, scenario JSON), `backend/tests/test_eu_foundation.py`, `docs/data-foundation/`.
Modified (test expectations only, because live depot stock legitimately grew from 81 units/4 warehouses to 172 units/8 warehouses for NVM-1020-FL): `backend/tests/test_agent.py`, `backend/tests/test_intelligence_contract.py`. No application code changed. Full backend suite after the change: all pass (the two data-snapshot assertions above updated; `test_eu_foundation.py` 5 passed).

## 10. Neo4j labels and relationship types added
Labels (27): Address, AirportCargoTerminal, Capability, Carrier, CrossDock, Customer, CustomerContact, DataSource, Dealer, DealerContact, FreightRate, Industry, InlandPort, Location, PostalArea, RailTerminal, Region, SeaPort, ServiceCentre, ShipTo, Supplier, SupplierContact, TransportLeg, TransportOption, TransportRoute, TransportTerminal, Warehouse (12 labels did not exist before: AirportCargoTerminal, Capability, CrossDock, Industry, InlandPort, PostalArea, RailTerminal, SeaPort, ServiceCentre, TransportLeg, TransportRoute, TransportTerminal; the rest are existing labels with new instances).
New relationship types (22): CAN_ORDER_PART, FROM_DEPOT, HAS_CAPABILITY, HAS_LEG, HAS_SERVICE_CENTRE, INSTALLABLE_BY, INSTALLS_PART, IN_INDUSTRY, LEG_FROM, LEG_TO, OPERATES_MACHINE, PRICED_BY, REPLENISHED_FROM, REPLENISHES_DEPOT, REQUIRES_SERVICE, SELLS_MACHINE_FAMILY, SERVES_TERRITORY, SERVICES_MACHINE_FAMILY, SERVICES_PART, SUPPORTS_MACHINE, TO_SHIP_TO, USES_OPTION (the other types added reuse existing names). 68 constraints/indexes added (unique id per label, unique `rel_id` per relationship type). Full per-label and per-type counts: `validation.json`.

## 11. Known caveats
- `SYNTHETIC_DEMO` is the project's stored spelling of SYNTHETIC_DEMO_DATA; `demo_marker = SYNTHETIC_DEMO_DATA` is also set.
- Order/fulfilment: only the relationship contract is documented ([ORDER_FOUNDATION.md](ORDER_FOUNDATION.md)); `SHIPS_TO`, `RECEIVED_BY`, `FULFILLED_FROM`, `USES_TRANSPORT` are not instantiated and no new orders were created.
- The earlier existing depots hold every catalogue part; new depots hold a selective subset. Parts marked BACKORDER/LIMITED receive no new depot stock.
- Dealer machine-family support uses `SUPPORTS_MACHINE` and `SERVES_FAMILY` rather than a second `SUPPORTED_BY` edge.
- Routes use the nearest two depots, the nearest in-country depot and the two principal depots (WH-001, WH-002) within 1,800 km. Non-road options exceeding 1.5× the direct road distance are not generated. During development, 385 orphan legs and the routes/legs/rates made obsolete by tightening the routing rules were removed from this same batch (`seed.py` prune is scoped to this batch id); no other batch or source data was deleted.
- Parts Store `PART_SUMMARIES` sums stock per part; rows with `UNKNOWN` stock carry no quantity (null), which that code was not previously exposed to — verify when the Store UI next touches depot stock.
- Ship-to coordinates and city centres are approximate and synthetic. No real dealer, customer, supplier or carrier names, contacts or rates were used.

## 12. How to run
```
python backend/scripts/eu_foundation/build.py          # plan only
python backend/scripts/eu_foundation/seed.py apply     # additive + idempotent; checksum before/after
python backend/scripts/eu_foundation/validate.py       # 72 checks (read-only; writes validation.json)
python backend/scripts/eu_foundation/scenarios.py      # 14 scenarios
```
Standing reminder: rotate the Aura database password, as it has been used from this machine's `.env`.
