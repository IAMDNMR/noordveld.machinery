# Relationship coverage audit

## GRAPH RELATIONSHIP COVERAGE = PASS

Every required relationship, and every relationship found by inspecting the source data, is classified in
`relationship_coverage_matrix.csv`. Nothing is omitted. Source columns that look like references: 81; each is either a
relationship or an explained exclusion (8 exclusions).

| Required relationships (the 50 you listed) | Count |
|---|---|
| TOTAL RELATIONSHIPS REQUIRED | 50 |
| IMPLEMENTED_WITH_DATA | 10 |
| IMPLEMENTED_SYNTHETIC | 27 |
| SCHEMA_ONLY_NO_DATA | 13 |
| NOT_APPLICABLE | 0 |
| BLOCKED_BY_MISSING_DATA | 0 |

| Additional relationships found in the source data | Count |
|---|---|
| TOTAL | 50 |
| IMPLEMENTED_WITH_DATA | 11 |
| IMPLEMENTED_SYNTHETIC | 32 |
| SCHEMA_ONLY_NO_DATA | 0 |
| NOT_APPLICABLE | 5 |
| BLOCKED_BY_MISSING_DATA | 2 |

## Relationships added by this audit (the source states them; they were only text columns before)

- `HOME_PLANT` (BusinessUnit to Plant), from `business_units.home_plant_id`
- `SUPPLIES_CATEGORY` (Supplier to Category), from `SYN_suppliers.categories_supplied`. Declared scope only: it does NOT imply any part-level supply.
- `COVERS_CATEGORY` (ComplianceRequirement to Category), from `SYN_compliance.categories_covered`
- `SHIPS_TO_COUNTRY` (Warehouse to Location), from `SYN_warehouses.ships_to` (NL and DE; BE is blocked, see below)

## Blocked or schema-only, with the data needed

| GROUP | SOURCE_NODE | RELATIONSHIP | TARGET_NODE | STATUS | MISSING_DATA |
|---|---|---|---|---|---|
| REQUIRED | Order | Order -> Allocation | Allocation | SCHEMA_ONLY_NO_DATA | Allocation records (quantity per warehouse, timestamps) |
| REQUIRED | Order | Order -> Fulfilment | Fulfilment | SCHEMA_ONLY_NO_DATA | Fulfilment records |
| REQUIRED | ServiceJob | FOR_MACHINE | Machine | SCHEMA_ONLY_NO_DATA | ServiceJob records |
| REQUIRED | ServiceJob | REQUIRES_PART | Part | SCHEMA_ONLY_NO_DATA | ServiceJob records |
| REQUIRED | ServiceJob | PERFORMED_BY | Dealer | SCHEMA_ONLY_NO_DATA | ServiceJob records and dealer service assignments |
| REQUIRED | Part | HAS_RISK | SourceRisk | SCHEMA_ONLY_NO_DATA | Risk records |
| REQUIRED | Part | ALTERNATIVE_TO | Part | SCHEMA_ONLY_NO_DATA | Authoritative alternative / interchangeability evidence |
| REQUIRED | Part | SUPERSEDES / SUPERSEDED_BY | Part | SCHEMA_ONLY_NO_DATA | Supersession records |
| REQUIRED | Machine | Machine -> Configuration | Configuration | SCHEMA_ONLY_NO_DATA | Configuration records |
| REQUIRED | Customer | Customer -> Request | Request | SCHEMA_ONLY_NO_DATA | Request records |
| REQUIRED | Request | Request -> Part | Part | SCHEMA_ONLY_NO_DATA | Request lines |
| REQUIRED | Installation | Installation -> Machine | Machine | SCHEMA_ONLY_NO_DATA | Installation records |
| REQUIRED | Installation | Installation -> Part | Part | SCHEMA_ONLY_NO_DATA | Installation records |
| ADDITIONAL | Warehouse (WH-004) | LOCATED_AT_PLANT | Plant | BLOCKED_BY_MISSING_DATA | plant_id for WH-004 |
| ADDITIONAL | Warehouse | SHIPS_TO_COUNTRY (Belgium) | Location (BE) | BLOCKED_BY_MISSING_DATA | A Belgium country Location |

## Deliberately not relationships

| SOURCE_NODE | RELATIONSHIP | CURRENTLY_IMPLEMENTED |
|---|---|---|
| DeliveryEstimate | DeliveryEstimate -> ShippingRate | NO: The workbook states no link; the rate is only derivable from the distance band. A derivable link is not a stated one, so it is not created. |
| User / Role | User -> Customer, User -> Role | NO: SYN_users / SYN_roles are access-control demo data, not part of Parts Intelligence for this phase. |
| Any place | DISTANCE_TO (SYN_distances, 946 pairs) | NO: Proximity must never create a business relationship; distances are not imported. |
| Supplier / Dealer | Supplier or Dealer -> Plant / Machine / Customer by proximity or country | NO: Forbidden inference: no supplier, dealer or customer relationship is derived from location. |
| Part | Part -> Part by shared machines or similar names | NO: Forbidden inference: shared fitment or naming never creates an alternative or interchangeable relationship. |

## Source columns and what happens to them

| sheet | column | handled by |
|---|---|---|
| SYN_addresses | owner_id | LOCATED_AT_ADDRESS (plants here; other owners through their own address_id) |
| SYN_addresses | owner_name | EXCLUDED: a label, not an identifier |
| SYN_addresses | owner_type | LOCATED_AT_ADDRESS (plants here; other owners through their own address_id) |
| SYN_assembly_components | assembly_id | PART_OF |
| SYN_assembly_components | component_part_id | PART_OF |
| SYN_assembly_master | assembly_part_id | IDENTIFIED_BY_PART |
| SYN_cart_items | cart_id | CONTAINS_LINE |
| SYN_cart_items | part_id | REFERENCES_PART |
| SYN_carts | customer_id | OPENED_BY |
| SYN_compliance | categories_covered | COVERS_CATEGORY |
| SYN_customers | address_id | LOCATED_AT_ADDRESS |
| SYN_dealers | address_id | LOCATED_AT_ADDRESS |
| SYN_dealers | families_served | SERVES_FAMILY |
| SYN_delivery_options | from_warehouse_id | FROM_WAREHOUSE |
| SYN_delivery_options | to_id | TO_CUSTOMER / TO_DEALER |
| SYN_distances | from_node_id | EXCLUDED: proximity never creates a relationship |
| SYN_distances | to_node_id | EXCLUDED: proximity never creates a relationship |
| SYN_identification_requirements | fits_variant_ids | ADMITS_VARIANT |
| SYN_identification_requirements | machine_id | FOR_MACHINE |
| SYN_identification_requirements | part_id | FOR_PART |
| SYN_inventory | location_id | AVAILABLE_AT / STOCKED_BY (quantities) |
| SYN_inventory | part_id | AVAILABLE_AT / STOCKED_BY (quantities) |
| SYN_machine_specifications | machine_id | HAS_MACHINE_SPECIFICATION |
| SYN_machine_variants | machine_id | VARIANT_OF |
| SYN_order_items | fulfilment_location_id | ALLOCATED_FROM / PLANNED_FULFILMENT_FROM |
| SYN_order_items | order_id | CONTAINS_LINE |
| SYN_order_items | part_id | REFERENCES_PART |
| SYN_order_status_history | order_id | HAS_STATUS_EVENT |
| SYN_orders | customer_id | ORDERED_BY |
| SYN_orders | delivery_address_id | DELIVERS_TO_ADDRESS |
| SYN_part_catalog | primary_supplier_id | SUPPLIED_BY.is_primary (checked identical for all 100 parts; not stored twice) |
| SYN_part_compliance | compliance_id | HAS_COMPLIANCE |
| SYN_part_compliance | part_id | HAS_COMPLIANCE |
| SYN_part_dealer | dealer_id | STOCKED_BY |
| SYN_part_dealer | part_id | STOCKED_BY |
| SYN_part_relationships | from_part_id | CO_ORDERED_WITH |
| SYN_part_relationships | to_part_id | CO_ORDERED_WITH |
| SYN_part_supplier | part_id | SUPPLIED_BY |
| SYN_part_supplier | supplier_id | SUPPLIED_BY |
| SYN_pricing | part_id | PRICES_PART |
| SYN_search_aliases | entity_id | HAS_ALIAS |
| SYN_service_parts | part_id | REQUIRES_PART |
| SYN_service_parts | service_id | REQUIRES_PART |
| SYN_services | machine_id | FOR_MACHINE |
| SYN_shipment_events | shipment_id | HAS_TRACKING_EVENT |
| SYN_shipments | from_location_id | DISPATCHED_FROM |
| SYN_shipments | order_id | HAS_SHIPMENT |
| SYN_shipments | order_item_id | SHIPS_LINE |
| SYN_shipments | to_customer_id | DELIVERS_TO_CUSTOMER |
| SYN_supplier_backorders | part_id | FOR_PART |
| SYN_supplier_backorders | supplier_id | PLACED_WITH |
| SYN_suppliers | address_id | LOCATED_AT_ADDRESS |
| SYN_suppliers | categories_supplied | SUPPLIES_CATEGORY |
| SYN_users | customer_id | EXCLUDED: access control, not required for this phase |
| SYN_users | role_id | EXCLUDED: access control, not required for this phase |
| SYN_warehouses | address_id | LOCATED_AT_ADDRESS |
| SYN_warehouses | plant_id | LOCATED_AT_PLANT |
| SYN_warehouses | ships_to | SHIPS_TO_COUNTRY |
| business_units | home_plant_id | HOME_PLANT |
| categories | parent_category_id | SUBCATEGORY_OF |
| legacy_part_mapping | current_part_id | HAS_LEGACY_REFERENCE |
| legacy_part_mapping | legacy_business_unit_id | ISSUED_BY_BUSINESS_UNIT |
| locations | parent_location_id | IN_COUNTRY |
| machine_families | business_unit_id | PRODUCT_FAMILY_OF |
| machine_part_fitment | machine_id | FITS |
| machine_part_fitment | part_id | FITS |
| machines | business_unit_id | BRANDED_AS |
| machines | family_id | MEMBER_OF_FAMILY |
| machines | machine_type_id | OF_TYPE |
| machines | plant_id | MANUFACTURED_AT |
| part_relationships | from_part_id | SAME_NAME_GROUP_AS / RELATED_COMPONENT |
| part_relationships | to_part_id | SAME_NAME_GROUP_AS / RELATED_COMPONENT |
| part_specifications | part_id | HAS_SPECIFICATION |
| parts | category_id | IN_CATEGORY |
| parts | plant_id | ORIGINATES_AT |
| parts | subcategory_id | IN_SUBCATEGORY |
| plants | business_unit_id | OWNED_BY |
| plants | location_id | LOCATED_IN |
| relationships_all | from_id | EXCLUDED: the workbook's own edge list, reconciled not imported |
| relationships_all | to_id | EXCLUDED: the workbook's own edge list, reconciled not imported |
| search_index | entity_id | EXCLUDED: derived search text, not imported |

## Reading the inverse rows

Rows such as "Machine -> Part" and "Supplier -> Part" are inverse traversals of one stored relationship (`FITS`, `SUPPLIED_BY`).
Storing both directions would duplicate the same fact, which the readiness gate forbids; Cypher traverses either way.
