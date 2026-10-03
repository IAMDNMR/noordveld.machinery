# Graph readiness report

Generated 2026-10-03T08:14:37 by `scripts/graph_build.py` from `data\processed\noordveld-complete-dataset-synthetic-demo.xlsx` (identical to the Downloads copy) and
`data\catalogue\noordveld-parts-catalog.xlsx`. No database was contacted.

## GRAPH_READINESS = PASS

| Measure | Value |
|---|---|
| Nodes | 1840 |
| Relationships | 3812 |
| Node labels | 38 |
| Relationship types | 61 |
| Duplicate nodes | 0 |
| Duplicate relationships | 0 |
| Duplicate semantic relationships | 0 |
| Orphan relationships | 0 |
| Broken references | 0 |
| Relationship violations (endpoint + source + direction + cardinality + semantic) | 0 |
| Synthetic records (nodes + relationships) | 3846 |
| Source-derived records | 1234 |
| Derived records | 556 |
| User-provided (project brief) records | 16 |
| Excluded source records | 40 |

## Gate checks

| id | check | result | status |
|---|---|---|---|
| G01 | Duplicate canonical node IDs | 0 | PASS |
| G02 | Missing (null) canonical node IDs | 0 | PASS |
| G03 | Duplicate relationship IDs | 0 | PASS |
| G04 | Duplicate relationships (same type and endpoints) | 0 | PASS |
| G05 | Duplicate semantic relationships (symmetric facts stored in both directions) | 0 | PASS |
| G06 | Broken references (relationship endpoint does not exist) | 0 | PASS |
| G07 | Orphan relationships (no source record / provenance) | 0 | PASS |
| G08 | Invalid endpoint types (not in the relationship contract) | 0 | PASS |
| G09 | Relationships from a source the contract does not allow | 0 | PASS |
| G10 | Inconsistent relationship direction (a type used both ways) | 0 | PASS |
| G11 | Generic or unsupported relationship types (RELATED_TO, HAS, ALTERNATIVE_TO, SUPERSEDES, INTERCHANGEABLE...) | 0 | PASS |
| G12 | Interchangeability asserted anywhere | 0 | PASS |
| G13 | Conditional fitments kept CONDITIONAL | 3 of 3 | PASS |
| G14 | Fitments imported = source fitment rows | 219 of 219 | PASS |
| G15 | Fitment added by synthetic data | 0 | PASS |
| G16 | Supplier relationships not backed by an explicit supplier record | 0 | PASS |
| G17 | Dealer relationships not backed by an explicit stocking record | 0 | PASS |
| G18 | Unknown dealer stock imported as 0 (unsupported inventory) | 0 | PASS |
| G19 | Synthetic records carrying data_status = SYNTHETIC_DEMO | 3846 of 3846 (100%) | PASS |
| G20 | Catalogue records labelled synthetic (or synthetic overwriting source) | 0 | PASS |
| G21 | Missing values replaced by guesses or stored as fake values | 0 | PASS |
| G22 | Legacy identifiers confused with canonical identifiers | 0 | PASS |
| G23 | Graph facts without provenance | 0 | PASS |
| G24 | Conflicting relationship types for one fact (allocated AND planned) | 0 | PASS |
| G25 | Cardinality violations (exactly-one / single-owner rules) | 0 | PASS |
| G26 | Catalogue parts differing from the original catalogue workbook | 0 of 100 | PASS |
| G27 | Catalogue machines missing from the original workbook | 0 | PASS |
| G28 | Excluded source records documented | 40 documented | PASS |
| G29 | Downloads copy identical to data/processed copy | True | PASS |
| G30 | Source foreign-key columns not accounted for (neither a relationship nor an explained exclusion) | 0 | PASS |
| G31 | Relationship types in the contract missing from the coverage matrix | 0 | PASS |
| G32 | Coverage rows whose status contradicts the graph | 0 | PASS |
| G33 | Required relationships explicitly accounted for | 50 of 50 | PASS |

## Warnings (acceptable, represented honestly)

- Operational layers are SYNTHETIC_DEMO: suppliers (12), dealers (15), warehouses (4), stock, prices, compliance, orders, shipments and service plans. Never present them as real.
- 3 fitments are CONDITIONAL: For tracked NV-7500 variant (PRT-030 -> MCH-005), cross-compatible after 2019 unification (PRT-044 -> MCH-012), cross-compatible after 2019 unification (PRT-045 -> MCH-012).
- Machine with no parts in the catalogue: KFT-120 (no fitment is manufactured for it).
- 5 legacy part numbers are unresolved free text: NVM-1090-HY, NVM-1130-HY, NVM-1060-DT, NVM-1070-EL, NVM-2205-BH.
- Shipments exist for 4 of 8 orders; 9 of 14 order lines shipped.
- Assemblies cover 43 of 100 parts; service plans cover 33 of 100 parts.
- Warehouse WH-004 (Zwolle) has no plant link in the source (not filled).
- Machine status, introduction year, category, production status and description are NOT_STATED for all 15 machines; part type, OEM status and criticality are NOT_STATED for all 100 parts.
- Machine families and sub-categories are DERIVED by rule and await business confirmation.
- Plants are fictional (USER_PROVIDED, declared by the project brief). Plant coordinates are NOT_STATED; synthetic coordinates in SYN_geo_nodes are deliberately not imported.
- Reference nodes with no relationships (by design): ShippingRate 8, DataSource 4.
- No item in the workbook is externally verified, including the catalogue layer: authoritative_flag = false everywhere.
- Workbook inconsistency: 01_Legend says 'SYNTHETIC: none exists in this dataset' (written for the catalogue layer) while the SYN_ sheets are synthetic; record_counts labels catalogue sheets 'REAL_DERIVED' although 00_README says nothing is real. The graph follows the row-level data_class.
- SYN_data_sources rows (including SRC-001, which describes the supplied catalogue) carry data_class SYNTHETIC in the workbook; the DataSource nodes keep that class rather than relabelling it.

## Missing domains (schema supports them; no records are created)

- MACHINE_UNITS (serial-numbered machines)
- CONFIGURATIONS
- REQUESTS / REQUEST_LINES
- SERVICE_JOBS
- INSTALLATIONS / COMPLETION
- ALTERNATIVES
- SUPERSESSIONS
- RISKS

## Fixes applied in this build

- **Mirrored co-order duplicates:** 14 `SYN_part_relationships` rows repeated a pair that was already present in the opposite
  direction. `CO_ORDERED_WITH` is symmetric, so each pair is stored once (lower part id to higher part id) and the
  duplicate's record id is kept on the stored relationship (`merged_source_record_ids`). 89 rows → 75 relationships.
  `SAME_NAME_GROUP_AS` (also symmetric) had no mirrored rows. No directional relationship was touched.
- **Unknown dealer stock:** 26 `SYN_inventory` rows state 0 stock at a dealer that `SYN_part_dealer` does not list as
  stocking the part. They remain excluded (UNKNOWN, not ZERO); see `excluded_records.csv`.
