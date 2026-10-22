# Generated TMS: executable coverage — 15 October 2026

Follows [STUDIO_REFINEMENT_2026_10_15.md](STUDIO_REFINEMENT_2026_10_15.md). The TMS generated from the `noordveld_transport`
reference pack ran, but most of it could not be used on a fresh database. This change fixes the parts that had a decided answer and
leaves every business decision open. Nothing was committed or pushed, and Neo4j was not written to.

## What changed and why the counts dropped

| Change | Where | Effect |
|---|---|---|
| **Generated keys.** A system-generated key gets a value when its record is created: the record's own id, or the next number for an integer key. A submitted key is still refused. Values stored earlier are no longer re-validated as if the client had sent them. | `runtime_server.py` (`generated_value`, `save_record`), `runtime_generation.py` | 8 coverage items removed (`pick_task_id`, `pack_unit_id`, `handoff_id`, `transport_request_id`, `transport_plan_id`, `vehicle_id`, `pod_id`, `exception_id`). Also fixes a bug: before, a second record with an empty key failed with "must be unique". |
| **Absent keys duplicate nothing.** Uniqueness is checked only when a key has a value. | `runtime_server.py` | A dispatcher can create more than one shipment even though its imported `shipment_id` is never supplied locally. |
| **Bound `rule_exception_resolution`.** The rule already says the dispatcher decides between retry and cancel, and no open decision affects it. The binding (`value` of `ent_transport_exception.resolution`) only reads the dispatcher's recorded choice. Any value other than `RETRY_DELIVERY` or `CANCEL_TRANSPORT` is refused. | `scripts/build_transport_reference_pack.py` | 1 item removed. |
| **`tl_request` without prose.** "An order exists" and "a transport request exists" are already the step's reads and writes, and the runtime refuses the step until both records are linked. | same | 1 item removed. The step can now run. |
| **Import stand-in.** Entities whose key is `imported` come from another system: Order, OrderLine, Warehouse, Carrier, Route, Shipment and TrackingEvent. They are listed in `schema.json` as `imports`. No adapter is connected, so a labelled demo identity, *Data import stand-in (no integration connected)*, can enter them by hand. It is not a business role. It cannot run process steps or touch any other entity. Its records stay in their organization and are audited as `record.import`. | `runtime_server.py` (`IMPORT_ROLE`), `runtime_generation.py`, generated `README.md` | `runtime_records_creatable` now **passes**. Its detail says these records come from an external system with no adapter connected. No business role was made to own orders, carriers or warehouses, because the domain pack says those values are imported. |

The pack version moved from 2026.10.1 to **2026.10.2**, so projects adopted from the older version show the newer pack as available.

**Counts** (TMS adopted from the pack): `runtime_business_coverage` went from 77 to **67** items. `runtime_records_creatable` went from a
warning with 3 gaps to a pass. The conversation-built TMS that reported 84 items has more adopted content, but the same 10 removals
apply to it.

## Verified

- `python backend/scripts/test_offline.py`: **547 passed, 316 skipped** (baseline 544 / 316). The new tests are in
  `backend/tests/test_tms_runtime_fresh_database.py`: coverage contents and count; a planner on a fresh database; stand-in limits;
  a submitted generated key refused; a key that survives updates; tenant isolation of imports.
- Browser check of the exported, fixture-approved runtime on a new `studio-runtime-*` database, all through the UI:
  1. The stand-in entered an order, a carrier and a route.
  2. The planner created a transport request, and its key was generated.
  3. The planner started *Transport lifecycle* and completed *Register the transport request*.
  4. The planner created a transport plan with the carrier and route.
  5. The planner completed *Plan the transport*. That was refused with "Rule rule_carrier_eligibility has no executable binding", and the
     instance stayed at *Plan the transport*, unchanged.

## What is still not executable (67 items)

**The planner's path ends at carrier eligibility.** That is as far as an honest end-to-end run goes until the business decides.

- **Open decisions (4)**, deferred and never answered for the owner:
  - `dec_carrier_selection` blocks `rule_carrier_eligibility` and so stops every transport after planning.
  - `dec_delay_threshold` blocks `rule_delivery_outcome`.
  - `dec_pod_requirements` blocks `rule_pod_required`.
  - `dec_partial_handoff` blocks `rule_handoff_complete`.
- **Rules without a binding (9):**
  - `rule_carrier_eligibility`, `rule_delivery_outcome`, `rule_pod_required` and `rule_handoff_complete` depend on the open decisions above.
  - `rule_capacity_check`: no load attribute exists on the plan or request to compare with `capacity_kg`. Adding one is a modelling decision.
  - `rule_goods_ready`: nothing records the release that `tl_check_ready` could read. The step reads only the transport request.
  - `rule_tracking_sequence`: confirmed, but it is a check over a sequence of events (`app/logistics/rules.py`). The bounded
    single-comparison binding cannot express it, so it would need a runtime extension rather than pack data.
  - `rule_availability` and `rule_allocation`: confirmed, but they depend on stock and route data this pack does not include.
- **Imported attributes (47)** across the 7 imported entities. No import adapter is connected. Demo values can only be typed in by the stand-in.
- **Statuses (6)**: `status` on transport request, plan, pick task, pack unit, handoff and exception. Nothing provides them.
  The domain pack declares initial states for some of them (`ASSIGNED`, `RELEASED`, `RECORDED`, `RAISED`), but only as assumptions, and
  the Design Studio entity model does not carry lifecycle events. Inferring a status from the process state would be a guess.
- **Integration (1):** `int_carrier_tracking` (deferred).

## Noticed, not fixed (outside this task)

> Both items below were fixed later the same day; see [STUDIO_ENGINEERING_ROUND_2026_10_15.md](STUDIO_ENGINEERING_ROUND_2026_10_15.md).

- The generated record form sends `datetime-local` values without a time zone (for example `2026-10-21T08:00`). The server requires a
  zone, so every datetime field (planned departure and arrival, `raised_at`, `delivered_at`, `released_at`) is refused when entered
  through the UI. Confirmed against the server's pattern; the plan in the browser check was saved without dates.
- On the fresh-database walk-through, the Warehouse picker on the planner's transport-request form says "Related records are not visible
  to your role". The planner reads no step that includes Warehouse. The link is optional, so this does not block anything.
