# Demo enrichment: graph audit

Taken 2026-10-03T16:30:28+00:00 (read-only). Nodes **1840**, relationships **3812**, constraints 99.

Provenance (nodes): {"SOURCE_DERIVED": 456, "DERIVED": 165, "USER_PROVIDED": 10, "SYNTHETIC_DEMO": 1209}
Provenance (relationships): {"SOURCE_DERIVED": 778, "DERIVED": 391, "SYNTHETIC_DEMO": 2637, "USER_PROVIDED": 6}

Source fingerprint (every SOURCE_DERIVED / DERIVED / USER_PROVIDED node and relationship with all properties): `f685de957e89985cd5b1d11d16d3895f23b25bdd995db0b6369eddc45cbeaaaa`

Schema-only labels (documented, no data): none

## Gaps
| Check | Value |
|---|---|
| machines_without_profile_fields | ["NV-2100", "NV-3200", "NV-4500", "NV-6000", "NV-7500", "KFT-120", "KFT-200", "KFT-450", "KFT-600", "KFT-800", "BTS-100", "BTS-250", "BTS-500", "BTS-750", "BTS-900"] |
| machines_without_fitted_parts | ["KFT-120"] |
| parts_without_assembly | 72 |
| parts_without_service_plan | 67 |
| parts_without_supplier | 0 |
| parts_without_inventory | 0 |
| parts_without_dealer | 1 |
| parts_without_compliance | 0 |
| parts_in_any_order | 14 |
| profile_fields_missing | {"application": 100, "maintenance_class": 100, "criticality": 100} |
| warehouse_fields_missing | {"warehouse_type": 4, "operating_status": 4} |
| customer_requests | 0 |
| orders | 8 |
| inventory_rows_zero_but_in_stock | 0 |

## Labels
| Label | Count | data_status |
|---|---|---|
| Address | 44 | SYNTHETIC_DEMO |
| Assembly | 15 | SYNTHETIC_DEMO |
| BusinessUnit | 3 | SOURCE_DERIVED |
| Carrier | 1 | SYNTHETIC_DEMO |
| Cart | 3 | SYNTHETIC_DEMO |
| CartLine | 6 | SYNTHETIC_DEMO |
| Category | 101 | DERIVED, SOURCE_DERIVED |
| ComplianceRequirement | 8 | SYNTHETIC_DEMO |
| Customer | 10 | SYNTHETIC_DEMO |
| DataSource | 4 | SYNTHETIC_DEMO, USER_PROVIDED |
| Dealer | 15 | SYNTHETIC_DEMO |
| DeliveryEstimate | 100 | SYNTHETIC_DEMO |
| IdentificationRequirement | 6 | SYNTHETIC_DEMO |
| LegacyReference | 100 | SOURCE_DERIVED |
| Location | 5 | SOURCE_DERIVED |
| Machine | 15 | SOURCE_DERIVED |
| MachineFamily | 3 | DERIVED |
| MachineSpecification | 83 | SYNTHETIC_DEMO |
| MachineType | 15 | SOURCE_DERIVED |
| MachineVariant | 30 | SYNTHETIC_DEMO |
| Order | 8 | SYNTHETIC_DEMO |
| OrderLine | 14 | SYNTHETIC_DEMO |
| OrderStatus | 6 | USER_PROVIDED |
| OrderStatusEvent | 32 | SYNTHETIC_DEMO |
| Part | 100 | SOURCE_DERIVED |
| PartCatalogProfile | 100 | SYNTHETIC_DEMO |
| PartSpecification | 279 | DERIVED, SOURCE_DERIVED |
| Plant | 3 | USER_PROVIDED |
| Price | 100 | SYNTHETIC_DEMO |
| Region | 14 | SYNTHETIC_DEMO |
| SearchAlias | 493 | SYNTHETIC_DEMO |
| ServicePlan | 60 | SYNTHETIC_DEMO |
| Shipment | 9 | SYNTHETIC_DEMO |
| ShippingRate | 8 | SYNTHETIC_DEMO |
| Supplier | 12 | SYNTHETIC_DEMO |
| SupplierBackorder | 4 | SYNTHETIC_DEMO |
| TrackingEvent | 27 | SYNTHETIC_DEMO |
| Warehouse | 4 | SYNTHETIC_DEMO |

## Relationships
| From | Type | To | Count | data_status |
|---|---|---|---|---|
| IdentificationRequirement | ADMITS_VARIANT | MachineVariant | 10 | SYNTHETIC_DEMO |
| OrderLine | ALLOCATED_FROM | Warehouse | 10 | SYNTHETIC_DEMO |
| Part | AVAILABLE_AT | Warehouse | 400 | SYNTHETIC_DEMO |
| Machine | BRANDED_AS | BusinessUnit | 15 | SOURCE_DERIVED |
| Shipment | CARRIED_BY | Carrier | 9 | SYNTHETIC_DEMO |
| Cart | CONTAINS_LINE | CartLine | 6 | SYNTHETIC_DEMO |
| Order | CONTAINS_LINE | OrderLine | 14 | SYNTHETIC_DEMO |
| ComplianceRequirement | COVERS_CATEGORY | Category | 10 | SYNTHETIC_DEMO |
| Part | CO_ORDERED_WITH | Part | 75 | SYNTHETIC_DEMO |
| Order | DELIVERS_TO_ADDRESS | Address | 8 | SYNTHETIC_DEMO |
| Shipment | DELIVERS_TO_CUSTOMER | Customer | 9 | SYNTHETIC_DEMO |
| Shipment | DISPATCHED_FROM | Warehouse | 9 | SYNTHETIC_DEMO |
| Part | FITS | Machine | 219 | SOURCE_DERIVED |
| IdentificationRequirement | FOR_MACHINE | Machine | 6 | SYNTHETIC_DEMO |
| ServicePlan | FOR_MACHINE | Machine | 60 | SYNTHETIC_DEMO |
| IdentificationRequirement | FOR_PART | Part | 6 | SYNTHETIC_DEMO |
| SupplierBackorder | FOR_PART | Part | 4 | SYNTHETIC_DEMO |
| DeliveryEstimate | FROM_WAREHOUSE | Warehouse | 100 | SYNTHETIC_DEMO |
| Machine | HAS_ALIAS | SearchAlias | 45 | SYNTHETIC_DEMO |
| Part | HAS_ALIAS | SearchAlias | 448 | SYNTHETIC_DEMO |
| Part | HAS_COMPLIANCE | ComplianceRequirement | 100 | SYNTHETIC_DEMO |
| Part | HAS_LEGACY_REFERENCE | LegacyReference | 100 | SOURCE_DERIVED |
| Machine | HAS_MACHINE_SPECIFICATION | MachineSpecification | 83 | SYNTHETIC_DEMO |
| Order | HAS_SHIPMENT | Shipment | 9 | SYNTHETIC_DEMO |
| Part | HAS_SPECIFICATION | PartSpecification | 279 | DERIVED, SOURCE_DERIVED |
| Order | HAS_STATUS_EVENT | OrderStatusEvent | 32 | SYNTHETIC_DEMO |
| Shipment | HAS_TRACKING_EVENT | TrackingEvent | 27 | SYNTHETIC_DEMO |
| BusinessUnit | HOME_PLANT | Plant | 3 | SOURCE_DERIVED |
| Assembly | IDENTIFIED_BY_PART | Part | 15 | SYNTHETIC_DEMO |
| Part | IN_CATEGORY | Category | 100 | SOURCE_DERIVED |
| Location | IN_COUNTRY | Location | 3 | SOURCE_DERIVED |
| Address | IN_REGION | Region | 44 | SYNTHETIC_DEMO |
| Part | IN_SUBCATEGORY | Category | 100 | DERIVED |
| LegacyReference | ISSUED_BY_BUSINESS_UNIT | BusinessUnit | 100 | DERIVED |
| Customer | LOCATED_AT_ADDRESS | Address | 10 | SYNTHETIC_DEMO |
| Dealer | LOCATED_AT_ADDRESS | Address | 15 | SYNTHETIC_DEMO |
| Plant | LOCATED_AT_ADDRESS | Address | 3 | SYNTHETIC_DEMO |
| Supplier | LOCATED_AT_ADDRESS | Address | 12 | SYNTHETIC_DEMO |
| Warehouse | LOCATED_AT_ADDRESS | Address | 4 | SYNTHETIC_DEMO |
| Warehouse | LOCATED_AT_PLANT | Plant | 3 | SYNTHETIC_DEMO |
| Plant | LOCATED_IN | Location | 3 | USER_PROVIDED |
| Machine | MANUFACTURED_AT | Plant | 15 | SOURCE_DERIVED |
| Machine | MEMBER_OF_FAMILY | MachineFamily | 15 | DERIVED |
| Machine | OF_TYPE | MachineType | 15 | SOURCE_DERIVED |
| Cart | OPENED_BY | Customer | 3 | SYNTHETIC_DEMO |
| Order | ORDERED_BY | Customer | 8 | SYNTHETIC_DEMO |
| Part | ORIGINATES_AT | Plant | 100 | SOURCE_DERIVED |
| Plant | OWNED_BY | BusinessUnit | 3 | USER_PROVIDED |
| Part | PART_OF | Assembly | 35 | SYNTHETIC_DEMO |
| SupplierBackorder | PLACED_WITH | Supplier | 4 | SYNTHETIC_DEMO |
| OrderLine | PLANNED_FULFILMENT_FROM | Warehouse | 4 | SYNTHETIC_DEMO |
| Price | PRICES_PART | Part | 100 | SYNTHETIC_DEMO |
| MachineFamily | PRODUCT_FAMILY_OF | BusinessUnit | 3 | DERIVED |
| PartCatalogProfile | PROFILES_PART | Part | 100 | SYNTHETIC_DEMO |
| OrderStatusEvent | RECORDS_STATUS | OrderStatus | 32 | SYNTHETIC_DEMO |
| CartLine | REFERENCES_PART | Part | 6 | SYNTHETIC_DEMO |
| OrderLine | REFERENCES_PART | Part | 14 | SYNTHETIC_DEMO |
| Part | RELATED_COMPONENT | Part | 2 | DERIVED |
| ServicePlan | REQUIRES_PART | Part | 71 | SYNTHETIC_DEMO |
| Part | SAME_NAME_GROUP_AS | Part | 9 | DERIVED |
| Dealer | SERVES_FAMILY | MachineFamily | 30 | SYNTHETIC_DEMO |
| Shipment | SHIPS_LINE | OrderLine | 9 | SYNTHETIC_DEMO |
| Warehouse | SHIPS_TO_COUNTRY | Location | 8 | SYNTHETIC_DEMO |
| Part | STOCKED_BY | Dealer | 315 | SYNTHETIC_DEMO |
| Category | SUBCATEGORY_OF | Category | 91 | DERIVED |
| Part | SUPPLIED_BY | Supplier | 157 | SYNTHETIC_DEMO |
| Supplier | SUPPLIES_CATEGORY | Category | 25 | SYNTHETIC_DEMO |
| DeliveryEstimate | TO_CUSTOMER | Customer | 40 | SYNTHETIC_DEMO |
| DeliveryEstimate | TO_DEALER | Dealer | 60 | SYNTHETIC_DEMO |
| MachineVariant | VARIANT_OF | Machine | 30 | SYNTHETIC_DEMO |
