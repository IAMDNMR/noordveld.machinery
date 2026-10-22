# Catalog correction status — 19 October 2026

92 of the original 132 catalog findings are corrected: 81 task field scopes and 11 task permissions. The original graph versions remain; corrected versions are additive. All 18 active packs and their current assessment hashes were read back from Neo4j. Graph now holds 37 versions (34 reference, 3 domain).

Icons in the Studio application navigation, task cards, and task headings now use task meaning. The generated runtime also includes semantic SVG task icons. Repeated task meanings can appropriately reuse an icon.

53 backend tests and 6 frontend tests pass; the frontend build passes. Backend tests include screen generation across every pack, owner-aware task field contracts, generated runtime behavior, permissions, and existing engineering checks.

The separately checked legacy domain-discovery test still expects a company pack to be auto-selected without the company being named. Current eligibility deliberately excludes that. This discrepancy was not hidden by weakening company isolation.

Existing projects are not silently overwritten when reference versions change. New adoption uses corrected packs; prior project edits and approvals are preserved. Existing projects need an explicit knowledge-update/reconciliation step to take on the new definitions.

## Remaining findings — not marked resolved

All 40 remaining findings below stay visible. 26 rules, 3 prose conditions, and 5 tasks without authorization are in the two legacy Noordveld packs. Six integrations span four packs. They require further implementation; integration providers and API locations have been requested.

| Pack | Item | Finding | Required work |
| --- | --- | --- | --- |
| cap_documents | int_doc_storage | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
| cat_transport | int_tms_tracking_feed | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
| noordveld_spare_parts | rule_part_orderable | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_identification | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_fitment | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_details_valid | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_dealer_can_install | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_availability | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_idempotent | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_cost_not_available | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_allocation | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_allocation_concurrency | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_allocation_recovery | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_action_status | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_shipment_outcome | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_tracking_sequence | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_dealer_service | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_warranty_outcome | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | rule_warranty_review | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_spare_parts | order_review | PROSE_CONDITION | Needs executable pre/postconditions and the related transactional side effect, not text interpreted as code. |
| noordveld_spare_parts | order_allocate | PROSE_CONDITION | Needs executable pre/postconditions and the related transactional side effect, not text interpreted as code. |
| noordveld_spare_parts | order_allocate | TASK_ACCESS_INCOMPLETE | No existing role permission authorizes this task. Platform automation or dealer/reviewer identity and its policy must be defined. |
| noordveld_spare_parts | order_ship | PROSE_CONDITION | Needs executable pre/postconditions and the related transactional side effect, not text interpreted as code. |
| noordveld_spare_parts | claim_submit | TASK_ACCESS_INCOMPLETE | No existing role permission authorizes this task. Platform automation or dealer/reviewer identity and its policy must be defined. |
| noordveld_spare_parts | claim_review | TASK_ACCESS_INCOMPLETE | No existing role permission authorizes this task. Platform automation or dealer/reviewer identity and its policy must be defined. |
| noordveld_spare_parts | claim_missing_evidence | TASK_ACCESS_INCOMPLETE | No existing role permission authorizes this task. Platform automation or dealer/reviewer identity and its policy must be defined. |
| noordveld_spare_parts | int_catalogue_graph | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
| noordveld_spare_parts | int_order_records | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
| noordveld_spare_parts | int_tracking | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
| noordveld_transport | rule_availability | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_allocation | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_carrier_eligibility | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_capacity_check | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_handoff_complete | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_goods_ready | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_delivery_outcome | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_pod_required | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | rule_tracking_sequence | RULE_NOT_EXECUTABLE | Needs an explicit implementation of the documented business predicate; assigning a constant result would change its meaning. |
| noordveld_transport | wh_allocate | TASK_ACCESS_INCOMPLETE | No existing role permission authorizes this task. Platform automation or dealer/reviewer identity and its policy must be defined. |
| noordveld_transport | int_carrier_tracking | INTEGRATION_NOT_IMPLEMENTED | Needs a real service adapter, provider/API configuration, and integration verification. |
