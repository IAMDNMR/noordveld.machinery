# Parts Intelligence graph schema

38 node labels, 61 relationship types, 1840 nodes, 3812 relationships.

## Node labels

| label | canonical_id | nodes | provenance | meaning |
|---|---|---|---|---|
| Address | address_id | 44 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Assembly | assembly_id | 15 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| BusinessUnit | business_unit_id | 3 | SOURCE_DERIVED | Noordveld and its legacy businesses. |
| Carrier | carrier_id | 1 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Cart | cart_id | 3 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| CartLine | cart_line_id | 6 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Category | category_id | 101 | SOURCE_DERIVED / DERIVED | Level 1: catalogue category (source). Level 2: name-head sub-category (derived). |
| ComplianceRequirement | compliance_id | 8 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Customer | customer_id | 10 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| DataSource | source_id | 4 | SYNTHETIC_DEMO / USER_PROVIDED | A provenance source the workbook declares (plus the project brief it cites). |
| Dealer | dealer_id | 15 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| DeliveryEstimate | delivery_estimate_id | 100 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| IdentificationRequirement | requirement_id | 6 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| LegacyReference | legacy_reference_id | 100 | SOURCE_DERIVED | A previous part number of the same part, or an unresolved free-text note. |
| Location | location_id | 5 | SOURCE_DERIVED | Catalogue country / city locations. |
| Machine | machine_id | 15 | SOURCE_DERIVED | A machine MODEL from the catalogue (one row per model). Not a serial-numbered unit; units do not exist in the data. |
| MachineFamily | family_id | 3 | DERIVED | Family derived from the model-code prefix. Needs business confirmation. |
| MachineSpecification | machine_spec_id | 83 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| MachineType | machine_type_id | 15 | SOURCE_DERIVED | Catalogue machine type. |
| MachineVariant | variant_id | 30 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Order | order_id | 8 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| OrderLine | order_line_id | 14 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| OrderStatus | order_status_code | 6 | USER_PROVIDED | Workflow status vocabulary from the brief. |
| OrderStatusEvent | status_event_id | 32 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Part | part_id | 100 | SOURCE_DERIVED | A catalogue part (unified part number). |
| PartCatalogProfile | profile_id | 100 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| PartSpecification | specification_id | 279 | SOURCE_DERIVED / DERIVED | Verbatim spec note or a value parsed from it. |
| Plant | plant_id | 3 | USER_PROVIDED | A plant declared fictional by the project brief. |
| Price | price_id | 100 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Region | region_id | 14 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| SearchAlias | alias_id | 493 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| ServicePlan | service_plan_id | 60 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Shipment | shipment_id | 9 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| ShippingRate | rate_id | 8 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Supplier | supplier_id | 12 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| SupplierBackorder | backorder_id | 4 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| TrackingEvent | tracking_event_id | 27 | SYNTHETIC_DEMO | Synthetic demonstration entity. |
| Warehouse | warehouse_id | 4 | SYNTHETIC_DEMO | Synthetic demonstration entity. |

Every node also carries the provenance properties (provenance_type, data_status, source_id, source_file, source_sheet, source_record_id, source_name, source_ref, confidence, authoritative_flag, last_updated). Nodes whose canonical id differs from the
workbook column keep the workbook value in `source_id_value`.

## Relationships

| direction | cardinality | count | provenance | synthetic_allowed |
|---|---|---|---|---|
| (Part)-[:FITS]->(Machine) | N:M | 219 | SOURCE_DERIVED | NO |
| (Machine)-[:MANUFACTURED_AT]->(Plant) | N:1 (exactly one per machine) | 15 | SOURCE_DERIVED | NO |
| (Machine)-[:OF_TYPE]->(MachineType) | N:1 (exactly one per machine) | 15 | SOURCE_DERIVED | NO |
| (Machine)-[:MEMBER_OF_FAMILY]->(MachineFamily) | N:1 | 15 | DERIVED | NO |
| (Machine)-[:BRANDED_AS]->(BusinessUnit) | N:1 | 15 | SOURCE_DERIVED | NO |
| (MachineFamily)-[:PRODUCT_FAMILY_OF]->(BusinessUnit) | N:1 | 3 | DERIVED | NO |
| (Plant)-[:OWNED_BY]->(BusinessUnit) | N:1 | 3 | USER_PROVIDED | NO |
| (Plant)-[:LOCATED_IN]->(Location) | N:1 | 3 | USER_PROVIDED | NO |
| (Location)-[:IN_COUNTRY]->(Location) | N:1 | 3 | SOURCE_DERIVED | NO |
| (Category)-[:SUBCATEGORY_OF]->(Category) | N:1 | 91 | DERIVED | NO |
| (Part)-[:IN_CATEGORY]->(Category) | N:1 (exactly one per part) | 100 | SOURCE_DERIVED | NO |
| (Part)-[:IN_SUBCATEGORY]->(Category) | N:1 (exactly one per part) | 100 | DERIVED | NO |
| (Part)-[:ORIGINATES_AT]->(Plant) | N:1 (exactly one per part) | 100 | SOURCE_DERIVED | NO |
| (Part)-[:HAS_LEGACY_REFERENCE]->(LegacyReference) | 1:1 | 100 | SOURCE_DERIVED | NO |
| (LegacyReference)-[:ISSUED_BY_BUSINESS_UNIT]->(BusinessUnit) | N:1 | 100 | DERIVED | NO |
| (Part)-[:HAS_SPECIFICATION]->(PartSpecification) | 1:N | 279 | DERIVED/SOURCE_DERIVED | NO |
| (Part)-[:SAME_NAME_GROUP_AS]->(Part) | N:M symmetric | 9 | DERIVED | NO |
| (Part)-[:RELATED_COMPONENT]->(Part) | N:M | 2 | DERIVED | NO |
| (Part)-[:CO_ORDERED_WITH]->(Part) | N:M symmetric | 75 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:SUPPLIED_BY]->(Supplier) | N:M | 157 | SYNTHETIC_DEMO | YES (marked) |
| (SupplierBackorder)-[:PLACED_WITH]->(Supplier) | N:1 | 4 | SYNTHETIC_DEMO | YES (marked) |
| (SupplierBackorder)-[:FOR_PART]->(Part) | N:1 | 4 | SYNTHETIC_DEMO | YES (marked) |
| (IdentificationRequirement)-[:FOR_PART]->(Part) | N:1 | 6 | SYNTHETIC_DEMO | YES (marked) |
| (IdentificationRequirement)-[:FOR_MACHINE]->(Machine) | N:1 | 6 | SYNTHETIC_DEMO | YES (marked) |
| (IdentificationRequirement)-[:ADMITS_VARIANT]->(MachineVariant) | N:M | 10 | SYNTHETIC_DEMO | YES (marked) |
| (ServicePlan)-[:FOR_MACHINE]->(Machine) | N:1 | 60 | SYNTHETIC_DEMO | YES (marked) |
| (ServicePlan)-[:REQUIRES_PART]->(Part) | N:M | 71 | SYNTHETIC_DEMO | YES (marked) |
| (Warehouse)-[:LOCATED_AT_PLANT]->(Plant) | N:1 | 3 | SYNTHETIC_DEMO | YES (marked) |
| (Warehouse)-[:LOCATED_AT_ADDRESS]->(Address) | 1:1 | 4 | SYNTHETIC_DEMO | YES (marked) |
| (Supplier)-[:LOCATED_AT_ADDRESS]->(Address) | 1:1 | 12 | SYNTHETIC_DEMO | YES (marked) |
| (Dealer)-[:LOCATED_AT_ADDRESS]->(Address) | 1:1 | 15 | SYNTHETIC_DEMO | YES (marked) |
| (Customer)-[:LOCATED_AT_ADDRESS]->(Address) | 1:1 | 10 | SYNTHETIC_DEMO | YES (marked) |
| (Plant)-[:LOCATED_AT_ADDRESS]->(Address) | 1:1 | 3 | SYNTHETIC_DEMO | YES (marked) |
| (Address)-[:IN_REGION]->(Region) | N:1 | 44 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:AVAILABLE_AT]->(Warehouse) | N:M | 400 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:STOCKED_BY]->(Dealer) | N:M | 315 | SYNTHETIC_DEMO | YES (marked) |
| (Dealer)-[:SERVES_FAMILY]->(MachineFamily) | N:M | 30 | SYNTHETIC_DEMO | YES (marked) |
| (Price)-[:PRICES_PART]->(Part) | 1:1 | 100 | SYNTHETIC_DEMO | YES (marked) |
| (PartCatalogProfile)-[:PROFILES_PART]->(Part) | 1:1 | 100 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:HAS_COMPLIANCE]->(ComplianceRequirement) | N:M | 100 | SYNTHETIC_DEMO | YES (marked) |
| (Assembly)-[:IDENTIFIED_BY_PART]->(Part) | 1:1 | 15 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:PART_OF]->(Assembly) | N:M | 35 | SYNTHETIC_DEMO | YES (marked) |
| (Machine)-[:HAS_MACHINE_SPECIFICATION]->(MachineSpecification) | 1:N | 83 | SYNTHETIC_DEMO | YES (marked) |
| (MachineVariant)-[:VARIANT_OF]->(Machine) | N:1 | 30 | SYNTHETIC_DEMO | YES (marked) |
| (Cart)-[:OPENED_BY]->(Customer) | N:1 | 3 | SYNTHETIC_DEMO | YES (marked) |
| (Cart)-[:CONTAINS_LINE]->(CartLine) | 1:N | 6 | SYNTHETIC_DEMO | YES (marked) |
| (Order)-[:CONTAINS_LINE]->(OrderLine) | 1:N | 14 | SYNTHETIC_DEMO | YES (marked) |
| (CartLine)-[:REFERENCES_PART]->(Part) | N:1 (exactly one per line) | 6 | SYNTHETIC_DEMO | YES (marked) |
| (OrderLine)-[:REFERENCES_PART]->(Part) | N:1 (exactly one per line) | 14 | SYNTHETIC_DEMO | YES (marked) |
| (Order)-[:ORDERED_BY]->(Customer) | N:1 (exactly one per order) | 8 | SYNTHETIC_DEMO | YES (marked) |
| (Order)-[:DELIVERS_TO_ADDRESS]->(Address) | N:1 | 8 | SYNTHETIC_DEMO | YES (marked) |
| (OrderLine)-[:ALLOCATED_FROM]->(Warehouse) | N:1 | 10 | SYNTHETIC_DEMO | YES (marked) |
| (OrderLine)-[:PLANNED_FULFILMENT_FROM]->(Warehouse) | N:1 | 4 | SYNTHETIC_DEMO | YES (marked) |
| (Order)-[:HAS_STATUS_EVENT]->(OrderStatusEvent) | 1:N | 32 | SYNTHETIC_DEMO | YES (marked) |
| (OrderStatusEvent)-[:RECORDS_STATUS]->(OrderStatus) | N:1 | 32 | SYNTHETIC_DEMO | YES (marked) |
| (Order)-[:HAS_SHIPMENT]->(Shipment) | 1:N | 9 | SYNTHETIC_DEMO | YES (marked) |
| (Shipment)-[:SHIPS_LINE]->(OrderLine) | N:1 | 9 | SYNTHETIC_DEMO | YES (marked) |
| (Shipment)-[:DISPATCHED_FROM]->(Warehouse) | N:1 | 9 | SYNTHETIC_DEMO | YES (marked) |
| (Shipment)-[:DELIVERS_TO_CUSTOMER]->(Customer) | N:1 | 9 | SYNTHETIC_DEMO | YES (marked) |
| (Shipment)-[:CARRIED_BY]->(Carrier) | N:1 | 9 | SYNTHETIC_DEMO | YES (marked) |
| (Shipment)-[:HAS_TRACKING_EVENT]->(TrackingEvent) | 1:N | 27 | SYNTHETIC_DEMO | YES (marked) |
| (DeliveryEstimate)-[:FROM_WAREHOUSE]->(Warehouse) | N:1 | 100 | SYNTHETIC_DEMO | YES (marked) |
| (DeliveryEstimate)-[:TO_CUSTOMER]->(Customer) | N:1 | 40 | SYNTHETIC_DEMO | YES (marked) |
| (DeliveryEstimate)-[:TO_DEALER]->(Dealer) | N:1 | 60 | SYNTHETIC_DEMO | YES (marked) |
| (BusinessUnit)-[:HOME_PLANT]->(Plant) | 1:1 | 3 | SOURCE_DERIVED | NO |
| (Supplier)-[:SUPPLIES_CATEGORY]->(Category) | N:M | 25 | SYNTHETIC_DEMO | YES (marked) |
| (ComplianceRequirement)-[:COVERS_CATEGORY]->(Category) | N:M | 10 | SYNTHETIC_DEMO | YES (marked) |
| (Warehouse)-[:SHIPS_TO_COUNTRY]->(Location) | N:M | 8 | SYNTHETIC_DEMO | YES (marked) |
| (Part)-[:HAS_ALIAS]->(SearchAlias) | 1:N | 448 | SYNTHETIC_DEMO | YES (marked) |
| (Machine)-[:HAS_ALIAS]->(SearchAlias) | 1:N | 45 | SYNTHETIC_DEMO | YES (marked) |

Every relationship carries a deterministic `rel_id` (`TYPE:source_record_id`), its own properties, and the provenance
properties.

## Mapping from the expected model

| expected | in this graph | why |
|---|---|---|
| (:Part)-[:FITS]->(:Machine) | (:Part)-[:FITS]->(:Machine) | As expected. :Machine is a model (no serial units exist). |
| (:Part)-[:BELONGS_TO]->(:Category) | (:Part)-[:IN_CATEGORY]->(:Category) and (:Part)-[:IN_SUBCATEGORY]->(:Category) | Two distinct facts: a source-stated category and a rule-derived sub-category. A single BELONGS_TO would collapse them; BELONGS_TO is also on the generic list. |
| (:Part)-[:PART_OF]->(:Assembly) | (:Part)-[:PART_OF {quantity}]->(:Assembly) | As expected (synthetic BOM). |
| (:Part)-[:SUPPLIED_BY]->(:Supplier) | (:Part)-[:SUPPLIED_BY]->(:Supplier) | As expected (synthetic). |
| (:Part)-[:AVAILABLE_AT]->(:Depot) | (:Part)-[:AVAILABLE_AT {on_hand, reserved, available}]->(:Warehouse) | The workbook calls depots warehouses; the label keeps the source term. |
| (:Part)-[:STOCKED_BY]->(:Dealer) | (:Part)-[:STOCKED_BY {stocking_status, available...}]->(:Dealer) | As expected (synthetic). |
| (:Part)-[:ALTERNATIVE_TO]->(:Part) | not created | MISSING: no authoritative evidence. |
| (:Part)-[:SUPERSEDES]->(:Part) | not created | MISSING: no supersession data. |
| (:Order)-[:ORDERED_BY]->(:Customer) | (:Order)-[:ORDERED_BY]->(:Customer) | As expected. |
| (:Order)-[:CONTAINS]->(:OrderLine) | (:Order)-[:CONTAINS_LINE]->(:OrderLine) | CONTAINS_LINE keeps order lines distinct from other containment. |
| (:OrderLine)-[:REFERENCES_PART]->(:Part) | (:OrderLine)-[:REFERENCES_PART]->(:Part) | As expected. |
| (:Order)-[:HAS_SHIPMENT]->(:Shipment) | (:Order)-[:HAS_SHIPMENT]->(:Shipment) | As expected. |
| (:Shipment)-[:HAS_TRACKING_EVENT]->(:TrackingEvent) | (:Shipment)-[:HAS_TRACKING_EVENT]->(:TrackingEvent) | As expected. |
| (:ServiceJob)-[:FOR_MACHINE]->(:Machine) | (:ServicePlan)-[:FOR_MACHINE]->(:Machine) | Service JOBS are MISSING; the data has service PLANS (interval templates). They are not relabelled as jobs. |
| (:ServiceJob)-[:REQUIRES_PART]->(:Part) | (:ServicePlan)-[:REQUIRES_PART]->(:Part) | As above. |
| FULFILLED_BY | (:OrderLine)-[:ALLOCATED_FROM]->(:Warehouse) / (:OrderLine)-[:PLANNED_FULFILMENT_FROM]->(:Warehouse) | Split by allocation status, so a planned source is never read as an actual allocation. |
| CO_ORDERED_WITH | (:Part)-[:CO_ORDERED_WITH]->(:Part) | Symmetric, stored once; traverse undirected. |

## Supported by the schema, absent in the data (not created)

| relationship | from | to | status |
|---|---|---|---|
| ALTERNATIVE_TO | Part | Part | An authoritative statement that one part can replace another. No such evidence exists. |
| SUPERSEDES | Part | Part | A newer part number replaces an older one. No supersession data exists (legacy references are previous numbers of the SAME part). |
| REPLACEMENT_FOR | Part | Part | No evidence exists. |
| INTERCHANGEABLE_WITH | Part | Part | Never asserted by any source. |
| FOR_MACHINE (ServiceJob) | ServiceJob | Machine | No service jobs exist; only synthetic service plans. |
| REQUIRES_PART (ServiceJob) | ServiceJob | Part | No service jobs exist. |
| INSTALLED_ON | Installation | MachineUnit | No installations or serial-numbered machine units exist. |
| REQUESTED_BY | Request | Customer | No customer requests exist (carts are not requests). |
| HAS_RISK | Part | SourceRisk | No risk data exists. |

## Machine hierarchy

| Level | Status |
|---|---|
| Machine family | DERIVED (model-code prefix) |
| Machine model | SOURCE_DERIVED (`:Machine`) |
| Variant / serial range | SYNTHETIC_DEMO (`:MachineVariant`) |
| Configuration | MISSING |
| Assembly | SYNTHETIC_DEMO (demo BOM) |
| Component → Part | SYNTHETIC_DEMO (`PART_OF`) |
