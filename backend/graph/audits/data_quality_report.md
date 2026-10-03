# Data quality report

## Sources

- `noordveld-complete-dataset-synthetic-demo.xlsx`: 60 sheets. Catalogue sheets are SOURCE_DERIVED / DERIVED from the supplied catalogue;
  `SYN_` sheets are synthetic (seed 42); `plants` and `order_statuses` are DEMO (declared by the project brief).
- `noordveld-parts-catalog.xlsx`: the supplied catalogue (100 parts, 15 machine types). Every catalogue part matches it
  (name, category, plant, compatible machines): 0 differences.
- The Downloads copy is byte-identical to `data/processed/`.

Per-sheet row counts, identifiers, duplicates, nulls, NOT_STATED and blank counts: `source_inventory.csv`.

## Entity quality

| label | canonical_id | nodes | duplicate_ids | relationships_touching | isolated_nodes | provenance |
|---|---|---|---|---|---|---|
| Address | address_id | 44 | 0 | 96 | 0 | SYNTHETIC_DEMO:44 |
| Assembly | assembly_id | 15 | 0 | 50 | 0 | SYNTHETIC_DEMO:15 |
| BusinessUnit | business_unit_id | 3 | 0 | 124 | 0 | SOURCE_DERIVED:3 |
| Carrier | carrier_id | 1 | 0 | 9 | 0 | SYNTHETIC_DEMO:1 |
| Cart | cart_id | 3 | 0 | 9 | 0 | SYNTHETIC_DEMO:3 |
| CartLine | cart_line_id | 6 | 0 | 12 | 0 | SYNTHETIC_DEMO:6 |
| Category | category_id | 101 | 0 | 417 | 0 | SOURCE_DERIVED:10 / DERIVED:91 |
| ComplianceRequirement | compliance_id | 8 | 0 | 110 | 0 | SYNTHETIC_DEMO:8 |
| Customer | customer_id | 10 | 0 | 70 | 0 | SYNTHETIC_DEMO:10 |
| DataSource | source_id | 4 | 0 | 0 | 4 | SYNTHETIC_DEMO:3 / USER_PROVIDED:1 |
| Dealer | dealer_id | 15 | 0 | 420 | 0 | SYNTHETIC_DEMO:15 |
| DeliveryEstimate | delivery_estimate_id | 100 | 0 | 200 | 0 | SYNTHETIC_DEMO:100 |
| IdentificationRequirement | requirement_id | 6 | 0 | 22 | 0 | SYNTHETIC_DEMO:6 |
| LegacyReference | legacy_reference_id | 100 | 0 | 200 | 0 | SOURCE_DERIVED:100 |
| Location | location_id | 5 | 0 | 17 | 0 | SOURCE_DERIVED:5 |
| Machine | machine_id | 15 | 0 | 503 | 0 | SOURCE_DERIVED:15 |
| MachineFamily | family_id | 3 | 0 | 48 | 0 | DERIVED:3 |
| MachineSpecification | machine_spec_id | 83 | 0 | 83 | 0 | SYNTHETIC_DEMO:83 |
| MachineType | machine_type_id | 15 | 0 | 15 | 0 | SOURCE_DERIVED:15 |
| MachineVariant | variant_id | 30 | 0 | 40 | 0 | SYNTHETIC_DEMO:30 |
| Order | order_id | 8 | 0 | 71 | 0 | SYNTHETIC_DEMO:8 |
| OrderLine | order_line_id | 14 | 0 | 51 | 0 | SYNTHETIC_DEMO:14 |
| OrderStatus | order_status_code | 6 | 0 | 32 | 0 | USER_PROVIDED:6 |
| OrderStatusEvent | status_event_id | 32 | 0 | 64 | 0 | SYNTHETIC_DEMO:32 |
| Part | part_id | 100 | 0 | 2841 | 0 | SOURCE_DERIVED:100 |
| PartCatalogProfile | profile_id | 100 | 0 | 100 | 0 | SYNTHETIC_DEMO:100 |
| PartSpecification | specification_id | 279 | 0 | 279 | 0 | SOURCE_DERIVED:208 / DERIVED:71 |
| Plant | plant_id | 3 | 0 | 130 | 0 | USER_PROVIDED:3 |
| Price | price_id | 100 | 0 | 100 | 0 | SYNTHETIC_DEMO:100 |
| Region | region_id | 14 | 0 | 44 | 0 | SYNTHETIC_DEMO:14 |
| SearchAlias | alias_id | 493 | 0 | 493 | 0 | SYNTHETIC_DEMO:493 |
| ServicePlan | service_plan_id | 60 | 0 | 131 | 0 | SYNTHETIC_DEMO:60 |
| Shipment | shipment_id | 9 | 0 | 72 | 0 | SYNTHETIC_DEMO:9 |
| ShippingRate | rate_id | 8 | 0 | 0 | 8 | SYNTHETIC_DEMO:8 |
| Supplier | supplier_id | 12 | 0 | 198 | 0 | SYNTHETIC_DEMO:12 |
| SupplierBackorder | backorder_id | 4 | 0 | 8 | 0 | SYNTHETIC_DEMO:4 |
| TrackingEvent | tracking_event_id | 27 | 0 | 27 | 0 | SYNTHETIC_DEMO:27 |
| Warehouse | warehouse_id | 4 | 0 | 538 | 0 | SYNTHETIC_DEMO:4 |

## Field completeness (fields with values the source does not state)

| entity_or_domain | field_or_relationship | records_missing | records_total | classification |
|---|---|---|---|---|
| BusinessUnit | acquired_year | 1 | 3 | PARTIAL |
| Category | description | 101 | 101 | MISSING |
| Category | review_flags | 10 | 101 | PARTIAL |
| LegacyReference | legacy_code_prefix | 5 | 100 | PARTIAL |
| LegacyReference | legacy_part_number | 5 | 100 | PARTIAL |
| LegacyReference | legacy_system | 100 | 100 | MISSING |
| LegacyReference | review_flags | 93 | 100 | PARTIAL |
| Location | postal_code | 5 | 5 | MISSING |
| Location | region | 5 | 5 | MISSING |
| Machine | description | 15 | 15 | MISSING |
| Machine | introduction_year | 15 | 15 | MISSING |
| Machine | machine_category | 15 | 15 | MISSING |
| Machine | production_status | 15 | 15 | MISSING |
| Machine | review_flags | 15 | 15 | MISSING |
| Machine | status | 15 | 15 | MISSING |
| MachineSpecification | unit | 15 | 83 | PARTIAL |
| Part | criticality | 100 | 100 | MISSING |
| Part | oem_status | 100 | 100 | MISSING |
| Part | part_nature | 85 | 100 | PARTIAL |
| Part | part_status | 100 | 100 | MISSING |
| Part | part_type | 100 | 100 | MISSING |
| Part | review_flags | 90 | 100 | PARTIAL |
| PartSpecification | normalized_unit | 208 | 279 | PARTIAL |
| PartSpecification | normalized_value | 208 | 279 | PARTIAL |
| PartSpecification | source_label | 247 | 279 | PARTIAL |
| PartSpecification | unit | 208 | 279 | PARTIAL |
| Plant | manufacturing_role | 3 | 3 | MISSING |

## Partial synthetic coverage (preserved, not filled)

- Orders: 8; orders with shipments: 4; shipped order lines: 9 of 14.
- Assemblies: 15, covering 43 parts. Service plans: 60, covering 33 parts.
- Warehouse WH-004 (Zwolle): no plant link.
- Order lines: 10 allocated (reserved or shipped), 4 not yet allocated (planned source only).

## Unresolved source items (kept unresolved)

- Machine with no catalogue parts: KFT-120.
- Legacy part numbers recorded only as free text: NVM-1090-HY (LEG-010), NVM-1130-HY (LEG-014), NVM-1060-DT (LEG-022), NVM-1070-EL (LEG-037), NVM-2205-BH (LEG-043).
- Conditional fitments: PRT-030 -> MCH-005: For tracked NV-7500 variant, PRT-044 -> MCH-012: cross-compatible after 2019 unification, PRT-045 -> MCH-012: cross-compatible after 2019 unification.

## Cross-dataset consistency

- Dealer stock (`SYN_inventory`, 341 dealer rows) vs dealer stocking (`SYN_part_dealer`, 315): 26 inventory rows have no
  stocking record. All 26 are 0-stock rows → excluded as UNKNOWN.
- Primary supplier on `SYN_part_catalog` vs `SYN_part_supplier.is_primary`: consistent for all 100 parts.
- List price on `SYN_part_catalog` vs `SYN_pricing`: consistent for all 100 parts.
- Store display names vs catalogue part names: identical for all 100 parts.

## Reconciliation with the workbook's own edge list (`relationships_all`, not imported)

| workbook_type | workbook_edges | graph_type | graph_edges | match | note |
|---|---|---|---|---|---|
| PRODUCED_AT | 15 | MANUFACTURED_AT | 15 | YES |  |
| HAS_MACHINE_TYPE | 15 | OF_TYPE | 15 | YES |  |
| IN_FAMILY | 15 | MEMBER_OF_FAMILY | 15 | YES |  |
| OF_BRAND | 15 | BRANDED_AS | 15 | YES |  |
| FAMILY_OF_BRAND | 3 | PRODUCT_FAMILY_OF | 3 | YES |  |
| OWNED_BY | 3 | OWNED_BY | 3 | YES |  |
| LOCATED_IN | 3 | LOCATED_IN | 3 | YES |  |
| IN_COUNTRY | 3 | IN_COUNTRY | 3 | YES |  |
| SUBCATEGORY_OF | 91 | SUBCATEGORY_OF | 91 | YES |  |
| IN_CATEGORY | 100 | IN_CATEGORY | 100 | YES |  |
| IN_SUBCATEGORY | 100 | IN_SUBCATEGORY | 100 | YES |  |
| ORIGINATES_AT | 100 | ORIGINATES_AT | 100 | YES |  |
| HAS_PART_FITMENT | 219 | FITS | 219 | YES |  |
| HAS_LEGACY_MAPPING | 100 | HAS_LEGACY_REFERENCE | 100 | YES |  |
| LEGACY_BUSINESS | 100 | ISSUED_BY_BUSINESS_UNIT | 100 | YES |  |
| SAME_SUBCATEGORY | 9 | SAME_NAME_GROUP_AS | 9 | YES |  |
| RELATED_COMPONENT | 2 | RELATED_COMPONENT | 2 | YES |  |
| SUPPLIED_BY | 157 | SUPPLIED_BY | 157 | YES |  |
| STOCKED_AT | 741 | AVAILABLE_AT + STOCKED_BY | 715 | EXPLAINED | 26 dealer zero-rows excluded (UNKNOWN, not 0) |
| HAS_COMPONENT | 35 | PART_OF | 35 | YES | direction Part -> Assembly |
| USES_PART | 71 | REQUIRES_PART | 71 | YES |  |
| SERVICES_MACHINE | 60 | FOR_MACHINE | 60 | YES |  |
| FREQUENTLY_ORDERED_WITH_DEMO | 89 | CO_ORDERED_WITH | 75 | EXPLAINED | 14 mirrored duplicates stored once |
| ORDERS_PART | 14 | REFERENCES_PART | 14 | YES |  |
| FULFILLED_FROM | 14 | ALLOCATED_FROM + PLANNED_FULFILMENT_FROM | 14 | YES | workbook edge is order -> warehouse with 3 repeats; graph is per order line and split by allocation status |
| PLACED_BY | 8 | ORDERED_BY | 8 | YES |  |
| LOCATED_AT_PLANT | 3 | LOCATED_AT_PLANT | 3 | YES |  |
| DEALER_SERVES_FAMILY | 30 | SERVES_FAMILY | 30 | YES |  |
| MEETS_COMPLIANCE | 100 | HAS_COMPLIANCE | 100 | YES |  |
| ON_BACKORDER_FROM | 4 | PLACED_WITH | 4 | YES |  |

## Not imported (and why)

- `00_README`: workbook documentation
- `01_Legend`: workbook documentation
- `search_index`: derived search text (embedding_status NOT_GENERATED)
- `part_data_coverage`: derived coverage summary (used in this audit)
- `relationships_all`: workbook's own edge list; used only to reconcile counts
- `SYN_geo_nodes`: synthetic coordinates (kept off nodes so source NOT_STATED coordinates are not overwritten)
- `SYN_distances`: pairwise distances; proximity must never create business relationships
- `SYN_roles`: access control, not required for this phase
- `SYN_users`: access control, not required for this phase
- `SYN_agent_test_questions`: golden test questions (used for validation design)
- `SYN_prototype_gap_analysis`: workbook metadata
- `data_dictionary`: workbook metadata
- `record_counts`: workbook metadata
- `SYN_quality_checks`: workbook's own QA results
