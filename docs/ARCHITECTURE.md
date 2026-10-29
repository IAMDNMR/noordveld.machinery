# Architecture

How the Noordveld backend turns the graph into answers and orders. One document, in build order: the canonical data layer, the logistics network,
lifecycle and warranty, the Commerce Context Engine, the agentic commerce layer and the direct-order flow. The Spark ordering journey, the profile and
Parts Intelligence are described in `backend/README.md` and `backend/INTELLIGENCE.md`.

## Contents

- [Canonical data model and ingestion](#canonical-data-model)
- [Logistics network, routes and shipments](#logistics-network)
- [Machine lifecycle, warranty and traceability](#lifecycle-and-warranty)
- [Commerce Context Engine](#commerce-context-engine)
- [Agentic commerce: contracts, agent and workspace](#commerce-agent)
- [Direct-order flow](#order-flow)

<a id="canonical-data-model"></a>

## Canonical data model and ingestion

*Originally `CANONICAL_DATA_MODEL.md`; Canonical data model and ingestion (schema 1.0).*

Phase 2 (global network, routes, shipments, tracking and the shipment context) is described in [LOGISTICS_NETWORK.md](#logistics-network). Phase 3 (machine lifecycle, installations, warranty evaluation and traceability, with the renamed installation relationships) is described in [LIFECYCLE_WARRANTY.md](#lifecycle-and-warranty).

Phase 1 of the Agentic E-Commerce data foundation: typed data contracts, a JSON/CSV ingestion engine, validation, provenance, idempotency and integrity coverage, plus the migration of what already exists. No workflows, UI or prompts were changed.

### 1. How it fits the existing system
Code is in `backend/app/canonical/`, data in `backend/data/canonical/`, the command line in `backend/scripts/canonical.py`. It reuses the existing Neo4j connection settings, the provenance vocabulary, the unique `rel_id` convention, the `SRC-*` source ids and the SOURCE/DERIVED DATA INTEGRITY CHECKSUM (`scripts/eu_foundation/audit_before.py`, unchanged). Nothing existing was replaced.

### 2. Existing concept → canonical concept → graph → migration
| Existing concept | Canonical | Existing label / relationship | Migration |
|---|---|---|---|
| Machine | `Machine` | `Machine` (SOURCE_DERIVED), `BRANDED_AS`→`BusinessUnit`, `MANUFACTURED_AT`→`Plant` | Exported; **verify only** (protected) |
| Machine variant | referenced by `MachineInstance.variant_id` | `MachineVariant`, `VARIANT_OF` | Not duplicated; referenced |
| Physical machine | `MachineInstance` | none | **New** label, `INSTANCE_OF_VARIANT`, `INSTANCE_OF_MACHINE`, `OWNED_BY_CUSTOMER`, `LOCATED_AT` |
| Part | `Part` | `Part` (SOURCE_DERIVED) | Exported; verify only |
| Part discovery text | `Part.description / common_names / technical_terms / symptoms / oem_status` | `PartCatalogProfile` (synthetic, `PROFILES_PART`) | Written to the **profile**, never to the protected Part |
| Aliases | `Part.aliases`, `Part.common_names` | `SearchAlias` (`CODE_VARIANT`, `SYNONYM_DEMO`) | Preserved: all aliases exported, `SYNONYM_DEMO` ones become `common_names` |
| Category | `Category` | `Category`, `SUBCATEGORY_OF`, `IN_CATEGORY`, `IN_SUBCATEGORY` | Exported; verify only |
| Specification | `Specification` | `PartSpecification`, `HAS_SPECIFICATION` | Exported with normalised names; verify only |
| Supplier | `Supplier` | `Supplier` (synthetic) | Exported; merge (round-trip identical) |
| Dealer | `Dealer` | `Dealer` | Exported; merge (identical) |
| Plant | `Plant` | `Plant` (USER_PROVIDED, SRC-BRIEF) | Exported; verify only |
| Location | `Location` (one namespace with `graph_label`) | `Plant`, `Warehouse`, `ShipTo`, `Location` | Exported (440); merge for synthetic, verify protected |
| Fitment | `Fitment` | `FITS` (SOURCE_DERIVED) | Context stored in new `FitmentContext` linked by `FITMENT_OF_PART` / `FITMENT_ON_MACHINE`; `CONFIRMED`→`APPROVED` |
| Approved source | `ApprovedSource` | `SUPPLIED_BY` (synthetic) supplies; **`APPROVED_SOURCE`** approves | New relationship, derived from active `SUPPLIED_BY` |
| Assembly link | `AssemblyLink` | `PART_OF` | Exported; verify |
| Legacy mapping | `LegacyPartMapping` | `HAS_LEGACY_REFERENCE` | Exported; verify |
| Customer / order / order line | `Customer`, `Order`, `OrderLine` | same labels; `ORDERED_BY`, `CONTAINS_LINE` | Exported (app-written orders excluded); orders and lines **verify only** |
| Inventory | `Inventory` | `AVAILABLE_AT` (depot) | Exported (876); verify only: live reservations stay the app's |
| Pricing | `Pricing` | `Price`, `PRICES_PART` | Exported; merge (identical) |
| Route | `Route` | `TransportRoute`, `PRICED_BY`→`FreightRate` | Exported (4,798); merge (identical) |
| Route leg | `RouteLeg` | `TransportLeg`, `HAS_LEG` | Exported (7,816 route-leg rows); verify |
| Shipment | `Shipment` | `Shipment` | Exported; merge: adds `departure_date`, `actual_eta`, `remediation_flags` |
| Tracking event | `TrackingEvent` | `TrackingEvent`, `HAS_TRACKING_EVENT` | Exported; merge: adds `event_type` |
| Technician, work order, installation, replacement | same names | none | **New** labels and relationships |
| Warranty policy | `WarrantyPolicy` | `PartCatalogProfile.warranty_months` | Migrated into 100 policies; **new** label |
| Warranty claim, evidence | `WarrantyClaim`, `Evidence` | none | **New** |
| FILM_* constants | `FeaturedScenario` (`scenarios/discovery.json`) | none | Recorded as data and consumed by the site (Phase 2); constants removed |
| CITY_COORDINATES | `Location.latitude/longitude` (`geo_basis = REFERENCE_CITY_CENTRE`) and `reference/geography.json` | `Location` | Written to unprotected city locations; consumed by the site (Phase 2); dict removed from code |
| Data source | provenance `SRC-CANON` | `DataSource` | New node |

Deviations from the brief, and why:
* **Fitment context is a new `FitmentContext` node, not extra properties on `FITS`.** `FITS` is SOURCE_DERIVED and covered by the integrity checksum; adding properties would change it. The two stay 1:1 (`fitment_id` = the `FITS` relationship id).
* **Discovery text is written to `PartCatalogProfile`** for the same reason.
* **`ApprovedSource.source_type` is `source_kind`** (OEM, SUPPLIER, DEALER) because `source_type` is the provenance field.
* **Transport modes** keep the existing network values (`RAIL`, `MULTIMODAL`, `SHORT_SEA`, `INLAND_WATERWAY`) next to the brief's `SEA`, `AIR`, `ROAD`, `SEA_PLUS_ROAD`; nothing is remapped.

### 3. Write policy
* A node is **protected** when `data_status` is SOURCE_DERIVED, DERIVED, REAL, or USER_PROVIDED, and **app-owned** when `source_id = APP-SESSION`. Neither is ever modified: the record is compared and reported as `verified`, `extension_pending` (canonical holds values the graph lacks) or `drift` (a value differs).
* `verify` datasets (orders, order lines, inventory, route legs and the protected master data) are compared even when the node is unprotected: the graph owns them in this phase.
* Other nodes are merged: only differing properties are written, so a second run writes nothing.
* New records are stamped `source_id = SRC-CANON` with `data_status`, `source_type`, `source_record_id`, `ingestion_timestamp`, `canonical_schema_version`, `canonical_dataset`. Existing records keep their own provenance.
* Relationships are unique per (type, from, to) with a deterministic `rel_id`. Nothing is ever deleted. Dry-run writes nothing.

### 4. Files
`backend/data/canonical/`: `master/` (plants, locations, categories, machines, suppliers, dealers, parts, specifications), `relationships/` (fitment, approved_sources, assemblies, legacy_part_mappings), `commerce/` (customers, orders, order_lines, inventory, pricing), `logistics/` (routes, route_legs, shipments, tracking_events), `lifecycle/` (machine_instances, technicians, work_orders, installations, replacements, warranty_policies, warranty_claims, evidence), `scenarios/` (discovery, logistics, warranty), `reference/discovery_vocabulary.json`, `manifest.json` (dataset versions and checksums), `integrity.json` (checksum baseline). Every JSON file carries `dataset`, `dataset_version`, `canonical_schema_version`, `generated_at`.

### 5. Commands
```
python backend/scripts/canonical.py export [--dataset NAME ...]   # graph -> canonical files (read-only on the graph)
python backend/scripts/canonical.py generate                      # deterministic synthetic lifecycle + scenario files
python backend/scripts/canonical.py validate [--dataset ...]      # schema and references among files, offline
python backend/scripts/canonical.py dry-run  [--dataset ...]      # full plan against the graph, no writes
python backend/scripts/canonical.py ingest --yes [--dataset ...]  # idempotent MERGE, checksums, report
python backend/scripts/canonical.py verify   [--dataset ...]      # re-plan: nothing left to create or update
python backend/scripts/canonical.py checksum                      # dataset checksums and graph fingerprint
```
Reports are written to `backend/data/canonical/reports/` (git-ignored).

### 6. Integrity
* The existing SOURCE/DERIVED DATA INTEGRITY CHECKSUM is checked before and after every ingestion and recorded in the report. New domains are SYNTHETIC_DEMO and sit outside it by design.
* `dataset_checksum`: SHA-256 over a dataset's validated records (every field except `ingestion_timestamp`), independent of file order. Stored in `manifest.json`.
* `graph_fingerprint`: SHA-256 over every node and relationship created by the ingestion (`source_id = SRC-CANON`), excluding timestamps. Stored in `integrity.json`; identical after re-ingestion.

### 7. Migration path for the existing generators
`scripts/eu_foundation/*` and the workbook-to-Cypher loaders are **unchanged and still the source of the graph**. The path: generate canonical files from the graph (`export`) → validate → dry-run → ingest (a no-op for exported data: verified 0 drift) → regress → switch consumers (`FILM_*`, `CITY_COORDINATES`, the generators) to canonical data → only then remove the old generation code. Steps 1–4 are done; the switch and the removal are not.

### 8. Known limits (Phase 1)
* Normalised specification names, `valid_from/valid_to` on fitment and discovery text on the protected `Part` itself are canonical-only until a checksum rebaseline is agreed for protected records (12 specification names are `extension_pending`).
* 11 seeded shipments have no determinable route or destination location; they carry `remediation_flags` and a null `route_id` rather than an invented link.
* `FILM_*` and `CITY_COORDINATES` were migrated to canonical data in Phase 2 (see [LOGISTICS_NETWORK.md](#logistics-network)).
* Lifecycle, fitment-context and approved-source records are synthetic and labelled `SYNTHETIC_DEMO`.

<a id="logistics-network"></a>

## Logistics network, routes and shipments

*Originally `LOGISTICS_NETWORK.md`; Logistics network, routes and shipment context (Phase 2).*

Built on the canonical layer ([CANONICAL_DATA_MODEL.md](#canonical-data-model)): the same models, engine, validation, provenance, deterministic ids, idempotency and integrity checks. No UI and no agent yet; the graph can now answer **"where is my shipment?"** and **"what are the realistic transport options and trade-offs?"** from records.

Everything added is synthetic demonstration data (`data_status = source_type = SYNTHETIC_DEMO`). It is not a real carrier schedule, rate or commitment.

### 1. Geography
A Netherlands-centred network: the Netherlands distribution centre (`WH-005`), Rotterdam seaport, Amsterdam air cargo terminal, then Western Europe (UK, Switzerland, Norway), the USA (Houston, Savannah, Chicago, Los Angeles) and Africa (Lagos, Tema, Durban, Mombasa, Casablanca). **Japan is an origin for one demonstration lane only** (a supplier near Nagoya, its seaport and airport): every other route starts at the Netherlands distribution centre.

Location model (`Location`): `location_id`, `name`, `location_type` (WAREHOUSE, DISTRIBUTION_CENTER, DEALER, PORT, AIRPORT, TERMINAL, CUSTOMS, SUPPLIER, PLANT), `country`, `region` (EUROPE, USA, AFRICA, ASIA), `latitude`, `longitude`, `timezone`, `data_status`, `source_type`. Existing depots, plants, dealers and the 48 terminals already in the graph were enriched in place; 29 locations and 12 dealers were added. A dealer is its own place (`location_id` = `dealer_id`). Nothing was duplicated.

Authoring source: `backend/data/canonical/reference/network_definition.json` (the one place the network is written down). `python backend/scripts/canonical.py network` checks it is coherent (legs contiguous, ends match the lane, days and cost are the sum of the legs, event sequences possible) and expands it into the `network_*` datasets.

### 2. Routes and legs
A `Route` carries `origin_location_id`, `destination_location_id`, `transport_mode`, `planned_transit_days`, `estimated_cost`, `currency`, `service_level`, `status`. Its `RouteLeg`s run in order from the origin to the destination, each with mode, days and cost; a route's days and cost are the **sums of its legs**. 27 routes and 90 legs on 13 lanes. **No mode has a built-in duration or price anywhere in code**: a test fails if one appears.

Same-lane sea vs air (the mandatory pair): supplier `SUP-041` → dealer `DLR-004`:

| Route | Mode | Service | Days | Cost (EUR, synthetic) |
|---|---|---|---|---|
| `RTE-NET-JPNL-SEA-ECO` | SEA | ECONOMY | 91 | 2,835 |
| `RTE-NET-JPNL-SEA-STD` | SEA | STANDARD | 45 | 3,785 |
| `RTE-NET-JPNL-AIR-EXP` | AIR | EXPRESS | 6 | 12,675 |

The 91 days exist on that one route record only (an economy consolidated service with transhipment and port waits). Every other NL-origin lane has a sea (or short-sea, or road) route and an air route with different days and cost.

### 3. Shipments and tracking
Tracking is a list of discrete events with an allowed order (`app/logistics/rules.py`): ORDER_CONFIRMED → BOOKED → DEPARTED_ORIGIN → (IN_TRANSIT) → ARRIVED_PORT → CUSTOMS → DEPARTED_PORT → ARRIVED_DC → OUT_FOR_DELIVERY → DELIVERED, with the seeded shipments' shorter PICKED lifecycle also valid. The engine rejects a shipment whose events are impossible together. **There is no live position**: an event at sea or in flight has no place, only a status, and the context says so.

Scenario shipments (fully linked to order, part, route and places):
* `SHP-NET-0001` A: Japan → sea → Rotterdam → Netherlands DC → dealer. IN_TRANSIT, on leg 2 of 4, planned ETA 2026-11-19.
* `SHP-NET-0002` B: the air alternative for the same order, part and lane. Out for delivery, ETA 2026-10-07.
* `SHP-NET-0003` C: Netherlands DC → Houston port → Houston regional logistics hub → US dealer. Left the port towards the hub, ETA 2026-10-09.
* `SHP-NET-0004` D: a delivered air shipment to a UK dealer (the full lifecycle including DELIVERED).

The 11 seeded shipments have no deterministic route (their depot has no recorded route to the customer's ship-to). They are **not linked**: `route_resolution_status = ROUTE_NOT_DETERMINABLE`, `route_id` null, with remediation flags.

### 4. Route progress
A leg is completed when the shipment has an arrival event (ARRIVED_PORT, ARRIVED_DC, DELIVERED) at the leg's destination. From that: completed legs, remaining legs, the current leg, and whether the shipment is on a leg or at a place. Legs complete in order. No GPS.

### 5. ShipmentContext
`app/logistics/context.py` assembles, from data only (no language model): shipment, order, part, origin, destination, current location, current status, events, route, legs, route progress, planned ETA (with days to ETA), alternative routes for the same origin and destination, a transport comparison, provenance and plain notes. The comparison is arithmetic on each route's own days and cost (difference to the current route, fastest, lowest cost); it never depends on the mode. A shipment without a route says so and has no progress or alternatives.

Two readers feed it with identical vocabulary: `FileReader` (the canonical files) and `GraphReader` (Neo4j, read-only). A test builds the context for six shipments from both and requires the same answer.

### 6. Migration of code values to data
| Was | Now | Status |
|---|---|---|
| `FILM_MACHINE`, `FILM_PART`, `FILM_CUSTOMER` in `services/site.py` | the `FeaturedScenario` FILM record in the graph (`scenarios/discovery.json`), read by the launch-film query | **migrated, constants removed** |
| `CITY_COORDINATES` in `core/geography.py` | graph locations (map positions) and `reference/geography.json` (the exporter's reference) | **migrated, constant removed** |
| hard-coded route durations, transport costs | none existed in code; all values are route records | n/a |
| shipment states (`order_flow.py` SHIPMENT_EFFECT, ACTIONS) | workflow rules for the direct-order flow | kept: rules, not business data |
| hard-coded dealer geography | none; dealers carry country, region and coordinates in the graph | n/a |

Effect of the coordinate migration: plant and depot map pins moved by under 0.01° (the graph's synthetic depot coordinates have two decimals, the old table four), and every city that had no position now has one.

### 7. Commands
```
python backend/scripts/canonical.py network     # validate and expand the network definition
python backend/scripts/canonical.py export      # existing data -> canonical files (enriched)
python backend/scripts/canonical.py dry-run | ingest --yes | verify | checksum
```

### 8. Limits
* All numbers are synthetic and illustrative. There is no carrier integration and no live position.
* Scenario shipments belong to three synthetic orders (channel `DEMO_NETWORK`); processors see them in the orders list, end users do not.
* A shipment uses one route; multi-route or re-routed shipments are not modelled.
* The 11 seeded shipments stay unresolved until a deterministic link exists.
* `CUSTOMS` as a location type exists in the model; customs are events at ports and terminals, not separate places.

<a id="lifecycle-and-warranty"></a>

## Machine lifecycle, warranty and traceability

*Originally `LIFECYCLE_WARRANTY.md`; Machine lifecycle, warranty and traceability (Phase 3, schema 1.0).*

Answers, from data and rules only: **"Is this covered under warranty, and was this part properly fitted?"** No language model, no UI, no claim submission, no external API. A later layer may explain a verified result; it never decides one. Phases 1 and 2 are described in [CANONICAL_DATA_MODEL.md](#canonical-data-model) and [LOGISTICS_NETWORK.md](#logistics-network).

### 1. Graph model
```
(MachineInstance)-[:HAS_INSTALLATION]->(InstallationEvent)-[:INSTALLED_PART]->(Part)
                                       (InstallationEvent)-[:PERFORMED_BY]->(Technician)-[:EMPLOYED_BY]->(Dealer)
                                       (InstallationEvent)-[:PERFORMED_AT]->(Dealer)
                                       (InstallationEvent)-[:RECORDED_IN]->(WorkOrder)<-[:HAS_WORK_ORDER]-(MachineInstance)
(MachineInstance)-[:HAS_REPLACEMENT]->(ReplacementEvent)-[:REMOVED_INSTALLATION|NEW_INSTALLATION]->(InstallationEvent); (ReplacementEvent)-[:RECORDED_IN]->(WorkOrder)
(MachineInstance)-[:HAS_CLAIM]->(WarrantyClaim)-[:CLAIM_ON_INSTALLATION]->(InstallationEvent); (WarrantyClaim)-[:CLAIM_FOR_PART]->(Part); (WarrantyClaim)-[:FILED_BY_DEALER]->(Dealer)
(WarrantyPolicy)-[:WARRANTY_FOR_PART]->(Part)            (Evidence)-[:SUPPORTS]->(any record above, a Dealer, a Technician or a Part)
```
* **`FITS` / `FitmentContext` is approval; `HAS_INSTALLATION` is fact.** A part can be installed on a machine it was never approved for (scenario G008), and an approved part may never have been fitted. The evaluator needs both.
* `MachineInstance` is the anchor: its history is every installation, replacement, work order and claim reachable from it.
* The Phase 1 names `OF_PART`, `INSTALLED_BY_DEALER`, `INSTALLED_BY_TECHNICIAN`, `UNDER_WORK_ORDER` were replaced by `INSTALLED_PART`, `PERFORMED_AT`, `PERFORMED_BY`, `RECORDED_IN` (`python backend/scripts/canonical.py migrate-lifecycle --yes`). A relationship is removed only if it carries this ingestion's own source id and its replacement already exists between the same two nodes.

### 2. Records and validation
* `InstallationEvent.validation_status` is `VALID` or `INCOMPLETE`, with `validation_issues` naming what is missing (`technician_missing`, `work_order_missing`, `dealer_missing`, `part_missing`, `machine_instance_missing`, `removal_before_installation`, `installed_before_machine_existed`, `technician_works_for_another_dealer`, `work_order_for_another_machine`, …). A reference that is not available is left empty, never filled in. It is computed by `rules.validate_installation` when the files are generated and re-checked by the quality checks.
* **Authorisation** is the dealer's existing `authorized_status`; the value `AUTHORISED` means authorised. There is no second field.
* **Technicians**: certification and specialisation (Hydraulics, Powertrain, Electrical, Transmission), employed by one dealer.
* **Work orders**: service type `INSTALLATION | REPLACEMENT | INSPECTION | MAINTENANCE | REPAIR`. One work order may record several component events (WO-G001 records two installations; WO-G005-2 an installation and the replacement it completes).
* **Replacements** keep history: the removed installation stays as `REMOVED` with its removal date. Chronology: removed installation date < replacement date <= new installation date; removal date <= replacement date. **Current component** = installation with no `removal_date` and status `CURRENT` (derived, never stored as a "current part" field).
* **Evidence** types: `INSTALLATION_RECORD, SERVICE_REPORT, INSPECTION_RECORD, WORK_ORDER, DEALER_RECORD, TECHNICIAN_RECORD, PART_RECORD` (plus the Phase 2 shipment/order types). Synthetic evidence says so in `reference`; no fabricated URLs or document ids. Dealer, technician and part records exist once per entity.
* Every lifecycle record carries `data_status = SYNTHETIC_DEMO`, `source_type`, `source_record_id`, `ingestion_timestamp`, `canonical_dataset`, `canonical_schema_version`; the existing catalogue records keep their own provenance.

### 3. Warranty policy and the deterministic evaluator
`WarrantyPolicy` is data: `coverage_period_days`, `start_rule` (`INSTALLATION_DATE | DELIVERY_DATE | PURCHASE_DATE`), `region` (empty = every region) and `coverage_conditions`, a list of condition codes. How each code is checked is one catalogue in `app/lifecycle/rules.py` (`CONDITIONS`); a policy naming an unknown code is rejected by the model.

| Condition | Holds when | If it fails |
|---|---|---|
| `APPROVED_MACHINE_FITMENT` | the part has an `APPROVED` fitment for the machine model | NOT_ELIGIBLE |
| `APPROVED_PART` | catalogue status `VERIFIED` and an `APPROVED` source | NOT_ELIGIBLE |
| `AUTHORISED_DEALER_INSTALL` | installing dealer `authorized_status = AUTHORISED` | NOT_ELIGIBLE |
| `COVERAGE_PERIOD_ACTIVE` | failure date (else evaluation date) in [start, start + days] | NOT_ELIGIBLE |
| `INSTALLATION_EVIDENCED` | technician, work order, installation record and work-order record exist | INSUFFICIENT_DATA |
| `NO_PRIOR_CLAIM` | no earlier claim for this part on this machine | REQUIRES_REVIEW |
| `NO_PRIOR_REPLACEMENT` | this installation is not the result of repeated replacement | REQUIRES_REVIEW |

Always evaluated first: `PART_INSTALLED` (this installation is of the claimed part on the claimed machine) and `POLICY_FOUND` (exactly one most-specific active policy; none → INSUFFICIENT_DATA, two equal → REQUIRES_REVIEW).

**Outcome precedence**: a definite hard failure (`NOT_ELIGIBLE`) > any unknown fact (`INSUFFICIENT_DATA`) > a review trigger (`REQUIRES_REVIEW`) > `ELIGIBLE`. A start rule that needs a delivery or purchase date that is not on record gives INSUFFICIENT_DATA; nothing is guessed. The same facts always give the same outcome.

**Claims.** Statuses `SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED, CLOSED`. The status and decision of a *decided* claim are derived from the evaluator when the files are generated (`APPROVED` ⇔ ELIGIBLE, `REJECTED` ⇔ NOT_ELIGIBLE, else `UNDER_REVIEW`); the quality checks fail if a stored decision disagrees with the rules. Golden claims stay `SUBMITTED`: the evaluator returns the verdict, no approval is invented.

### 4. Context, traceability, part lifecycle (`app/lifecycle/context.py`)
`WarrantyContextBuilder(reader).for_claim(id)` / `.for_part(machine_instance_id, part_id)` returns a `WarrantyContext`: machine, current_part, installation, dealer, technician, work_order, fitment, approved_source, warranty_policy, coverage_start, coverage_end, replacement_history, prior_claims, evidence, decision_factors (code, status, detail, records, evidence), provenance, plus `outcome`, `reasons`, `missing`. `.traceability(machine_instance_id, part_id?)` gives installed now / installed before / who / where / when replaced / linked claims. `.part_lifecycle(installation_id)` gives Installed → Serviced → Inspected → Removed → Replaced → Current/Historical, each stage dated from a record; a stage with no record is absent. Readers: `FileReader` (canonical files) and `GraphReader` (Neo4j, read-only) return identical dictionaries; a live test asserts they agree.

### 5. Golden scenarios (`reference/lifecycle_scenarios.json`, KFT-600/800 and BTS-750)
| ID | Case | Expected |
|---|---|---|
| G001 | Piston pump (PRT-007) fitted by an authorised dealer, one work order for two components, failure inside the period | ELIGIBLE |
| G002 | Same part fitted by a SERVICE_PARTNER dealer | NOT_ELIGIBLE (authorisation) |
| G003 | Failure after the 365-day period (installed 2025-02-10, failed 2026-05-01) | NOT_ELIGIBLE (expired) |
| G004 | Second claim for the same part on the same machine | REQUIRES_REVIEW |
| G005 | Pump replaced twice (A→B→C), third unit fails | REQUIRES_REVIEW |
| G006 | Installation with no technician, work order or evidence | INSUFFICIENT_DATA |
| G007 | Wheel hub bearing PRT-022 (UNVERIFIED) | NOT_ELIGIBLE (not an approved part) |
| G008 | Verified gear pump with no fitment for the KFT-600 | NOT_ELIGIBLE (no approved fitment) |

### 6. Commands
```
python backend/scripts/canonical.py generate            # lifecycle + scenario files, validation and claim decisions derived by the rules
python backend/scripts/canonical.py validate            # offline schema/reference validation
python backend/scripts/canonical.py dry-run             # plan against the graph
python backend/scripts/canonical.py ingest --yes        # idempotent MERGE
python backend/scripts/canonical.py migrate-lifecycle [--yes]   # superseded relationship names (dry run without --yes)
python backend/scripts/canonical.py lifecycle-report    # counts, data-quality checks, golden scenarios against the graph (read-only)
```

### 7. Known limits
* Only `INSTALLATION_DATE` can start a coverage period today: no delivery or purchase dates are recorded on machine instances, so those rules return INSUFFICIENT_DATA rather than a guess.
* All dealers in the data have `warranty_capable = false` for NL; the evaluator does not use it (authorisation is `authorized_status`).
* Lifecycle data is synthetic and labelled `SYNTHETIC_DEMO`; the existing 3 claims were re-derived by the evaluator, so their earlier hand-written outcomes changed (CLM-0002 and CLM-0003 are REJECTED because their installing dealers are INDEPENDENT).

<a id="commerce-context-engine"></a>

## Commerce Context Engine

*Originally `COMMERCE_CONTEXT_ENGINE.md`; Commerce Context Engine (Phase 4).*

One engine turns graph facts into a structured, evidenced, deterministic context for three journeys: **discovery**, **order and logistics visibility**, **warranty and traceability**.
It is not the conversational agent. It decides nothing with a language model and invents nothing: the agent explains the structure it returns.

```
request → intent / flow → CommerceContextEngine → (authorization on the records) → reader → rules → structured context + evidence path → agent → user
```

### Architecture

| Layer | Where | Reuses |
|---|---|---|
| Engine | `backend/app/commerce/engine.py` `CommerceContextEngine` | — |
| Discovery | `commerce/discovery.py`, `commerce/discovery_reader.py` | canonical datasets; graph through the existing `Exporter` (no new Cypher) |
| Logistics | `commerce/logistics.py` | Phase 2 `ShipmentContextBuilder` and `LogisticsReader` (three additive methods: `order_lines`, `shipments_of_order`, `orders_of_customer`) |
| Warranty | `commerce/warranty.py` | Phase 3 `WarrantyContextBuilder` → `rules.evaluate` (the single source of truth) |
| Common model | `commerce/contract.py` | — |
| Access | `commerce/access.py` | `Role`, `User`, signed session |
| Agent adapter | `commerce/intent.py`, `commerce/service.py` `AgenticCommerceService` | the engine only |
| API | `api/routes/commerce.py` | existing auth, `require()`, error format |

Every reader exists twice with identical output: files (tests, offline) and graph (Neo4j, read-only). `CommerceContextEngine.from_files(...)` / `.from_graph(client)`.

### Common contract

Every context has `context_id, context_type, generated_at, data_status, source_records, evidence, confidence, missing, warnings`, a `decision` (`CommerceDecision`), an `evidence_path` and a `visibility` note.

* `decision.status`: `SUCCESS | NOT_FOUND | NOT_ELIGIBLE | REQUIRES_REVIEW | REQUIRES_CLARIFICATION | INSUFFICIENT_DATA`; `decision.decision` is the domain word (`RECOMMEND`, `NO_VALID_RECOMMENDATION`, `TRACKED`, `DELIVERED`, `ROUTE_NOT_DETERMINABLE`, `ELIGIBLE`, `NOT_ELIGIBLE` ...).
* `confidence = {level, data_status, fact_verified, real_world_verified, basis}` keeps four things apart. `level` is completeness (COMPLETE / PARTIAL / INSUFFICIENT). `data_status` is what kind of data the records are (`SYNTHETIC_DEMO`, `SOURCE_DERIVED`, `MIXED` ...). `fact_verified` is true when every fact in the decision was checked against graph records that agree with each other, **including on synthetic demo data**: it says the graph is internally consistent. `real_world_verified` is true only when nothing is missing and every record is `REAL` or `SOURCE_DERIVED`. Unresolved requests, missing route or missing warranty facts are `fact_verified = false`; a definite negative (not eligible, right part out of stock) is `true`.
* `context_id` is a hash of the request, the reference day, the outcome and the records used. The same request on the same data gives the same body; only `generated_at` follows the wall clock unless the engine is pinned with `as_of`.
* Missing data is listed in `missing`; unknown is never turned into zero, "available" or "likely".

### Discovery

`extract entities → retrieve by vocabulary → identify machine → canonical product check → fitment → approved source → availability → price → rank → recommend`.

**Rule: an alias never overrides canonical product semantics.** Authority, highest first: canonical product / category / type (`Part.name`, `technical_terms`, `part_number`, subcategory and category names) → machine fitment (the FITS record) → approved source → availability → semantic relevance → ranking. Aliases, common names, symptoms and the (generated) description only *identify* a candidate. Each candidate gets a `product_match` status:

| status | meaning | can be recommended |
|---|---|---|
| `CANONICAL_MATCH` | every request term is in the part's canonical name / category / type | yes |
| `CANONICAL_TYPE_MISMATCH` | covered only by alias text, and a term that names a product class (hydraulic, pump ...) conflicts with the part's canonical class | never, not even as an alternative |
| `ALIAS_ONLY_MATCH` | covered by alias text only, no class conflict | never; shown in `unconfirmed_matches` for the user to confirm |
| `PARTIAL_MATCH` | some terms not covered | never |

* The machine is resolved only from an id, an owned machine instance or an explicit model identifier. A family (`KFT`), a type word (`loader`) or a near miss (`X200`) is `REQUIRES_CLARIFICATION`; the near miss may be *suggested*, never used.
* Each candidate is stated as separate facts, not one score: `product_match`, `fitment`, `approved_source`, `availability` (`AVAILABLE | UNAVAILABLE | UNKNOWN`), `recommendation`, plus `flags {MATCHED, PRODUCT_MATCH, COMPATIBLE, APPROVED, AVAILABLE, RECOMMENDED, REJECTED}`.
* Rejection reasons, in order of authority: `CANONICAL_TYPE_MISMATCH | ALIAS_ONLY_MATCH | LOW_SEMANTIC_MATCH`, `NOT_APPROVED | DEPRECATED`, `NO_FITMENT`, `NO_APPROVED_SOURCE | OUT_OF_REGION`, `NOT_AVAILABLE | AVAILABILITY_UNKNOWN`. Each names its record or says `ABSENCE_OF_RECORD`.
* Decisions: `RECOMMEND`; `NO_AVAILABLE_RECOMMENDATION` (the right part exists, fits and is approved, but is unavailable or its stock is unknown: `compatible_part` names it, `alternatives` lists only other parts that pass the same checks, and no part of a different kind is substituted); `NO_VALID_RECOMMENDATION`; `REQUIRES_CLARIFICATION`.
* Ranking, among parts that passed every gate: weighted mean of `fitment .30, semantic_match .25, approval .20, availability .20, regional .05` (components that do not apply are left out), ties by part id. Weights are returned in `scoring`.
* Evidence path: `Part → Fitment → ApprovedSource → Inventory → Price` (for the recommended part, or for the compatible part when it cannot be offered).

### Logistics

`LogisticsContext` is the Phase 2 `ShipmentContext` plus the common contract. Progress, ETA, alternatives and the comparison are read from the route records; nothing in the application knows how long or how dear any mode is. A shipment with `route_resolution_status = ROUTE_NOT_DETERMINABLE` returns `INSUFFICIENT_DATA`, `requires_review = true`, no route/legs/ETA/alternatives, and still returns what is known (status, events, order, part). Evidence path: `Order → Shipment → Route → TrackingEvent`. With no reference, an end customer's request resolves among their own open shipments, or asks which one.

### Warranty

`WarrantyContext` is the Phase 3 context. `ELIGIBLE → SUCCESS`; the other outcomes keep their name as the status. Each `decision_factor` has `result`, `detail`, and `sources: [{entity, id}]`; a factor resting on the absence of a record (no earlier claim) names the record that was searched and `basis: ABSENCE_OF_RECORD`. Evidence path: `MachineInstance → Installation → WorkOrder → Dealer → WarrantyPolicy → Claim → Evidence`.

### Authorization

Account role → commerce role: `END_USER → END_CUSTOMER`; `ORDER_PROCESSOR → OEM`, or `DEALER` when a `dealer_id` is given. An account can narrow itself, never widen. Ownership is checked on the records before a context is built: order `customer_id`/`dealer_id`, machine `owner_id`, installation and claim dealer. For non-OEM callers, a record that does not exist and a record that is not theirs are refused identically (403). Visibility is a small table (`access.HIDDEN`) applied to a copy of the result and reported in `visibility.hidden_fields`: end customers do not see per-depot stock, internal shipment flags, per-leg freight cost or technician names.

Limit: the demo has no dealer account. A processor may act as any dealer by naming a `dealer_id` (processors already read every order); a real dealer login would link an account to a dealer.

### API (all POST, authenticated, `commerce.context` permission, JSON)

| Endpoint | Body |
|---|---|
| `/api/v1/commerce/discovery/context` | `request`, optional `machine_id`, `machine_instance_id`, `destination_country`, `user_role`, `dealer_id` |
| `/api/v1/commerce/logistics/context` | optional `shipment_id`, `order_id`, `user_role`, `dealer_id` |
| `/api/v1/commerce/warranty/context` | `claim_id`, or `machine_instance_id` + `part_id`; optional `user_role`, `dealer_id` |
| `/api/v1/commerce/request` | agent adapter: `request`, optional `intent` and any of the references above |

Business outcomes are in `decision.status` with HTTP 200. 401 not signed in, 403 refused, 422 malformed. Unknown fields are rejected.

### Known data facts

* "hydraulic pump for my KFT-600": `PRT-007` (piston pump, Hydraulics) is the right part: it fits, has an approved source, and has **no stock in any depot**. The result is `NO_AVAILABLE_RECOMMENDATION` with `compatible_part = PRT-007`. `PRT-097` (central lubrication pump) and `PRT-078` (water pump) carry the alias "hydraulic pump" but belong to other categories: `CANONICAL_TYPE_MISMATCH`, kept as diagnostics only.
* The Phase 2 "pump" shipment `SHP-NET-0001` carries `NVM-1010-HY`, a hydraulic hose.

### Live validation

`python backend/scripts/commerce_live_validate.py [--out report.json] [--offline] [--full-detail]` (read-only; helpers in `scripts/commerce_validation_lib.py`).

**Online run:** connectivity (host, port, DNS, TCP, authentication, database) → `snapshot_before` → **pass 1** → `snapshot_after_pass1` → **pass 2** → `snapshot_after_pass2` → determinism. A pass contains:
* **entity counts** for 29 entities (Part … FeaturedScenario): canonical vs graph, difference, status, and the missing ids. Id sets are compared, not only totals. Records written by the running app (`source_id = APP-SESSION`) are counted apart as `graph_app_written`.
* **field-level comparison** of every registry dataset (all 46, including Phase 1–3 and the network datasets) with the same canonical-field-to-graph-property mapping the ingestion uses, plus the relationship edges each record needs and provenance (`data_status`, `source_record_id`). Every difference is `dataset / record_id / field / canonical_value / graph_value / difference_type` with type `MISSING_IN_GRAPH | MISSING_IN_CANONICAL | VALUE_MISMATCH | TYPE_MISMATCH | NORMALIZATION_ONLY | IGNORED_BOOKKEEPING`. An absent graph property where the canonical record states a value is `MISSING_IN_GRAPH`.
* **normalisation**: only the named rules in `RULES` (list order, numeric type/tolerance, empty-equivalent, date/timestamp format, country-code case, specification-name casefold, FITS `CONFIRMED→APPROVED`, SUPPLIED_BY `ACTIVE*→APPROVED`, import bookkeeping). Each applied rule is counted in `normalization.normalization_rules_applied`; the protected catalogue allows only list order, numeric type/tolerance and specification-name casefold. There is no catch-all bucket.
* **protected comparison**: machines, parts, categories, specifications, plants, legacy references, assemblies, plus the supplied FITS and SUPPLIED_BY relationships, part category links and search aliases.
* engine(files) vs engine(graph) on every scenario; discovery D001…, logistics per shipment (expected/actual status and route, ETA, alternatives), warranty G001–G008 (expected/actual decision, matching/mismatching factors); authorization (test, role, resource, expected, actual); the four API routes; evidence-chain and provenance checks.

**Read-only:** the only graph handle is `ReadOnlyGraph` (no write method; a query containing a write keyword raises before it is sent; every query is counted). Static and behavioural tests enforce it.

**Classification** (`final_classification`, exit code): `PHASE 4H COMPLETE` (0) only if Neo4j was reached and every criterion in `acceptance` is PASS twice; `PHASE 4H FAILED — LIVE VALIDATION FOUND PRODUCT/DATA ISSUES` (1) if Neo4j was reached and anything failed; `PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE` (2) if DNS, TCP, authentication or the database failed, or in OFFLINE mode. BLOCKED, SKIPPED and FAIL are never reported as PASS.

**Offline:** `--offline` runs the same machinery against an in-memory twin of the canonical files. It proves the validator and the engine logic; it is not Neo4j, reports `mode = OFFLINE`, `live_graph_verified = false`, and is always BLOCKED.

`tests/test_commerce_validator.py` tests the validator (counts, field comparison, normalisation, protected comparison, snapshots, determinism, JSON, unreachable/authentication/blocked, mismatch, mutation guard). `tests/test_commerce_live.py` runs the live checks and **skips** (never passes) when Neo4j is unreachable.

<a id="commerce-agent"></a>

## Agentic commerce: contracts, agent and workspace

*Originally `COMMERCE_AGENT.md`; Agentic E-Commerce MVP (Phase 5): contracts, agent and workspace.*

The first vertical slice of the product on top of the validated Phase 4 commerce APIs and the live Neo4j graph.

```
User → Commerce Agent → intent → Discovery / Logistics / Warranty → Commerce Context Engine → Neo4j
     → evidence + decision → agent answer → UI
```

### 1. The Phase 4 contract map (frozen: Phase 5 changes none of it)

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/v1/commerce/discovery/context` | `request`, optional `machine_id`, `machine_instance_id`, `destination_country`, `user_role`, `dealer_id` | `DiscoveryContext` |
| `POST /api/v1/commerce/logistics/context` | `shipment_id` or `order_id` (+ scope) | `LogisticsContext` |
| `POST /api/v1/commerce/warranty/context` | `claim_id`, or `machine_instance_id` with `part_id` (+ scope) | `WarrantyContext` |
| `POST /api/v1/commerce/request` | `request`, optional `intent` and references (+ scope) | `{intent, intent_source, decision, context}` |

* **Common context fields** (`app/commerce/contract.py`): `context_id`, `context_type`, `generated_at`, `data_status`, `source_records[]`, `evidence[]`, `confidence{level, data_status, fact_verified, real_world_verified, basis}`, `missing[]`, `warnings[]`, `decision{status, decision, summary, facts, reasons, evidence, source_records, missing, warnings, recommended_next_action}`, `evidence_path[]`, `visibility{role, hidden_fields[]}`.
* **Statuses** (`decision.status`): `SUCCESS, NOT_FOUND, NOT_ELIGIBLE, REQUIRES_REVIEW, REQUIRES_CLARIFICATION, INSUFFICIENT_DATA`. Business outcomes are HTTP 200; HTTP errors are 401 (not signed in), 403 (not allowed: the same body for a record that does not exist and one that is not yours), 422 (malformed).
* **Discovery decisions**: `RECOMMEND, NO_AVAILABLE_RECOMMENDATION, NO_VALID_RECOMMENDATION, REQUIRES_CLARIFICATION`; part-level `product_match_status` includes `CANONICAL_MATCH`, `CANONICAL_TYPE_MISMATCH`, `ALIAS_ONLY_MATCH`, `PARTIAL_MATCH`; rejection codes `NO_FITMENT, NO_APPROVED_SOURCE, NOT_AVAILABLE, AVAILABILITY_UNKNOWN, CANONICAL_TYPE_MISMATCH, …`. Fields: `machine`, `candidate_parts`, `fitment_results`, `approved_sources`, `availability`, `pricing`, `recommended_part`, `compatible_part`, `alternatives`, `ranking`, `rejection_reasons`, `clarification`.
* **Logistics**: `shipment`, `order`, `order_lines`, `shipment_lines[]` (every order line on the shipment, each with its part), `parts[]`, `part` (set only for a single-line shipment), `shipment_kind` (`SINGLE_LINE | MULTI_LINE | NO_LINE_RECORDED`), `order_shipments[]`, `order_split`, route, legs, `planned_eta`, `transport_comparison`, `tracking_events`, `route_resolution_status`. **Multi-line shipment** (several order lines travel together, canonical model `ShipmentLine`) and **order split** (one order over several shipments) are different facts; an order with several shipments still returns `REQUIRES_CLARIFICATION`.
* **Warranty**: `decision.facts.outcome` is `ELIGIBLE | NOT_ELIGIBLE | REQUIRES_REVIEW | INSUFFICIENT_DATA`, produced by `app/lifecycle/rules.py` only; `decision_factors[]` (every check with PASS / FAIL / UNKNOWN and its sources), `installation`, `dealer`, `technician`, `work_order`, `fitment`, `approved_source`, `warranty_policy`, `coverage_start/end`, `replacement_history`, `prior_claims`, `claim`, `traceability`.
* **Authorization** (`app/commerce/access.py`): END_USER → `END_CUSTOMER` (own records only), ORDER_PROCESSOR → `OEM` (everything) or `DEALER` with a `dealer_id`. An account can narrow itself, never widen. Removed for a customer: `availability[*].warehouses`, `shipment.remediation_flags`, `route_legs[*].estimated_cost`, `technician.name`, `traceability.*.installed_by.name`.
* **Evidence**: `evidence_path[]` is an ordered chain of `{step, entity, id, relation_to_next, data_status}`; provenance is `source_records[]` with `data_status` and `source_record_id`. Synthetic demo data is labelled `SYNTHETIC_DEMO` and the confidence block says so (`real_world_verified` is false unless every record is supplied data).

### 2. What Phase 5 adds

| Where | What |
|---|---|
| `POST /api/v1/commerce/agent` | The Commerce Agent. Body: `message` (≤ 500), `state` (what the previous answer returned), optional scope. Same authentication, permission (`commerce.context`) and principal derivation as the other commerce routes; a refusal in any journey is a 403 for the whole request. |
| `app/commerce_agent/agent.py` | Understanding (deterministic cues; the model only routes a message the cues cannot), reference resolution, the engine calls. No domain rule. |
| `app/commerce_agent/answer.py` | The answer, composed from each context's own `decision.summary`, facts and evidence. Optional model rewording of the lead only. |
| `app/llm` | One new operation, `parse_commerce_request` (routing only: which of the three journeys), with its schema and rules. Gemini's schema converter keeps array `items`. |
| `frontend/src/api/commerce.ts`, `components/commerce/*`, `pages/CommercePage.tsx` | The workspace at `/commerce` (nav item **Commerce Assistant**). |
| `scripts/commerce_agent_flows.py` | The four user flows and the security flows through the real API against the live graph, with a before/after graph snapshot. |

Phase 4 behaviour changed in **no** respect: no existing field, status, rule or visibility entry was altered (the Phase 4 and 4H suites pass unchanged). The only edits to existing files are additive (the route, the dependency, the LLM protocol, the Gemini `items` fix, a nav entry).

#### The agent response

```
intent        DISCOVERY | LOGISTICS | WARRANTY | MULTI_DOMAIN | CLARIFICATION | UNKNOWN
status        ANSWERED | PARTIAL | REQUIRES_CLARIFICATION | OUT_OF_SCOPE
answer        {text, lead, sections[{domain, title, status, decision, headline, lines[], notes[]}], synthetic_notice, grounding{mode TEMPLATE|LLM, validated, note}}
steps[]       what ran, in order: DISCOVERY → WARRANTY → LOGISTICS, with the resolution notes
contexts      the full, role-scoped Phase 4 contexts, by journey
evidence, evidence_paths, source_records, confidence, visibility, data_status, warnings, missing   (aggregated, tagged with the journey)
clarification {domain, question, options[]}
state         identifiers and the last search text (+ the question awaiting an answer); never a decision
understanding {intent, domains, source RULES|STATE|LLM|NONE, focus, references, reasons}
```

#### Rules the agent follows
* **Intent.** Cue scores per journey; every journey scoring ≥ 2 runs (`MULTI_DOMAIN` when several). A follow-up with no cue of its own continues the previous journey. The model is consulted only when the cues find nothing, and only picks journeys: it cannot override a decisive match. Out of scope → `UNKNOWN` (declined, with what the agent can do). Some signal but no journey → `CLARIFICATION`.
* **References.** Identifiers (`SHP-…`, `ORD-…`, `CLM-…`, `MI-…`, `PRT-…`, a part number) are read from the message by pattern, never by the model. A part number is turned into a part id through the catalogue.
* **Search text.** In a multi-journey message only the search clause goes to discovery (urgency words removed); the other journeys use the whole message.
* **Warranty resolution.** Claim given → that claim. Machine and part given → the single claim recorded for that part is "the failed one" and is judged; no claim → the installation is judged on its own; several claims → a question. In a multi-journey message the machine comes from discovery's machine and the customer's own instances of it (one → used; several → a question), and the part is the installed part of the kind searched for (canonical matches only).
* **Logistics for an unordered part.** The commerce logistics context follows shipments and orders. A replacement nobody has ordered has no shipment, so the answer says that (`NO_SHIPMENT_FOR_UNORDERED_PART`); no delivery time is invented. (Route-based delivery estimates for a part are produced by Agentic Shopping, not by the commerce contexts.)
* **Answers.** Each section is `decision.summary` plus lines templated over returned values. A question the agent asks is not reworded. The language model may reword the lead (≤ 2 sentences) only if `is_grounded` accepts it (every number and identifier is in the evidence) and the sense check passes (each section's outcome survives and a recorded absence is not turned into a presence); otherwise the deterministic lead stays and `grounding.note` says why.

### 3. The workspace: one input, one answer

`/commerce`, signed-in users only (a signed-out visitor sees a sign-in prompt and no data). There are no domain tabs and no separate forms: the user asks in natural language and the assistant works out the journey.

* **One input** ("What can I help you with?", Enter or Ask) and **one answer area** directly beneath it. The answer shows a plain-language lead, then only the detail that is relevant (a shipment question shows no empty warranty or discovery panel): the part card, the order lines of a shipment, the warranty checks, the machines a part is approved for, the order and its lines when it has no shipment yet.
* **Clarification is conversational.** The question is asked once, inside the answer, with options only when the records support them (the customer's own machines, claims, shipments). Choosing one, or typing a short reply, continues the original request: the server keeps the waiting question (`state.pending_message`) and reads a short reply as its answer. A new request drops it.
* **Evidence stays in the answer**: a collapsed "Evidence and sources" box holds the evidence path, confidence, hidden-field note, evidence items and source records. The demonstration-data disclosure and how the answer was written (records or model wording) are shown under the answer.
* **Follow-ups keep context.** Suggested follow-up questions fit the answer (and are omitted when they would make no sense, e.g. shipment questions for an order with no shipment). Earlier turns collapse into "Earlier in this conversation". *Start over* clears the remembered references.
* **States.** Loading ("Checking the records…", previous answer dimmed), no-result (the backend's own statement, e.g. no shipment recorded yet), ambiguous (the clarification), out of scope (declined with starting points), error (403 "You do not have access to that record", network error with *Try again*).
* **Responsive.** One column; on a phone the Ask button goes full width, tables scroll, chips stack.
* Order processors get a small "View as" control (OEM or a dealer id); a customer's role is never sent.

The page formats the backend's contexts and holds no business data (the existing `noBusinessData` scan covers it: the starting questions name no machine, shipment or claim). Parts Intelligence and Agentic Shopping are untouched.

#### Questions about one part and about orders (also answered in the same place)
* *Which machine uses this part?* (`PART_FITMENT`) and *Where did this part come from?* (`PART_ORIGIN`): `app/commerce/part_lookup.py` reads the fitment and approved-source records (a machine is listed only when a fitment record approves it; a source only when an approved-source record exists; anything not held is "not recorded", never a confirmed negative). The result carries the common contract (decision, evidence, evidence path, source records, confidence).
* *Where is order NCME-ORD-000001?*: an order the shop placed is recognised, and the logistics reader reads its owner through the account that placed it (`PLACED_BY` → `ACTS_FOR` → customer) after the existing `ORDERED_BY` link, so a customer sees their own shop order. It reports the order, its lines and "no shipment recorded yet" when there is none.

#### Added in the Waterfall audit (see WATERFALL_TRACEABILITY.md)
* **Potential routes (`ROUTE_OPTIONS`)**: "How long to ship to Lagos?", "Can you deliver to the USA?" with no shipment or order named. `app/commerce/route_options.py` reads the transport lanes the network records to a place (city, country or region; `network_routes()` on both logistics readers, one read-only query) and lists each route with its own days, cost and legs, fastest first. They are labelled potential routes: none is assigned to a shipment, and the numbers are the route records' own demonstration values. A place with no lane gets no route. A shipment or order number in the message always wins.
* **Comparison and lateness**: "compare sea and air", "by air", "alternatives" show the recorded alternative routes; a shipment past its planned ETA with no delivery is stated as such (no new ETA is invented).
* **Discovery**: a word the catalogue does not know is read as the closest catalogue word when one is close (every change is listed in the answer's notes); an unmatched machine identifier is named; "I need a …" is routed by rules; a trailing "delivered to <place>" is not part of the part search.
* **Warranty wording**: the check that decided a verdict is introduced as the check that failed, was incomplete or needs review, not as a bare requirement.

### 4. Validation

* `tests/test_commerce_agent.py` (75 tests): intents, discovery, logistics (single, multi-line, split, delivered, unresolved), warranty G001–G008, multi-domain, evidence, wording guard, the API, customer/dealer/OEM isolation, malformed requests.
* `frontend/src/components/commerce/commerce.test.tsx` (13 tests): the workspace over a mocked API.
* `scripts/commerce_agent_flows.py`: Flows A to D, the security and OEM flows, through the real FastAPI app against live Neo4j, with and without the model; the graph snapshot (counts, protected counts, checksum, fingerprint) is compared before and after.

### 5. Limits
* No delivery estimate for a specific part that has not been ordered: the Assistant lists the network's potential routes to the place instead (Agentic Shopping computes route-based delivery for a part).
* Discovery clarifications that ask for a machine offer no options: the user types the model.
* The model-wording guard is a conservative check (outcomes and absences), not a proof; the deterministic text is always the fallback and is what the evidence tab backs.
* Synthetic demonstration data throughout.

<a id="order-flow"></a>

## Direct-order flow

*Originally `ORDER_FLOW.md`; Parts Store direct-order flow (as built).*

Cart → Customer details → Cart review → Delivery & dealer → Availability → Fulfilment option → Review & place order → Order confirmation →
Allocation → Fulfilment → Shipment → Tracking → Dealer service (when asked for) → Completed. There is no quote request and no second ordering path.
Every rule is enforced in FastAPI (`backend/app/services/checkout.py`, `orders.py`, `order_flow.py`, `fulfilment.py`); the browser only collects choices and
shows the state the API returns. Order state is read from AuraDB on every load.

### Who and what an order keeps (never merged)
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

Order numbers are `NCME-ORD-000001`…, from one counter node (`OrderSequence`); `Order.idempotency_key` is unique, so a retried or double-submitted place-order creates one order.

### Availability, depot, transport
* Stock is known only for `IN_STOCK` / `LOW_STOCK` rows that carry a quantity. `UNKNOWN` stays UNKNOWN: it is shown as unknown, is never read as zero, and is never allocated.
* A depot is selectable only if every line has known stock ≥ quantity **and** a recorded route to the chosen ship-to (route + freight-rate record). The depot is not chosen by "most stock": it is ranked by the estimated transit and distance of its standard road route; the user confirms depot and option.
* Options are the existing `TransportRoute` nodes `(Warehouse)<-[:FROM_DEPOT]-(r)-[:TO_SHIP_TO]->(ShipTo)` with `USES_OPTION` and `PRICED_BY`; nothing is invented, and a depot without a route offers nothing.

### Allocation
After the order exists, one transaction takes the inventory rows' write locks (in part order), reserves each line only if `available >= quantity` for a known status, decrements `available`, increments `reserved`, records `ALLOCATED_FROM` with the quantity, marks the lines and order `RESERVED` and writes the audit event. If any line cannot be reserved the whole transaction rolls back and the order is recorded as `ALLOCATION_FAILED`. Two orders cannot reserve the same units (tested with 2 and 4 simultaneous allocations against the live graph). Dispatch consumes the reserved units (`on_hand` and `reserved` fall); cancelling or releasing before dispatch puts them back.

### Lifecycle (one status vocabulary: `OrderStatus` nodes)
`NEW` (order placed) → `ALLOCATED` → `FULFILMENT_PENDING` → `FULFILLING` → `READY_TO_SHIP` → `SHIPPED` → `DELIVERED` → `COMPLETED`.
Shipment (own node): `CREATED → DISPATCHED → IN_TRANSIT → DELIVERED`, with synthetic tracking events. Dealer service (own node, only when requested): `CREATED → PART_RECEIVED → STARTED → INSTALLED → COMPLETED`; completing it completes the order; an order without service completes directly after delivery.
Exceptions: `REJECTED`, `ALLOCATION_FAILED`, `ALLOCATION_RELEASED`, `CANCELLED`, `SHIPMENT_EXCEPTION`, `DELIVERY_FAILED`, `SERVICE_CANCELLED`.
Transitions are **actions** (`POST /orders/{id}/actions`), each valid only from specific statuses and shipment/service states, checked on the server and applied with the stock change and the audit event in one transaction. An End User may cancel while the order is still early; everything else is the Order Processor's (dealer steps are recorded by the processor on the dealer's behalf: there is no dealer login).

Earlier demo orders (`DEMO_WEB_STORE`, `DEMO_APP_REQUEST`) keep their forward-only flow and are never changed by this flow.
