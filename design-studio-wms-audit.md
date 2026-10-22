# Design Studio audit: new WMS project, 2026-10-22

Project: **Warehouse Management System**, `app_a2eab736-933d-4ea9-84b2-1fbe3a6d33ca` (local Studio API on 8022, knowledge from Neo4j).
An earlier attempt, `app_30c33297-24cb-4f35-8bf7-1356c4c1d6bb`, was built before the knowledge fix below; it is kept unchanged and can be deleted.

Marks: **OK** correct · **WRONG** incorrect, should change · **NOT NEEDED** should be removed · **GAP** missing, no verified source · **FIXED** fixed in this run.

## Environment

| Item | Mark | Notes |
|---|---|---|
| Studio API restart (8022) | OK | Restarted with the same local storage and Neo4j settings; the 3 existing projects are intact. A second Studio server on 8000 (not started by me) was left alone. |
| `GET /design-studio/project-dashboard` | WRONG | Takes ~8 s and the overview page requests it 4 times at once; the page shows "Loading your workspace…" meanwhile. |
| `GET /api/v1/me`, `/api/v1/site/overview` on Studio pages | NOT NEEDED | Website calls fire on Studio pages and fail (502/401) in the console. |

## Stage 1: Requirements

| Item | Mark | Notes |
|---|---|---|
| 10 requirements (receive, putaway, pick, pack, ship, cycle count/adjust, replenish, supervise exceptions, returns, reports) | OK | Match the brief. |
| 7 user types | OK | Match the brief. |
| "Shipping staff … assign carriers, and generate shipping documents" | GAP | No verified knowledge or integration for carriers or shipping documents. Needs a partner integration or a decision. |
| "Operational reports show receiving efficiency, putaway accuracy, pick/pack/ship rates…" | GAP | No verified KPI definitions; the metrics are unspecified. |
| 7 generic open questions (security, audit, accessibility, performance, records, systems, constraints) | NOT NEEDED | Generic checklist, not specific to this request. |
| Region / industry setup | OK | Both saved (EU, manufacturing). The selects are disabled while one saves. |

## Stage 2: Domain Knowledge

| Item | Mark | Notes |
|---|---|---|
| Only one verified pack offered/adopted for a WMS | FIXED | Root cause: once the project had a domain, the assistant (`studio_agent.build_context`) and the stage page (`studio_conversation` focus) only offered that one domain's packs, and the prompt said "adopt ONE pack". Stock control (`cat_stock_control`) was never offered, so the model invented count/reorder processes. Fix: `planning.reference_domains()` adds every other matched domain whose verified packs cover the request by the same test `plan_application` uses; the prompt now says one `adopt_pack` per covering pack. Regression test: `test_project_domain_does_not_hide_other_verified_knowledge_it_needs`. |
| Adopted packs: `cat_warehouse_fulfilment`, `cat_stock_control` (both 2026.10.22, verified) | OK | 6 verified processes, 6 confirmed rules. |
| Two "Item" entities (`ent_stk_item`, `ent_whs_item`) and two "Warehouse" entities (`ent_stk_warehouse`, `ent_whs_warehouse`) | WRONG | Each pack defines its own Item and Warehouse; `apply_pack` copies both. Proposed fix: when adopting a pack whose entity has the same name and documented source as an adopted one, map it onto the existing entity (union of attributes, rewire relationships, step reads/writes and rule bindings), as `deduplication.reconcile` does for requirements. Not done: needs a reviewed merge rule. |
| `wf_run_cycle_count` "Run cycle count" | NOT NEEDED | Duplicates verified `wf_stk_count` "Stock count". |
| `wf_automatic_replenishment` "Automatic replenishment" | NOT NEEDED | Overlaps verified `wf_stk_reorder` "Automatic reorder" (material request below reorder level). |
| `wf_process_return` "Process return" | NOT NEEDED | Duplicates verified `wf_whs_return` "Sales return". |
| `wf_operational_reporting` "Operational reporting" | NOT NEEDED | Reporting is screens over existing records, not a process with steps. |
| `wf_pack_picked_items`, `wf_create_shipment` | GAP | Needed by the requirements but not in any verified pack; model-drafted. |
| `ent_cycle_count`, `ent_cycle_count_line` | NOT NEEDED | Duplicate verified `ent_stk_count_line`. |
| `ent_replenishment_request` | NOT NEEDED | Duplicates verified `ent_stk_request` "Material request". |
| `ent_return_inspection` | GAP | Supports the "returns are inspected" requirement; no verified source. |
| Roles `role_stk_counter` vs `role_inventory_controller`; `role_stk_manager`, `role_whs_manager`, `role_warehouse_supervisor` | WRONG | Overlapping roles from two packs plus the brief; should be mapped to one set. |
| `role_system` "System" | NOT NEEDED | Automation is not a business role. |
| `exc_cycle_count_difference_exceeds_threshold` | WRONG | Implies a variance threshold no verified source defines (invented policy). |
| Page text "Nothing is copied into the project" | WRONG | Adopting a pack does copy its processes, records and rules into the project. |
| Assistant message "There is no process step called st_wf_run_cycle_count_…" | WRONG | Internal IDs shown to the person; the model referenced steps it had not created. |
| Chips "Allocation, Picking, Packing, Handoff" | WRONG | From the unverified `cat_warehouse` domain description, not from the adopted packs. |

## Stage 3: Business Process

12 processes; every step is reachable from its start, every step role exists, every process has an end.

| Item | Mark | Notes |
|---|---|---|
| 6 verified processes (reorder, stock count, transfer, receive and put away, pick and deliver, sales return) | OK | Unchanged from the packs. |
| Stage page scrolled sideways with many processes; "Looks good, continue" cut off | FIXED | `.sw-center__body > *` had no `min-width: 0`, so a 12-tab row widened the whole stage. Children now shrink and `.sw-tabs` scrolls in its own row (`StudioWorkspacePage.css`). |
| Duplicate trailing steps in model-added processes: "Enter counted quantities" after the end in Run cycle count, "Check stock levels and create replenishment requests" ×2, "Receive and inspect returned items" ×2, "View operational dashboard" ×2 | WRONG | The stage turn inserted steps again into processes that already had them. These processes are NOT NEEDED anyway (see Stage 2). |
| `wf_pack_picked_items` and `wf_create_shipment` | WRONG | Not connected to `wf_whs_pick_deliver`. In practice packing sits between "Submit the pick list" and "Create and submit the delivery note"; here they are separate processes with no link. |
| `wf_create_shipment` "Assign carrier", "Generate shipping labels", "Handover to carrier" | GAP | Need a carrier integration (partner); no verified source. |
| Stock adjustment approval | GAP | The requirement says controllers approve adjustments; the verified stock count lets the counter submit the reconciliation without approval. Needs a business decision; the model's own approval step lives in the NOT NEEDED duplicate process. |
| `role_system` as the role of replenishment steps | NOT NEEDED | Automatic steps should not need a business role. |
| Warnings ESCALATION_NO_AUTHORITY on `exc_stk_auto_failed`, `exc_whs_no_space` | OK | Correct warnings from the verified packs; who handles them is a business decision. |
| 10 × REQ_DRAFT warnings | OK | Requirements are still drafts; expected until approval. |

## Stage 4: Data Model

21 entities; every entity a process step reads or writes exists. The ER diagram renders correctly.

| Item | Mark | Notes |
|---|---|---|
| Verified pack entities (item, warehouse, material request, count line, transfer, receipt/line, pick list/line, delivery/line) | OK | Pack attributes intact. |
| Fields the model added to pack entities (item weight, dimensions, storage type, hazardous; warehouse capacity, putaway priority, address, zone, temperature; receipt supplier, PO reference, carrier; pick list priority, assigned picker; delivery customer, address, carrier, tracking) | OK | Reasonable warehouse fields; unverified, but no policy. |
| Duplicate Item / Warehouse entities | WRONG | See Stage 2. Model-added entities point at `ent_stk_item`, pack entities at `ent_whs_item`. |
| No storage location / bin entity | GAP | Locations are text (`assigned_location`, `source_location`, warehouse `zone`). Zone/bin management and putaway-to-bin cannot be screens of their own. No verified pack defines bins. |
| No stock balance (on hand per item and location) | GAP | Inventory lookup and availability have no record to read; only `projected_quantity` on Item. |
| No stock ledger entry entity | GAP | The verified requirement "record every movement in the stock ledger" has no record type; movement history cannot be shown. |
| `ent_replenishment_request.item`, `from_warehouse`, `to_warehouse`; `ent_cycle_count_line.item`; `ent_return_inspection.delivery_note`, `item` | WRONG | Text fields duplicating relationships the same entities already have. |
| `ent_shipment` relationship to itself (one-to-many) | WRONG | Self-relationship with no meaning. |
| Status fields of model-added entities (`ent_packing_slip.status`, `ent_shipment.status`, `ent_cycle_count.status`, `ent_replenishment_request.status`) | WRONG | No allowed values, so boards and filters cannot group by them and any text is accepted. |
| Key style: packs use integer `*_no`, model entities use text `number` | WRONG | Inconsistent identifiers in one application. |
| Customer, supplier, sales order, purchase order as text references | OK | Records owned by other systems (ERP); no integration is connected. |
| `ent_cycle_count`, `ent_cycle_count_line`, `ent_replenishment_request` | NOT NEEDED | Duplicates (see Stage 2). |

## Stage 5: Screens & UI (in progress)

Screen inventory of the schema-driven client for this project: Overview, My tasks, Reports (added), 12 process pages (board/list), 21 record lists with add/edit forms, a step page per process instance.

| Item | Mark | Notes |
|---|---|---|
| Stage blocked: "Generate the application's own interface here. Continue unlocks once it has been built" | FIXED | `guided.ready("screen")` required a model-generated interface; it now accepts the schema-driven screens when the project has processes and records (a generated interface, if any, must still be current). |
| Stage page blank for ~10 s with no loading indicator | WRONG | Structure and preview load silently. |
| Every process page is the same template ("PROCESS", name, "0 in progress · 0 finished", Board/List, "Nothing here yet"); only the title differs | WRONG | User feedback. Shared client defect: process pages are not shaped by what the process does (its first form, approvals, lookups, exceptions). Redesign pending confirmation. |
| Flat navigation: 12 processes + 21 record types as one long list; nav label, page eyebrow and heading repeat the same words | WRONG | User feedback. Needs grouping into work areas and records shown where they are used. |
| Line records (receipt, pick, delivery, packing, shipment, count lines) as top-level screens | WRONG | Should live inside their parent document. |
| Documents did not show their lines; no "Add line" from the parent | FIXED | Record pages now list related records (from the relationships) with "Add …" pre-linked to the parent; saving returns to the parent. |
| No reports screen | FIXED | Reports page: work by process step and records by status values, from real data only. |
| Relationship fields labelled with internal IDs ("rel whs rline receipt") | FIXED | Named after the relationship ("Goods receipt", "Item", "Warehouse"). |
| Preview left system-generated keys empty ("—"), so titles repeated the name ("Assen central · Assen central") | FIXED | Preview assigns keys as the server does. |
| "Revision" column in every list | NOT NEEDED | Technical value shown to operators. |
| "Putaway result" typed by hand on Goods receipt | WRONG | Pack data marks a rule outcome as user-entered; should be set by the putaway step. |
| Duplicate "Item" and "Warehouse" nav entries | WRONG | From the duplicate entities (Stage 2). |
| Create, required-field validation, number input, enum selects, search, status filter, edit with revision, cancel, back | OK | Tested on Warehouse, Item, Goods receipt, Receipt line in the preview. |
| No template applied | WRONG | Template choice was removed from Screens; the app uses the default look. |

### Stage 5 rebuild (shared client, every generated app)

| Item | Mark | Notes |
|---|---|---|
| Flat menu of 12 processes + 21 record types | FIXED | Processes sit in collapsible work-area groups with counts. Area names come from the adopted packs' capability (`runtime_generation.work_areas`): WMS → "Stock control" (5), "Warehouse fulfilment" (6), "Other processes" (1); Procurement → "Purchase to receipt"; After-sales → "Warranty and service". A model-drafted process joins the area whose records it uses. Nothing named by hand. |
| Records in the menu | FIXED | Only shared reference data (records three or more record types point at, or that no step writes) stays in the menu; documents are reached from their process; lines live inside their document; "All records" lists everything by area. |
| Identical process pages | FIXED | Each process page is built from its own steps: summary (who starts it, how many steps, how it ends), counts, the first step's form inline (e.g. "Register the goods receipt"), one lane per step with its kind (Enter / Do / Check / Approve / Look up), role, records it changes or uses and work waiting; search steps carry a lookup; exception paths; records the process produces; recently finished. |
| Menu label, eyebrow and heading repeating | FIXED | Eyebrow = area (process and list pages), role (Overview, My work, Reports, All records), document (record pages); title = the page itself. Eyebrows are upper-cased by CSS only. |
| Model generation auto-started on entering Screens | FIXED | `GeneratedFrontendView` started a model job for every new project and replaced the derived screens when it succeeded. It now only follows a running job or shows a failed one; a custom interface is generated on request. |
| Studio preview paints after ~15 s | WRONG | The preview is a nested data-URL iframe; slow to appear. |
| Revision column in lists | FIXED | Removed; the record page still states the revision. |
| Phone width (375 px) | OK | No sideways scroll; menu behind the Menu button; lanes stack. |

## Stage 6: Rules & Logic

| Item | Mark | Notes |
|---|---|---|
| 6 verified rules (`rule_stk_level`, `rule_stk_count`, `rule_stk_created`, `rule_stk_route`, `rule_whs_putaway`, `rule_whs_delivered`) | OK | Confirmed, cited, with executable checks the runtime server evaluates. |
| 8 model-added rules (packing slip only from submitted pick list, packed = picked "within tolerance", shipment from verified slip, carrier availability, replenishment at reorder level, cycle-count "threshold" auto-approval, return dispositions Restock/Repair/Scrap/Vendor Return, reports refresh) | NOT NEEDED | Policy no verified source gives. Correctly marked *assumption* with warnings and not enforced; should become business decisions, not rules. |
| Exceptions `exc_cycle_count_difference_exceeds_threshold`, `exc_packing_quantity_mismatch`, `exc_carrier_assignment_failed` | WRONG | Depend on invented thresholds or a carrier integration. |
| Negative stock prevention | GAP | No stock balance record, so nothing can be checked. |

## Stage 7: Roles & Permissions

| Item | Mark | Notes |
|---|---|---|
| 6 pack roles (stock manager, purchase manager, stock counter, goods receiver, picker, warehouse manager) | OK | Each performs steps of its pack's processes. |
| Packer, Shipping staff, Inventory controller, Warehouse supervisor | OK | From the brief; perform the drafted packing/shipping/count/reporting steps. |
| Receiving clerk, Putaway operator, Picking operator (added in this stage) | NOT NEEDED | No steps (ROLE_UNUSED); duplicate Goods receiver and Picker. |
| Stock counter vs Inventory controller; Stock manager vs Warehouse manager vs Warehouse supervisor | WRONG | Overlapping roles from two packs and the brief, not mapped to one set. |
| `role_system` "System" | NOT NEEDED | Not a business role. |

## Stage 8: Validation

First pass: 0 to fix, 0 decisions, 22 warnings, 24/24 requirements served by a step, 6/14 rules confirmed.

| Item | Mark | Notes |
|---|---|---|
| Automatic design repair rewrites earlier stages and sends the person back | WRONG | User-reported loop, reproduced. On entering Validation the Studio sends a repair request to the model by itself (`ValidationView`). The model added attributes to Item and Warehouse (Data Model content); the stage digests changed, so Data Model, Screens, Rules and Roles lost their "reviewed" mark (revision 21), the flow dropped back to Data Model/Screens and the process approval went stale. Every repair that touches earlier content restarts the journey. |
| Six invented rules marked "confirmed" with fabricated evidence | WRONG, partly FIXED | The repair turn's `confirm_rule` actions recorded sources such as "Confirmed by warehouse supervisor in design review" (no such review happened) and the proposal was applied with no click (14:01:34, before any action on the page; the client path that applied it is not yet identified). Fixed at the server: a model turn can no longer confirm a rule (`studio_conversation._execute` drops `confirm_rule` from non-direct plans with a reason); a person confirms in Rules & Logic. The six rules in this project are still marked confirmed. |
| Repair failed: "A start or end cannot handle an exception", shown twice | WRONG | The model tried an invalid fix for the two ESCALATION_NO_AUTHORITY warnings. |
| "Needs fixing 2" lists two WARNINGS while the card says "Nothing blocks approval" | WRONG | Contradictory labels. |
| "Screen 'New screen' is not linked to a process step" | NOT NEEDED | Placeholder screen left from the blank project template. |
| Process approval by the creator | OK | Local single-user mode allows it; organization mode requires another approver. |
| Design approval text "Generate the screens first" (`ValidationView`) | WRONG | Still assumes a model-generated interface; the derived screens are the interface. |
| Second validation pass | OK | 0 to fix, 0 decisions; process approved at revision 26, design approved at revision 27. |
| Design approval blocked: "Generate the screens first" | FIXED | `ValidationView` required a model-written interface; design approval now depends only on blocking findings and the process approval. |
| Repair turn added duplicate rules (`…_2` copies of packing slip, replenishment, carrier rules) | WRONG | Rules grew from 14 to 20. |

## Stage 9: Generate Application

| Item | Mark | Notes |
|---|---|---|
| Generation blocked without a model-written interface (compiler, generation readiness, Generate view, top bar) | FIXED | `compiler.py`, `studio_conversation` readiness, `GenerateView`, `StudioChrome`: the derived screens count as the interface; an out-of-date custom interface still blocks. |
| After Validation → Continue, the Studio opened Screens & UI instead of Generate Application | WRONG | Another "sent to the wrong stage" case. |
| Generated from revision 28: 68 files, generator checks pass | OK | JSON, OpenAPI refs, permissions per write, manifest digests, traceability, runtime syntax. |
| "runtime records creatable": receipt, pick, delivery lines need an Item, count lines and transfers a Warehouse, that no role may create | WRONG | Flagged by the generator but not by Validation; it blocks most WMS journeys (see below). Should be a blocking validation finding. |
| Stale assistant message "The application's own interface has not been generated yet…" | WRONG | Left from before the fix. |
| Page asks for microphone access on load without a click | WRONG | Blocked by the browser pane; check whether voice can ever act without the person. |
| Running application (http://127.0.0.1:8100, revision 28) | OK | Real Python server with its own SQLite database; role sign-in; menu grouped by area per role. |

## Running application: end-to-end checks

| Path | Result | Notes |
|---|---|---|
| Role-based menus and data | OK | Each role sees only its areas and records (e.g. Goods receiver: Warehouse fulfilment, 3 processes; Picker: 1 process, 2 record types). |
| Permissions enforced by the server | OK | Picker creating an Item or reading goods receipts → 403 "Your application role cannot access this entity". |
| Field validation enforced by the server | OK | Negative reorder level → 422 "Reorder level is at least 0"; missing item name → 422; system-calculated field submitted → 422. |
| Optimistic locking | OK | Advancing with an old revision → "Process changed. Reload before continuing." |
| Inbound: receipt → putaway → availability | BLOCKED | Receipt saved and process started from the inline form; completing "Register the goods receipt" correctly requires a receipt line, which needs a fulfilment Item that no role can create. No stock balance exists, so "availability" cannot be shown. |
| Shortage → replenishment (verified reorder) | BLOCKED | Process starts; the server refuses the check step: "The linked Item record has no Projected quantity yet; the rule … needs it." Nothing calculates projected quantity (no stock ledger). Correct fail-closed behaviour, but the path cannot finish. |
| Outbound: order → pick → pack → dispatch | BLOCKED | Pick lines need the uncreatable Item; packing and shipment are separate unconnected processes; carrier steps need an integration. |
| Count discrepancy → adjustment | BLOCKED | Count lines need a Warehouse no role can create; adjustment approval is a business gap. |
| Return → inspection → disposition | NOT TESTED | Depends on delivery notes from the blocked outbound path; dispositions are invented rules. |

## Fixes needed before a working WMS (in order)

1. **Merge duplicate entities when adopting several packs** (Item, Warehouse), and give reference data a maintaining role; make "records no role can create" a blocking Validation finding.
2. **Stop automatic repair from editing reviewed stages** (or limit it to the Validation stage's own content) and never apply proposals without a person; find the client path that applied one.
3. **Add the missing WMS knowledge as verified packs, not model drafts**: storage locations/bins, stock balance and stock ledger, packing and shipment linked to pick-and-deliver, returns inspection.
4. **Remove the not-needed items** listed above (duplicate processes, roles, entities, invented rules) and reset the six falsely confirmed rules to assumptions.
5. **Model behaviour**: stop it inventing policy, duplicating steps/rules, and inserting duplicate trailing steps.
6. **Speed**: project dashboard (~8 s, requested 4×), Studio preview paint (~15 s).
