# Design Studio — engineering refinement round, 15 October 2026

Follows [STUDIO_REFINEMENT_2026_10_15.md](STUDIO_REFINEMENT_2026_10_15.md) and [TMS_RUNTIME_COVERAGE_2026_10_15.md](TMS_RUNTIME_COVERAGE_2026_10_15.md).
Nothing was committed, pushed or deployed. Neo4j was not written to. This is not a production-readiness statement: identity, durable
storage and hosting remain gated as described in `backend/DESIGN_STUDIO_ACTIVATION.md`.

## 1. Dates and times — one convention

| Type | Meaning | Wire and storage | Shown as |
|---|---|---|---|
| `date` | a calendar day | `YYYY-MM-DD`, must be a real date, never converted | the same day in the viewer's locale |
| `datetime` | an instant | ISO 8601 with an explicit offset (`Z` or `±hh:mm`); stored canonically as UTC `…Z` (milliseconds kept when present) | the viewer's local time with its zone name |

- Server (`record_validation.py`, copied into every generated app as `validation.py`): real calendar checks (`2026-02-30` is refused),
  a wall-clock time without an offset is refused with *“… needs a time zone, for example 2026-10-21T08:00:00Z …”*, and
  `normalize_record` stores datetimes as UTC. The generated server applies it on every write.
- Generated client (`runtime_app.js`): `datetime-local` input is the browser's local time, converted to UTC before sending and back to
  local time on reload; the field hint names the zone. Dates are never passed through `Date` conversions.
- Fixed with it: clearing an optional field on edit was silently ignored (now sent as `null` and saved); the list view crashed on any
  datetime column (`toLocaleString` rejects `dateStyle` together with `timeZoneName`) — found by the browser run, not by unit tests.
- Regression tests: `test_dates_and_times_follow_one_explicit_convention_and_survive_a_restart` (offsets, wall-clock, impossible dates,
  date unchanged, clearing, restart) and the browser run below (10:00 entered in Europe/Amsterdam → stored `08:00:00Z` → reloads as 10:00).

## 2. Generated application runtime

- Every process step now carries `blocked`: the rules on the step and on the automatic decisions that always follow it that cannot run
  (no executable logic, or waiting on an open business decision), with a plain-language reason. The page shows them and the action is
  disabled as *unavailable*; the server gives the same reason if it is called anyway (the action still fails closed).
- Errors no longer expose internal ids: missing or unknown related records come back per field (*“Choose the related Carrier record.”*),
  rule failures quote the rule, missing prerequisites name the record.
- Forms: field-level messages from the client and the server, `aria-invalid`, a related-record picker the role cannot read is shown as
  unavailable with the reason, records with generated keys get a readable label (`#40b95b · 20 Oct 2026`) instead of a 32-character id.
- Layout: page/grid min-width fixes removed horizontal overflow at 1024 and 390 px.
- Server-side authorization and safe regeneration are unchanged (verified: a dispatcher creating a transport plan through the API → 403).

## 3. Visual quality

- Business process diagram (Studio): a top-down layered layout — one row per rank, parallel paths side by side and ordered by their
  predecessors, exception paths after the main step in their row, loops routed in a lane to the right, branch labels beside their source,
  edges that skip ranks bend around the steps in between. A unit test asserts no overlapping nodes, downward forward edges and loops right
  of all nodes. The canvas scrolls with the wheel and hands scrolling back to the page at either end; Fit to screen centres the process.
  The structured editor keeps its previous compact layout.
- Decisions moved up in Domain Knowledge, next to the reference knowledge they come from.
- Checked in a browser at 1440×900, 1024×768 and 390×844 (Studio and generated app): no horizontal overflow.
- Not changed: the data-model (entity) diagram still uses straight relationship lines that can cross on dense models.

## 4. Unsupported items — 67, classified

`schema.json` now has `unsupported_items` (category, item, detail, decision) next to the unchanged `unsupported` list. Count verified
against the current code for the TMS adopted from `noordveld_transport` 2026.10.2: **67**.

| Category | Count | Items |
|---|---|---|
| Missing imported data | 47 | attributes of Order, OrderLine, Warehouse, Carrier, Route, Shipment, TrackingEvent — no import adapter is connected |
| Unresolved business decision | 8 | the 4 open decisions, and the 4 rules that wait on them (`rule_carrier_eligibility`, `rule_delivery_outcome`, `rule_pod_required`, `rule_handoff_complete`) |
| Status nothing sets | 6 | `status` of transport request, transport plan, pick task, pack unit, fulfilment handoff, transport exception |
| Missing executable logic | 5 | `rule_capacity_check` (no load attribute to compare), `rule_goods_ready` (nothing records the release), `rule_tracking_sequence` (a sequence check over imported events), `rule_availability` and `rule_allocation` (stock and route data not in this pack) |
| Unavailable external integration | 1 | `int_carrier_tracking` |

None of the remaining technical items could be closed from approved requirements: each needs a modelling decision, data this pack does
not contain, or a runtime capability (sequence rules) — adding them would be inventing policy or pretending an integration exists.

## 5. Business decisions

- Open decisions for the TMS: **carrier selection** (`dec_carrier_selection`), **when a delay becomes an exception** (`dec_delay_threshold`),
  **what counts as proof of delivery** (`dec_pod_requirements`), **partial releases at handoff** (`dec_partial_handoff`).
- Each decision now shows the steps it holds back and the rules waiting on it, and warns when a rule will still need executable logic after
  the answer. *Preview impact* creates a reviewed proposal (affected steps, unbound rules, validation before/after); `answer_decision` is
  review-gated, and applying it requires `studio.review` (project owner, process owner, org admin). A designer can prepare but not apply.
- Recording an answer does not make the rule executable: the generated application keeps refusing the step, now saying *“has no executable
  logic”* instead of *“waits on a business decision”*. Binding the rule is a separate, reviewed step in Rules & Logic / the structured editor.

## 6. Assistant

- Turns and applies carry server-computed `notes`: *applied to the specification (revision N)*, *not in the generated application yet —
  generate again, then run its tests*, *recorded as an assumption without executable logic*, *no responsible role yet*. Proposal cards say
  *Proposed only — nothing is saved until it is applied*, and that a decision needs an owner.
- The prompt forbids claiming that anything works, is tested or is live; a test keeps the prompt aligned with the action vocabulary.

## 7. Verified (actual results)

- Backend offline suite: 549 passed, 316 skipped (547 before this round). Frontend: 27 files, 419 tests passed; typecheck clean; lint
  warnings only (no errors); production build succeeds. Two frontend files (BusinessJourney, DomainKnowledgePage) time out only when the
  backend suite runs at the same time; they pass alone and in a clean full run.
- Browser journey: 17 of 17 steps passed, no page errors, at 1440×900, 1024×768 and 390×844 without horizontal overflow.
- Browser (headless Edge, Europe/Amsterdam): new project from one language-model turn → decisions previewed → designer refused →
  owner applied four (synthetic test answers) → separate approver approved process → editor generated screens → design approved →
  generated, its 3 tests passed, launched → import stand-in entered order/carrier/route → planner: date saved unchanged, missing related
  record flagged on the field, datetime stored as UTC and reloaded as local time, optional time cleared and persisted → process started,
  first step completed, *Plan the transport* shown as unavailable with the reason → dispatcher has no start action; API write → 403.

## 8. Graph database — isolated environment required before any schema change

The only configured Neo4j is the shared AuraDB behind the live commerce demo. Before any graph-schema work (Studio documents,
domain-knowledge structure, the duplicate part/machine keys found earlier):

1. A **separate Neo4j instance** (local Neo4j 5 in Docker, or a dedicated AuraDB Free/Professional instance) with its own credentials,
   set through separate variables (e.g. `DEV_NEO4J_URI`, `DEV_NEO4J_USERNAME`, `DEV_NEO4J_PASSWORD`, `DEV_NEO4J_DATABASE`), never the
   shared `NEO4J_*`. The code must refuse to run schema changes when the URI equals the shared one.
2. A **read-only export** of the shared AuraDB (`apoc.export` or `neo4j-admin database dump`), restored into the development instance as
   the starting point; restore tested before use.
3. Schema changes as **idempotent, reviewed scripts** (`CREATE CONSTRAINT … IF NOT EXISTS`), run first against the development instance,
   with the existing `neo4j_store` contract tests and the graph tests (`RUN_GRAPH_TESTS`) passing there.
4. **Duplicate keys resolved** in the development copy before a uniqueness constraint is added; the resolution reviewed by the data owner.
5. Only then a separately approved change window for the shared database, with a fresh backup taken immediately before.
