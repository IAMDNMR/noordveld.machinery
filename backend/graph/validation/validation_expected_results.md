# Expected validation results

Computed from the canonical graph before import. After the AuraDB import every query in `validation_queries.cypher` must return exactly this.

| id | check | expected |
|---|---|---|
| V01 | Total nodes | 1840 |
| V02 | Total relationships | 3812 |
| V03 | Nodes per label | Address 44, Assembly 15, BusinessUnit 3, Carrier 1, Cart 3, CartLine 6, Category 101, ComplianceRequirement 8, Customer 10, DataSource 4, Dealer 15, DeliveryEstimate 100, IdentificationRequirement 6, LegacyReference 100, Location 5, Machine 15, MachineFamily 3, MachineSpecification 83, MachineType 15, MachineVariant 30, Order 8, OrderLine 14, OrderStatus 6, OrderStatusEvent 32, Part 100, PartCatalogProfile 100, PartSpecification 279, Plant 3, Price 100, Region 14, SearchAlias 493, ServicePlan 60, Shipment 9, ShippingRate 8, Supplier 12, SupplierBackorder 4, TrackingEvent 27, Warehouse 4 |
| V04 | Relationships per type | ADMITS_VARIANT 10, ALLOCATED_FROM 10, AVAILABLE_AT 400, BRANDED_AS 15, CARRIED_BY 9, CONTAINS_LINE 20, COVERS_CATEGORY 10, CO_ORDERED_WITH 75, DELIVERS_TO_ADDRESS 8, DELIVERS_TO_CUSTOMER 9, DISPATCHED_FROM 9, FITS 219, FOR_MACHINE 66, FOR_PART 10, FROM_WAREHOUSE 100, HAS_ALIAS 493, HAS_COMPLIANCE 100, HAS_LEGACY_REFERENCE 100, HAS_MACHINE_SPECIFICATION 83, HAS_SHIPMENT 9, HAS_SPECIFICATION 279, HAS_STATUS_EVENT 32, HAS_TRACKING_EVENT 27, HOME_PLANT 3, IDENTIFIED_BY_PART 15, IN_CATEGORY 100, IN_COUNTRY 3, IN_REGION 44, IN_SUBCATEGORY 100, ISSUED_BY_BUSINESS_UNIT 100, LOCATED_AT_ADDRESS 44, LOCATED_AT_PLANT 3, LOCATED_IN 3, MANUFACTURED_AT 15, MEMBER_OF_FAMILY 15, OF_TYPE 15, OPENED_BY 3, ORDERED_BY 8, ORIGINATES_AT 100, OWNED_BY 3, PART_OF 35, PLACED_WITH 4, PLANNED_FULFILMENT_FROM 4, PRICES_PART 100, PRODUCT_FAMILY_OF 3, PROFILES_PART 100, RECORDS_STATUS 32, REFERENCES_PART 20, RELATED_COMPONENT 2, REQUIRES_PART 71, SAME_NAME_GROUP_AS 9, SERVES_FAMILY 30, SHIPS_LINE 9, SHIPS_TO_COUNTRY 8, STOCKED_BY 315, SUBCATEGORY_OF 91, SUPPLIED_BY 157, SUPPLIES_CATEGORY 25, TO_CUSTOMER 40, TO_DEALER 60, VARIANT_OF 30 |
| V05 | Nodes and relationships per data_status | node DERIVED 165, node SOURCE_DERIVED 456, node SYNTHETIC_DEMO 1209, node USER_PROVIDED 10; relationship DERIVED 391, relationship SOURCE_DERIVED 778, relationship SYNTHETIC_DEMO 2637, relationship USER_PROVIDED 6 |
| V06 | Duplicate canonical ids (any label) | 0 rows |
| V07 | Duplicate relationships (same type, same endpoints, same rel_id) | 0 rows |
| V08 | Nodes or relationships without provenance | node 0, relationship 0 |
| V09 | Synthetic sheets not marked SYNTHETIC_DEMO | 0 |
| V10 | Relationships with a wrong endpoint label | one row per relationship type (61), bad = 0 in every row |
| V11 | Forbidden relationship types | 0 |
| V12 | Interchangeability asserted | 0 |
| V13 | Fitment status | CONDITIONAL 3, CONFIRMED 216 |
| V14 | Conditional fitments (must stay conditional) | NVM-1010-ST -> BTS-250: cross-compatible after 2019 unification; NVM-1020-ST -> BTS-250: cross-compatible after 2019 unification; NVM-1140-DT -> NV-7500: For tracked NV-7500 variant |
| V15 | Co-order duplication (mirrored pairs) | 0 |
| V16 | Co-order relationships | c 75, merged 14 |
| V17 | Part -> machines (NVM-1010-HY) | NV-3200 CONFIRMED, NV-4500 CONFIRMED |
| V18 | Machine -> parts (NV-4500) | 52 |
| V19 | Machine with no parts | KFT-120 |
| V20 | Part -> category, sub-category, legacy | Hydraulics, Hydraulic hose, AS-771 |
| V21 | Part -> suppliers | Veldstra Hydraulics (demo) true 28 SYNTHETIC_DEMO; Rijnmond Hydraulic Supply (demo) false 10 SYNTHETIC_DEMO |
| V22 | Part -> dealers | Brabant Heavy Parts (demo) 8; Drenthe Techniek (demo) 5; IJsselvallei Equipment (demo) 7 |
| V23 | Part -> warehouse inventory | Bakker Parts Depot Coevorden (demo) 9; Kessler Parts Depot Lingen (demo) 20; Noordveld Central Warehouse Assen (demo) 56; Regional Distribution Centre Zwolle (demo) 11 |
| V24 | Excluded dealer zero-rows are absent | 0 |
| V25 | Part -> orders | parts_ordered 14, orders 8 |
| V26 | Order -> customer and shipments | 8 rows; 4 orders with at least one shipment |
| V27 | Shipment -> tracking events | 9 shipments, 27 events |
| V28 | Service plan -> machine and parts | plans 60, machines 15, parts 33 |
| V29 | No service jobs, alternatives, supersessions or risks | 0, 0 |
| V30 | Trace part -> machine -> order -> shipment -> service | rows for NV-3200 and NV-4500; 4 service plans each |
| V31 | Impact analysis: part -> machines -> orders -> service plans | machines 2, orders 0, service_plans 1 |
| V32 | Provenance traversal | NV-3200 SOURCE_DERIVED machine_part_fitment FIT-0002 Catalog workbook (supplied); NV-4500 SOURCE_DERIVED machine_part_fitment FIT-0003 Catalog workbook (supplied) |
| V33 | Idempotency check (run after a second import) | 1840 and 3812: unchanged after re-running every file |
