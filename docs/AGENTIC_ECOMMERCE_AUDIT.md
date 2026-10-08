# Agentic E-Commerce: data and code audit

Read-only audit of the live Neo4j graph (read 2026-10-07), the seed files and the application code, against the Agentic E-Commerce requirements (Discovery, Order & Logistics Visibility, Warranty & Traceability). Nothing was changed.

## 1. Existing data inventory

### 1.1 Graph size
**9,874 nodes, 49,249 relationships.** Provenance (`data_status`): nodes SYNTHETIC_DEMO 9,169 · SOURCE_DERIVED 456 · DERIVED 165 · USER_PROVIDED 35 · none 1 (`OrderSequence`, a counter). Relationships: SYNTHETIC_DEMO 48,044 · SOURCE_DERIVED 778 · DERIVED 391 · USER_PROVIDED 36.

### 1.2 By domain
| Domain | Contents | Quality for the target model |
|---|---|---|
| **Product** | 15 machines, 15 machine types, 3 families, 30 variants (serial *ranges* only), 100 parts, 101 categories (2 levels), 279 part specifications, 493 search aliases, 100 legacy references, 30 assemblies, 83 machine specifications | Solid base. Specs are mostly free text (see 1.3). |
| **Fitment** | 219 `FITS` (216 CONFIRMED, 3 CONDITIONAL); 90 `PART_OF` assembly links; 75 `CO_ORDERED_WITH`; 2 `RELATED_COMPONENT` | Current fitment only. No `valid_from/valid_to`, no rule, no DEPRECATED / NOT_APPROVED states. Machine KFT-120 has no fitment. |
| **Catalogue state** | 100 part profiles (VERIFIED 91, UNVERIFIED 5, IDENTIFICATION_REQUIRED 3, AMBIGUOUS 1), 100 prices, `warranty_months` (12 months on 87, 6 on 13) | Good. Warranty is a bare number per part. |
| **Network** | 3 plants (Assen, Coevorden, Lingen), 14 depots, 93 dealers (76 authorised, 10 service partners, 7 industrial specialists), 84 service centres, 40 suppliers, 30 carriers, 10 customers, 173 locations, 126 regions | All **EU only** (27 countries). No USA, Africa, UK or Switzerland. |
| **Sourcing** | 355 `SUPPLIED_BY` (100 primary), 1,243 `STOCKED_BY` (dealer stock), 2,605 `INSTALLS_PART`, 2,595 `CAN_ORDER_PART`, 1,090 `SERVICES_PART`, 27 dealers with "Warranty Service" capability | `SUPPLIED_BY` has a status (all ACTIVE_DEMO) but no approval, regions or validity. |
| **Inventory** | 876 depot rows `AVAILABLE_AT` (IN_STOCK 682, OUT_OF_STOCK 122, ON_ORDER 44, LOW_STOCK 20, UNKNOWN 8), 100 delivery estimates | Usable. Synthetic, labelled. |
| **Logistics** | 4,798 routes, 1,277 legs, 653 freight rates, 22 transport options, 48 terminals (14 seaports, 12 airports, 12 rail, 8 inland ports, 2 cross-docks), 1,948 distances | 8 modes. Longest route 3,026 km / 9 days. **No intercontinental lane.** |
| **Orders / shipments** | 17 orders (14 web-store, 2 app requests, 1 direct order), 28 order lines, 58 status events, 11 shipments, 32 tracking events (IN_TRANSIT 15, PICKED 11, DELIVERED 6), 17 order statuses | Order-to-shipment chain works end to end. The 11 seeded shipments have a carrier, a depot and a customer, but **none is linked to a route** (`USES_ROUTE` exists only for shipments the new order flow creates). |
| **Service** | 60 service plans (interval in hours), 8 compliance requirements, 6 identification requirements | Plans exist; **no work orders, service events or technicians**. |
| **App** | 3 users, 5 carts, 7 cart lines, 6 customer requests | Application records, `source_id = APP-SESSION`. |

### 1.3 Findings
- **Specifications:** of 279 specs, 108 are "Note segment" and 100 are "Spec Note" (free text). Only about 70 are structured (Voltage, Volume, Filter rating, Pressure, Bore, Stroke, Flow rate, Displacement). Names are not normalised (`bore` / `Bore`, `stroke`).
- **Part keys:** parts carry `brand` and `origin_plant`, but no `oem_status`, description or technical terms. Aliases average 4.5 per part (range 2–6), and some are single words such as "line", "pipe", "cartridge".
- **Machines:** no `serial_number`, `model_year` or `status`. Only variant serial ranges (30). No machine instances exist.
- **Provenance:** present on every node except the counter. It uses `source_id`, `data_status`, `provenance_type`, `confidence` and `last_updated`; there are no `effective_from/to` or `ingestion_timestamp`.
- **Duplicates:** no duplicate part numbers. Every part has a fitment and a supplier.
- **Other:** `ComplianceRequirement` names and `OrderStatus` statuses read back as null under the field names I queried, so they need a second look.
- **Existing audit files** (`backend/graph/audits/`: synthetic data inventory, missing data register, relationship matrices) are the previous round's inventory. They predate the EU foundation and the ordering flow.

### 1.4 Seed files and ingestion
| Source | What it is |
|---|---|
| `backend/data/catalogue/noordveld-parts-catalog.xlsx` and `processed/noordveld-complete-dataset-synthetic-demo.xlsx` | The original source workbooks (parts, machines, fitment and synthetic sheets) |
| `backend/graph/cypher/*.cypher` (~2.8 MB) | Generated Cypher that loads the workbooks (`graph_build.py`, `aura_import.py`) |
| `backend/scripts/eu_foundation/*.py` | **Python generators** for dealers, suppliers, depots, routes and rates. They are deterministic, idempotent and carry a checksum. |
| `backend/scripts/order_flow/migrate.py` | Order-status migration |
| `backend/scripts/operational_demo/` | Empty; the OPS batch generator is missing |
| `backend/data/eu_foundation/*.json` | Audit baselines, seed-run records, a restore backup (1.2 MB), generated validation output |

Ingestion today is **workbook → Cypher** (original data) and **Python generators → graph** (operational data). There is no CSV/JSON/API ingestion with a canonical model and validation layer, which the target architecture calls for.

## 2. Hard-coded values inventory
The application is already largely data-driven: no part numbers, prices, stock or suppliers sit in application code. What is hard-coded:

| Where | What | Verdict |
|---|---|---|
| `backend/app/services/site.py:16` | `FILM_MACHINE = "NV-4500"`, `FILM_PART = "PRT-002"`, `FILM_CUSTOMER = "CUS-008"` (which records the launch film features) | **Move to data**: a "featured scenario" record in the graph |
| `backend/app/core/geography.py` | `CITY_COORDINATES` (25 cities) used for map pins | **Move to data**: Location already carries coordinates on dealers; extend to all locations |
| `backend/app/core/geography.py` | `COUNTRY_NAMES` (33) | Keep as reference data, or take from a Country node |
| `backend/app/services/order_flow.py` | `ACTIONS` table, stages, status labels, `SHIPMENT_EFFECT`, `SERVICE_EFFECT` | Keep: workflow rules, tested. Candidate for configuration later. |
| `backend/app/services/orders.py` | `FLOW`, `TRANSITIONS`, `QUEUE`, labels (earlier-channel orders) | Keep |
| `backend/app/services/fulfilment.py` | `STATES`, `KNOWN_AVAILABLE`, `LOW_STOCK_AT = 5`, cost note | Keep (the threshold matches the seeded data) |
| `backend/app/agent/supply.py`, `ranking.py` | Availability labels and rank order | Keep: ranking policy |
| `backend/app/agent/service.py` | Step labels, out-of-scope text | Keep: UI wording |
| `backend/app/api/routes/orders.py`, `schemas/cart.py` | Quantity limits (99 and 999) | Reconcile (known inconsistency) |
| `backend/app/llm/prompts.py` | Prompt rules (no business facts) | Keep |
| `frontend/src/data/content.ts`, `site.ts` | Navigation, labels, adapter from the API | Keep: labels only |
| `frontend/agentic-commerce/src/data/{stages,process}.ts`, `launch/launchData.ts` | Narrative copy for the Agentic page (commerce stages, process) | Keep as page copy; replace once the new page is built |
| `backend/scripts/eu_foundation/*.py` | The whole operational dataset is generated from code | **Move to ingested data files** (CSV/JSON) per the target architecture |

No `if machine == X` style business rules were found. No `Japan = 91 days` exists anywhere. No dealer, route or ETA is hard-coded in the application.

## 3. Missing data inventory
Against the target model (spec section 5 onward):

| Required | In graph today | Gap |
|---|---|---|
| Machine instance (serial, model year, owner, location, status) | No. Variants have serial ranges. | **Missing** |
| Fitment context (`valid_from/to`, rule, approval status, DEPRECATED / NOT_APPROVED) | Status CONFIRMED / CONDITIONAL only | **Partial** |
| Approved source (part → OEM/supplier/dealer, regions, validity) | `SUPPLIED_BY` + `is_primary`, status ACTIVE_DEMO | **Partial**: no approval, regions or validity |
| Natural-language discovery data (common names, symptoms, technical terms) | Aliases (2–6 per part), name, subcategory | **Partial**: no symptoms or technical terms |
| Structured specifications | About 70 of 279 structured | **Partial** |
| Customer / order / order line | Present | **Present** (dealer on order only for direct orders) |
| Shipment, tracking event | Present (11 / 32) | **Partial**: none of the 11 seeded shipments is linked to a route; no `planned_eta`, `actual_eta`, `departure_date` |
| Route, route leg, ports, terminals | Present (EU only) | **Partial**: no intercontinental, no actual vs planned duration, no leg status per shipment |
| Sea vs air comparison for the same lane | Not for the same origin and destination | **Missing** |
| USA and Africa network (dealers, destinations, ports, airports, routes, rates) | None | **Missing** |
| UK and Switzerland | None | **Missing** |
| Technician (certification, specialisation) | No | **Missing** |
| Work order / service event | No (service plans only) | **Missing** |
| Installation event (machine, part, serial, dealer, technician, work order, dates) | No | **Missing** |
| Removal / replacement history | No | **Missing** |
| Warranty policy (coverage, period, conditions, start rule) | `warranty_months` only | **Partial** |
| Warranty claim | No | **Missing** |
| Evidence layer (service report, inspection, record) | No | **Missing** |
| Provenance `effective_from/to`, `ingestion_timestamp` | Partly (`last_updated`) | **Partial** |
| Real / synthetic / reference classification | `data_status` exists | **Present** (extend vocabulary) |

## 4. Migration plan

### Keep (as is)
Machines, parts, categories, aliases, fitment links, assemblies, plants, suppliers, dealers, depots, locations, the EU transport network, inventory, orders, shipments and tracking, the direct-order flow, Agentic Shopping, Parts Intelligence, provenance fields, and the integrity checksum.

### Transform
- **Fitment:** add `valid_from`, `valid_to`, `fitment_rule` and an extended `approval_status` on `FITS`.
- **Sourcing → approved source:** add `approval_status`, `approved_regions`, `valid_from/to` to `SUPPLIED_BY` (or an `APPROVED_SOURCE` relationship).
- **Specifications:** normalise names (`bore` → `Bore`) and split the 208 free-text notes into structured fields where the text allows. Keep the text for discovery.
- **Parts:** add description, common names, technical terms and symptoms for natural-language discovery. Add `oem_status`.
- **Machines:** add `serial_number`, `model_year`, `status`. Create machine instances linked to variants.
- **Shipments:** add `planned_eta`, `actual_eta`, `departure_date` and `USES_ROUTE`; link the 11 route-less seeded shipments.
- **Warranty:** replace the bare `warranty_months` with `WarrantyPolicy` nodes (the existing value becomes the default).
- **Provenance:** add `effective_from/to` and `ingestion_timestamp`; extend the source-type vocabulary.

### Move into data
- `FILM_*` scenario choices into a graph record.
- `CITY_COORDINATES` into location coordinates.
- The `eu_foundation` generators' output into versioned CSV/JSON ingest files with a loader that validates and is idempotent.

### Newly ingested (synthetic, labelled `SYNTHETIC_DEMO`)
1. **Network:** UK, Switzerland, Norway, USA (Houston, Savannah, Chicago, Los Angeles), Africa (Lagos, Tema, Durban, Mombasa, Casablanca). About 12 locations, 25 dealers, destinations, a seaport and an airport each.
2. **Routes from the Netherlands:** deep-sea, air, sea-plus-road, customs legs, transit days, freight estimates. Stored per route, never as a universal value.
3. **Lifecycle:** machine instances, technicians, work orders, installation events, replacement history, warranty policies, claims, evidence records.
4. **Scenario seeds** for the three demo flows (a hydraulic pump with a sea route in transit and an air alternative; a pump with a full install and claim history).

### Remove
Nothing in the graph. Candidates once replaced: the Agentic page narrative copy, the `FILM_*` constants, the empty `operational_demo/` package, and the unused generator imports flagged earlier.

### Build order
1. **Canonical model and ingest layer:** define node and relationship contracts, loader, validation, idempotency and checksum coverage.
2. **Network and routes:** geography, then transport data.
3. **Lifecycle model:** machines, installations, work orders, warranty, claims, evidence.
4. **Context engine and the three agent flows:** Discovery (approved source added), Logistics (tracking, ETA, sea vs air), Warranty (history, decision).
5. **UI** that shows the reasoning path, then validation with a traceable source path for every answer.

## 5. Decisions needed
1. Final location list (UK, Switzerland, Norway; four US cities; five African cities).
2. Sea transit values: realistic (weeks) or one deliberately slow demo lane.
3. Warranty depth: simple (period from install date, authorised dealer, approved part) or richer (wear parts, repeat failures, claim workflow).
4. Ingest format for the canonical layer: CSV, JSON or both.
