# Identifier contract

Every node is merged on one canonical id (unique constraint). Names are never identity. No random UUIDs: re-imports are deterministic.

| label | canonical id property | source column | example | stable | synthetic id |
|---|---|---|---|---|---|
| Address | address_id | address_id | ADR-0001 | YES | YES |
| Assembly | assembly_id | assembly_id | ASM-001 | YES | YES |
| BusinessUnit | business_unit_id | business_unit_id | BU-NOORDVELD | YES | NO |
| Carrier | carrier_id | derived from carrier name (CAR-<slug>) | CAR-demo-freight-fictional | YES | YES |
| Cart | cart_id | cart_id | CRT-001 | YES | YES |
| CartLine | cart_line_id | cart_item_id | CIT-001 | YES | YES |
| Category | category_id | category_id | CAT-01 | YES | NO |
| ComplianceRequirement | compliance_id | compliance_id | CMP-01 | YES | YES |
| Customer | customer_id | customer_id | CUS-001 | YES | YES |
| DataSource | source_id | SYN_data_sources.source_id / SRC-BRIEF | SRC-001 | YES | YES |
| Dealer | dealer_id | dealer_id | DLR-001 | YES | YES |
| DeliveryEstimate | delivery_estimate_id | lead_id | DLT-0001 | YES | YES |
| IdentificationRequirement | requirement_id | requirement_id | IDR-001 | YES | YES |
| LegacyReference | legacy_reference_id | mapping_id | LEG-001 | YES | NO |
| Location | location_id | location_id | LOC-DE | YES | NO |
| Machine | machine_id | machine_id | MCH-001 | YES | NO |
| MachineFamily | family_id | family_id | FAM-NV | YES | NO |
| MachineSpecification | machine_spec_id | machine_spec_id | MSP-0001 | YES | YES |
| MachineType | machine_type_id | machine_type_id | MTY-001 | YES | NO |
| MachineVariant | variant_id | variant_id | VAR-001-1 | YES | YES |
| Order | order_id | order_id | ORD-0001 | YES | YES |
| OrderLine | order_line_id | order_item_id | OI-0001 | YES | YES |
| OrderStatus | order_status_code | order_status_code | NEW | YES | NO |
| OrderStatusEvent | status_event_id | history_id | OSH-0001 | YES | YES |
| Part | part_id | part_id | PRT-001 | YES | NO |
| PartCatalogProfile | profile_id | part_id | PCP-PRT-001 | YES | YES |
| PartSpecification | specification_id | specification_id | PSP-0001 | YES | NO |
| Plant | plant_id | plant_id | PLT-001 | YES | NO |
| Price | price_id | price_id | PRC-0001 | YES | YES |
| Region | region_id | region_id | REG-NL-DREN | YES | YES |
| SearchAlias | alias_id | alias_id | ALI-0001 | YES | YES |
| ServicePlan | service_plan_id | service_id | SVC-250-001 | YES | YES |
| Shipment | shipment_id | shipment_id | SHP-0001 | YES | YES |
| ShippingRate | rate_id | rate_id | SHR-01 | YES | YES |
| Supplier | supplier_id | supplier_id | SUP-001 | YES | YES |
| SupplierBackorder | backorder_id | backorder_id | BO-001 | YES | YES |
| TrackingEvent | tracking_event_id | event_id | EVT-0001 | YES | YES |
| Warehouse | warehouse_id | warehouse_id | WH-001 | YES | YES |

## Legacy and alternate identifiers

- Legacy part numbers (`AS-771`, `HK-2291-B`...) live on `:LegacyReference`, never as a Part id.
- `Part.part_number` (unified number, e.g. NVM-1010-HY) is unique but is not the merge key; `part_id` is.
- Search aliases live on `:SearchAlias` nodes.
- Relationships: `rel_id = TYPE:source_record_id` (unique per type, constraint). Symmetric relationships are stored lower
  id → higher id; merged duplicates keep their record ids in `merged_source_record_ids`.
