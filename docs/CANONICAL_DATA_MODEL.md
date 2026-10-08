# Canonical data model and ingestion (schema 1.0)

Phase 2 (global network, routes, shipments, tracking and the shipment context) is described in [LOGISTICS_NETWORK.md](LOGISTICS_NETWORK.md). Phase 3 (machine lifecycle, installations, warranty evaluation and traceability, with the renamed installation relationships) is described in [LIFECYCLE_WARRANTY.md](LIFECYCLE_WARRANTY.md).

Phase 1 of the Agentic E-Commerce data foundation: typed data contracts, a JSON/CSV ingestion engine, validation, provenance, idempotency and integrity coverage, plus the migration of what already exists. No workflows, UI or prompts were changed.

## 1. How it fits the existing system
Code is in `backend/app/canonical/`, data in `backend/data/canonical/`, the command line in `backend/scripts/canonical.py`. It reuses the existing Neo4j connection settings, the provenance vocabulary, the unique `rel_id` convention, the `SRC-*` source ids and the SOURCE/DERIVED DATA INTEGRITY CHECKSUM (`scripts/eu_foundation/audit_before.py`, unchanged). Nothing existing was replaced.

## 2. Existing concept → canonical concept → graph → migration
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

## 3. Write policy
* A node is **protected** when `data_status` is SOURCE_DERIVED, DERIVED, REAL, or USER_PROVIDED, and **app-owned** when `source_id = APP-SESSION`. Neither is ever modified: the record is compared and reported as `verified`, `extension_pending` (canonical holds values the graph lacks) or `drift` (a value differs).
* `verify` datasets (orders, order lines, inventory, route legs and the protected master data) are compared even when the node is unprotected: the graph owns them in this phase.
* Other nodes are merged: only differing properties are written, so a second run writes nothing.
* New records are stamped `source_id = SRC-CANON` with `data_status`, `source_type`, `source_record_id`, `ingestion_timestamp`, `canonical_schema_version`, `canonical_dataset`. Existing records keep their own provenance.
* Relationships are unique per (type, from, to) with a deterministic `rel_id`. Nothing is ever deleted. Dry-run writes nothing.

## 4. Files
`backend/data/canonical/`: `master/` (plants, locations, categories, machines, suppliers, dealers, parts, specifications), `relationships/` (fitment, approved_sources, assemblies, legacy_part_mappings), `commerce/` (customers, orders, order_lines, inventory, pricing), `logistics/` (routes, route_legs, shipments, tracking_events), `lifecycle/` (machine_instances, technicians, work_orders, installations, replacements, warranty_policies, warranty_claims, evidence), `scenarios/` (discovery, logistics, warranty), `reference/discovery_vocabulary.json`, `manifest.json` (dataset versions and checksums), `integrity.json` (checksum baseline). Every JSON file carries `dataset`, `dataset_version`, `canonical_schema_version`, `generated_at`.

## 5. Commands
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

## 6. Integrity
* The existing SOURCE/DERIVED DATA INTEGRITY CHECKSUM is checked before and after every ingestion and recorded in the report. New domains are SYNTHETIC_DEMO and sit outside it by design.
* `dataset_checksum`: SHA-256 over a dataset's validated records (every field except `ingestion_timestamp`), independent of file order. Stored in `manifest.json`.
* `graph_fingerprint`: SHA-256 over every node and relationship created by the ingestion (`source_id = SRC-CANON`), excluding timestamps. Stored in `integrity.json`; identical after re-ingestion.

## 7. Migration path for the existing generators
`scripts/eu_foundation/*` and the workbook-to-Cypher loaders are **unchanged and still the source of the graph**. The path: generate canonical files from the graph (`export`) → validate → dry-run → ingest (a no-op for exported data: verified 0 drift) → regress → switch consumers (`FILM_*`, `CITY_COORDINATES`, the generators) to canonical data → only then remove the old generation code. Steps 1–4 are done; the switch and the removal are not.

## 8. Known limits (Phase 1)
* Normalised specification names, `valid_from/valid_to` on fitment and discovery text on the protected `Part` itself are canonical-only until a checksum rebaseline is agreed for protected records (12 specification names are `extension_pending`).
* 11 seeded shipments have no determinable route or destination location; they carry `remediation_flags` and a null `route_id` rather than an invented link.
* `FILM_*` and `CITY_COORDINATES` were migrated to canonical data in Phase 2 (see [LOGISTICS_NETWORK.md](LOGISTICS_NETWORK.md)).
* Lifecycle, fitment-context and approved-source records are synthetic and labelled `SYNTHETIC_DEMO`.
