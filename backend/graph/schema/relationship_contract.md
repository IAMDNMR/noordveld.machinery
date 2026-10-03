# Relationship contract

Inference is never allowed: every relationship is a workbook row. Synthetic relationships are allowed only where stated, and always carry `data_status = SYNTHETIC_DEMO`.

## FITS  `(Part)-[:FITS]->(Machine)`

- **Meaning:** The catalogue states the part fits this machine model. Interchangeability is NOT implied.
- **Cardinality:** N:M
- **Allowed source:** machine_part_fitment
- **Required properties:** rel_id, fitment_status, fitment_type, source_confidence, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## MANUFACTURED_AT  `(Machine)-[:MANUFACTURED_AT]->(Plant)`

- **Meaning:** The machine model is built at this plant (catalogue Plant column).
- **Cardinality:** N:1 (exactly one per machine)
- **Allowed source:** machines
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## OF_TYPE  `(Machine)-[:OF_TYPE]->(MachineType)`

- **Meaning:** The machine model is of this machine type (catalogue Machine Type column).
- **Cardinality:** N:1 (exactly one per machine)
- **Allowed source:** machines
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## MEMBER_OF_FAMILY  `(Machine)-[:MEMBER_OF_FAMILY]->(MachineFamily)`

- **Meaning:** Rule-derived: the model-code prefix places the machine in this family. Needs business confirmation.
- **Cardinality:** N:1
- **Allowed source:** machines
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## BRANDED_AS  `(Machine)-[:BRANDED_AS]->(BusinessUnit)`

- **Meaning:** The machine is sold under this brand / business unit (catalogue Brand / Origin column).
- **Cardinality:** N:1
- **Allowed source:** machines
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PRODUCT_FAMILY_OF  `(MachineFamily)-[:PRODUCT_FAMILY_OF]->(BusinessUnit)`

- **Meaning:** The derived family belongs to this business unit's range.
- **Cardinality:** N:1
- **Allowed source:** machine_families
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## OWNED_BY  `(Plant)-[:OWNED_BY]->(BusinessUnit)`

- **Meaning:** The plant is owned by this business unit (project brief).
- **Cardinality:** N:1
- **Allowed source:** plants
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_IN  `(Plant)-[:LOCATED_IN]->(Location)`

- **Meaning:** The plant is in this catalogue location (city level).
- **Cardinality:** N:1
- **Allowed source:** plants
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## IN_COUNTRY  `(Location)-[:IN_COUNTRY]->(Location)`

- **Meaning:** A city-level location lies in this country-level location.
- **Cardinality:** N:1
- **Allowed source:** locations
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SUBCATEGORY_OF  `(Category)-[:SUBCATEGORY_OF]->(Category)`

- **Meaning:** A rule-derived sub-category (name head) sits under this catalogue category.
- **Cardinality:** N:1
- **Allowed source:** categories
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## IN_CATEGORY  `(Part)-[:IN_CATEGORY]->(Category)`

- **Meaning:** The part's catalogue category (level 1, source-stated).
- **Cardinality:** N:1 (exactly one per part)
- **Allowed source:** parts
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## IN_SUBCATEGORY  `(Part)-[:IN_SUBCATEGORY]->(Category)`

- **Meaning:** The part's rule-derived sub-category (level 2, name head). Not a taxonomy fact until approved.
- **Cardinality:** N:1 (exactly one per part)
- **Allowed source:** parts
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## ORIGINATES_AT  `(Part)-[:ORIGINATES_AT]->(Plant)`

- **Meaning:** The catalogue's Plant of Origin for the part.
- **Cardinality:** N:1 (exactly one per part)
- **Allowed source:** parts
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_LEGACY_REFERENCE  `(Part)-[:HAS_LEGACY_REFERENCE]->(LegacyReference)`

- **Meaning:** The part's previous / legacy part-number record (may be unresolved free text).
- **Cardinality:** 1:1
- **Allowed source:** legacy_part_mapping
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## ISSUED_BY_BUSINESS_UNIT  `(LegacyReference)-[:ISSUED_BY_BUSINESS_UNIT]->(BusinessUnit)`

- **Meaning:** The business whose numbering the legacy code belongs to (mostly rule-derived from prefix and plant).
- **Cardinality:** N:1
- **Allowed source:** legacy_part_mapping
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_SPECIFICATION  `(Part)-[:HAS_SPECIFICATION]->(PartSpecification)`

- **Meaning:** A specification row parsed or copied from the catalogue Spec Note.
- **Cardinality:** 1:N
- **Allowed source:** part_specifications
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SAME_NAME_GROUP_AS  `(Part)-[:SAME_NAME_GROUP_AS]->(Part)`

- **Meaning:** Both parts share a name head in the same category. A naming group only: NOT an alternative, NOT interchangeable. Symmetric, stored once (lower id to higher id).
- **Cardinality:** N:M symmetric
- **Allowed source:** part_relationships
- **Required properties:** rel_id, interchangeability_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## RELATED_COMPONENT  `(Part)-[:RELATED_COMPONENT]->(Part)`

- **Meaning:** The catalogue mentions the other part as a related component. NOT an alternative, NOT interchangeable.
- **Cardinality:** N:M
- **Allowed source:** part_relationships
- **Required properties:** rel_id, interchangeability_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## CO_ORDERED_WITH  `(Part)-[:CO_ORDERED_WITH]->(Part)`

- **Meaning:** Synthetic demo co-purchase signal. NOT engineering advice, NOT interchangeable. Symmetric, stored once (lower id to higher id).
- **Cardinality:** N:M symmetric
- **Allowed source:** SYN_part_relationships
- **Required properties:** rel_id, interchangeability_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SUPPLIED_BY  `(Part)-[:SUPPLIED_BY]->(Supplier)`

- **Meaning:** A synthetic supplier link for the part (cost, lead time, MOQ, primary flag).
- **Cardinality:** N:M
- **Allowed source:** SYN_part_supplier
- **Required properties:** rel_id, is_primary, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PLACED_WITH  `(SupplierBackorder)-[:PLACED_WITH]->(Supplier)`

- **Meaning:** The synthetic backorder is placed with this supplier.
- **Cardinality:** N:1
- **Allowed source:** SYN_supplier_backorders
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## FOR_PART  `(SupplierBackorder)-[:FOR_PART]->(Part)`

- **Meaning:** The synthetic backorder is for this part.
- **Cardinality:** N:1
- **Allowed source:** SYN_supplier_backorders
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## FOR_PART  `(IdentificationRequirement)-[:FOR_PART]->(Part)`

- **Meaning:** The synthetic identification requirement applies to this part.
- **Cardinality:** N:1
- **Allowed source:** SYN_identification_requirements
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## FOR_MACHINE  `(IdentificationRequirement)-[:FOR_MACHINE]->(Machine)`

- **Meaning:** The identification requirement is for this machine model.
- **Cardinality:** N:1
- **Allowed source:** SYN_identification_requirements
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## ADMITS_VARIANT  `(IdentificationRequirement)-[:ADMITS_VARIANT]->(MachineVariant)`

- **Meaning:** Synthetic: the variant/serial range the requirement lists as acceptable. Does NOT add catalogue fitment.
- **Cardinality:** N:M
- **Allowed source:** SYN_identification_requirements
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## FOR_MACHINE  `(ServicePlan)-[:FOR_MACHINE]->(Machine)`

- **Meaning:** The synthetic service plan (interval template) is for this machine model. A plan is NOT a service job.
- **Cardinality:** N:1
- **Allowed source:** SYN_services
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## REQUIRES_PART  `(ServicePlan)-[:REQUIRES_PART]->(Part)`

- **Meaning:** The synthetic service plan uses this part (quantity).
- **Cardinality:** N:M
- **Allowed source:** SYN_service_parts
- **Required properties:** rel_id, quantity, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_PLANT  `(Warehouse)-[:LOCATED_AT_PLANT]->(Plant)`

- **Meaning:** The synthetic warehouse is attached to this plant.
- **Cardinality:** N:1
- **Allowed source:** SYN_warehouses
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_ADDRESS  `(Warehouse)-[:LOCATED_AT_ADDRESS]->(Address)`

- **Meaning:** The synthetic placeholder address of the warehouse.
- **Cardinality:** 1:1
- **Allowed source:** SYN_warehouses
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_ADDRESS  `(Supplier)-[:LOCATED_AT_ADDRESS]->(Address)`

- **Meaning:** The synthetic placeholder address of the supplier.
- **Cardinality:** 1:1
- **Allowed source:** SYN_suppliers
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_ADDRESS  `(Dealer)-[:LOCATED_AT_ADDRESS]->(Address)`

- **Meaning:** The synthetic placeholder address of the dealer.
- **Cardinality:** 1:1
- **Allowed source:** SYN_dealers
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_ADDRESS  `(Customer)-[:LOCATED_AT_ADDRESS]->(Address)`

- **Meaning:** The synthetic placeholder address of the customer.
- **Cardinality:** 1:1
- **Allowed source:** SYN_customers
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## LOCATED_AT_ADDRESS  `(Plant)-[:LOCATED_AT_ADDRESS]->(Address)`

- **Meaning:** The synthetic placeholder address of the (fictional) plant.
- **Cardinality:** 1:1
- **Allowed source:** SYN_addresses
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## IN_REGION  `(Address)-[:IN_REGION]->(Region)`

- **Meaning:** The address lies in this synthetic region (VAT rate reference).
- **Cardinality:** N:1
- **Allowed source:** SYN_addresses
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## AVAILABLE_AT  `(Part)-[:AVAILABLE_AT]->(Warehouse)`

- **Meaning:** Synthetic warehouse stock of the part (on_hand, reserved, available, stock_status). 0 here is an explicit warehouse record.
- **Cardinality:** N:M
- **Allowed source:** SYN_inventory
- **Required properties:** rel_id, on_hand, reserved, available, stock_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## STOCKED_BY  `(Part)-[:STOCKED_BY]->(Dealer)`

- **Meaning:** Synthetic: the dealer is listed as stocking the part (SYN_part_dealer), with its quantities (SYN_inventory).
- **Cardinality:** N:M
- **Allowed source:** SYN_part_dealer
- **Required properties:** rel_id, stocking_status, inventory_id, available, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SERVES_FAMILY  `(Dealer)-[:SERVES_FAMILY]->(MachineFamily)`

- **Meaning:** Synthetic: the dealer serves this machine family. Does NOT mean the dealer supports every model or stocks every part.
- **Cardinality:** N:M
- **Allowed source:** SYN_dealers
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PRICES_PART  `(Price)-[:PRICES_PART]->(Part)`

- **Meaning:** The synthetic demo list price of the part (EUR, ex VAT).
- **Cardinality:** 1:1
- **Allowed source:** SYN_pricing
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PROFILES_PART  `(PartCatalogProfile)-[:PROFILES_PART]->(Part)`

- **Meaning:** The synthetic store profile of the part (status, orderable, weight, warranty...). Kept apart so source facts are never overwritten.
- **Cardinality:** 1:1
- **Allowed source:** SYN_part_catalog
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_COMPLIANCE  `(Part)-[:HAS_COMPLIANCE]->(ComplianceRequirement)`

- **Meaning:** A synthetic compliance record applies to the part.
- **Cardinality:** N:M
- **Allowed source:** SYN_part_compliance
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## IDENTIFIED_BY_PART  `(Assembly)-[:IDENTIFIED_BY_PART]->(Part)`

- **Meaning:** The synthetic assembly (demo BOM) is sold as this part number.
- **Cardinality:** 1:1
- **Allowed source:** SYN_assembly_master
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PART_OF  `(Part)-[:PART_OF]->(Assembly)`

- **Meaning:** Synthetic demo BOM: the part is a component of the assembly (quantity).
- **Cardinality:** N:M
- **Allowed source:** SYN_assembly_components
- **Required properties:** rel_id, quantity, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_MACHINE_SPECIFICATION  `(Machine)-[:HAS_MACHINE_SPECIFICATION]->(MachineSpecification)`

- **Meaning:** A synthetic machine specification. Not engineering data.
- **Cardinality:** 1:N
- **Allowed source:** SYN_machine_specifications
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## VARIANT_OF  `(MachineVariant)-[:VARIANT_OF]->(Machine)`

- **Meaning:** A synthetic variant / serial range of the machine model.
- **Cardinality:** N:1
- **Allowed source:** SYN_machine_variants
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## OPENED_BY  `(Cart)-[:OPENED_BY]->(Customer)`

- **Meaning:** The synthetic cart belongs to this customer. A cart is NOT a request.
- **Cardinality:** N:1
- **Allowed source:** SYN_carts
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## CONTAINS_LINE  `(Cart)-[:CONTAINS_LINE]->(CartLine)`

- **Meaning:** The cart contains this line.
- **Cardinality:** 1:N
- **Allowed source:** SYN_cart_items
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## CONTAINS_LINE  `(Order)-[:CONTAINS_LINE]->(OrderLine)`

- **Meaning:** The order contains this line.
- **Cardinality:** 1:N
- **Allowed source:** SYN_order_items
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## REFERENCES_PART  `(CartLine)-[:REFERENCES_PART]->(Part)`

- **Meaning:** The cart line is for this part.
- **Cardinality:** N:1 (exactly one per line)
- **Allowed source:** SYN_cart_items
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## REFERENCES_PART  `(OrderLine)-[:REFERENCES_PART]->(Part)`

- **Meaning:** The order line is for this part.
- **Cardinality:** N:1 (exactly one per line)
- **Allowed source:** SYN_order_items
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## ORDERED_BY  `(Order)-[:ORDERED_BY]->(Customer)`

- **Meaning:** The synthetic order was placed by this customer.
- **Cardinality:** N:1 (exactly one per order)
- **Allowed source:** SYN_orders
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## DELIVERS_TO_ADDRESS  `(Order)-[:DELIVERS_TO_ADDRESS]->(Address)`

- **Meaning:** The order's delivery address.
- **Cardinality:** N:1
- **Allowed source:** SYN_orders
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## ALLOCATED_FROM  `(OrderLine)-[:ALLOCATED_FROM]->(Warehouse)`

- **Meaning:** Stock for the line is reserved at, or was shipped from, this warehouse (allocation_status RESERVED or SHIPPED).
- **Cardinality:** N:1
- **Allowed source:** SYN_order_items
- **Required properties:** rel_id, allocation_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## PLANNED_FULFILMENT_FROM  `(OrderLine)-[:PLANNED_FULFILMENT_FROM]->(Warehouse)`

- **Meaning:** The line is NOT yet allocated; this is only its planned fulfilment location.
- **Cardinality:** N:1
- **Allowed source:** SYN_order_items
- **Required properties:** rel_id, allocation_status, provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_STATUS_EVENT  `(Order)-[:HAS_STATUS_EVENT]->(OrderStatusEvent)`

- **Meaning:** A step in the order's synthetic status history.
- **Cardinality:** 1:N
- **Allowed source:** SYN_order_status_history
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## RECORDS_STATUS  `(OrderStatusEvent)-[:RECORDS_STATUS]->(OrderStatus)`

- **Meaning:** The status the history step records (workflow vocabulary).
- **Cardinality:** N:1
- **Allowed source:** SYN_order_status_history
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_SHIPMENT  `(Order)-[:HAS_SHIPMENT]->(Shipment)`

- **Meaning:** The order has this synthetic shipment.
- **Cardinality:** 1:N
- **Allowed source:** SYN_shipments
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SHIPS_LINE  `(Shipment)-[:SHIPS_LINE]->(OrderLine)`

- **Meaning:** The shipment carries this order line.
- **Cardinality:** N:1
- **Allowed source:** SYN_shipments
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## DISPATCHED_FROM  `(Shipment)-[:DISPATCHED_FROM]->(Warehouse)`

- **Meaning:** The shipment left this warehouse.
- **Cardinality:** N:1
- **Allowed source:** SYN_shipments
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## DELIVERS_TO_CUSTOMER  `(Shipment)-[:DELIVERS_TO_CUSTOMER]->(Customer)`

- **Meaning:** The shipment is addressed to this customer.
- **Cardinality:** N:1
- **Allowed source:** SYN_shipments
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## CARRIED_BY  `(Shipment)-[:CARRIED_BY]->(Carrier)`

- **Meaning:** The (fictional) carrier of the shipment.
- **Cardinality:** N:1
- **Allowed source:** SYN_shipments
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_TRACKING_EVENT  `(Shipment)-[:HAS_TRACKING_EVENT]->(TrackingEvent)`

- **Meaning:** A synthetic tracking event of the shipment.
- **Cardinality:** 1:N
- **Allowed source:** SYN_shipment_events
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## FROM_WAREHOUSE  `(DeliveryEstimate)-[:FROM_WAREHOUSE]->(Warehouse)`

- **Meaning:** The synthetic delivery estimate starts at this warehouse.
- **Cardinality:** N:1
- **Allowed source:** SYN_delivery_options
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## TO_CUSTOMER  `(DeliveryEstimate)-[:TO_CUSTOMER]->(Customer)`

- **Meaning:** The estimate's destination is this customer.
- **Cardinality:** N:1
- **Allowed source:** SYN_delivery_options
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## TO_DEALER  `(DeliveryEstimate)-[:TO_DEALER]->(Dealer)`

- **Meaning:** The estimate's destination is this dealer.
- **Cardinality:** N:1
- **Allowed source:** SYN_delivery_options
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HOME_PLANT  `(BusinessUnit)-[:HOME_PLANT]->(Plant)`

- **Meaning:** The plant the project brief names as the business unit's home plant.
- **Cardinality:** 1:1
- **Allowed source:** business_units
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** NO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SUPPLIES_CATEGORY  `(Supplier)-[:SUPPLIES_CATEGORY]->(Category)`

- **Meaning:** Synthetic: the supplier's declared category scope. NOT a supply relationship for any specific part (SUPPLIED_BY is the only part-level link).
- **Cardinality:** N:M
- **Allowed source:** SYN_suppliers
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## COVERS_CATEGORY  `(ComplianceRequirement)-[:COVERS_CATEGORY]->(Category)`

- **Meaning:** Synthetic: the compliance requirement's declared category scope. NOT a part-level statement (HAS_COMPLIANCE is).
- **Cardinality:** N:M
- **Allowed source:** SYN_compliance
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## SHIPS_TO_COUNTRY  `(Warehouse)-[:SHIPS_TO_COUNTRY]->(Location)`

- **Meaning:** Synthetic: the warehouse ships to this country. Not a delivery estimate (DeliveryEstimate is).
- **Cardinality:** N:M
- **Allowed source:** SYN_warehouses
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_ALIAS  `(Part)-[:HAS_ALIAS]->(SearchAlias)`

- **Meaning:** A synthetic search alias / synonym of the part.
- **Cardinality:** 1:N
- **Allowed source:** SYN_search_aliases
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## HAS_ALIAS  `(Machine)-[:HAS_ALIAS]->(SearchAlias)`

- **Meaning:** A synthetic search alias of the machine model.
- **Cardinality:** 1:N
- **Allowed source:** SYN_search_aliases
- **Required properties:** rel_id, (provenance only), provenance properties
- **Provenance required:** YES
- **Synthetic allowed:** YES, only explicitly marked SYNTHETIC_DEMO
- **Inference allowed:** NO
- **Interchangeability:** NOT IMPLIED

## Never created without authoritative evidence

- `ALTERNATIVE_TO` (Part → Part): An authoritative statement that one part can replace another. No such evidence exists.
- `SUPERSEDES` (Part → Part): A newer part number replaces an older one. No supersession data exists (legacy references are previous numbers of the SAME part).
- `REPLACEMENT_FOR` (Part → Part): No evidence exists.
- `INTERCHANGEABLE_WITH` (Part → Part): Never asserted by any source.
- `FOR_MACHINE (ServiceJob)` (ServiceJob → Machine): No service jobs exist; only synthetic service plans.
- `REQUIRES_PART (ServiceJob)` (ServiceJob → Part): No service jobs exist.
- `INSTALLED_ON` (Installation → MachineUnit): No installations or serial-numbered machine units exist.
- `REQUESTED_BY` (Request → Customer): No customer requests exist (carts are not requests).
- `HAS_RISK` (Part → SourceRisk): No risk data exists.

## Forbidden generic types

ALTERNATIVE_TO, ASSOCIATED_WITH, BELONGS_TO, CONNECTED_TO, HAS, INTERCHANGEABLE, INTERCHANGEABLE_WITH, LINKED_TO, RELATED_TO, REPLACEMENT_FOR, SUPERSEDED_BY, SUPERSEDES
