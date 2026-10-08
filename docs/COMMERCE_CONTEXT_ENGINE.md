# Commerce Context Engine (Phase 4)

One engine turns graph facts into a structured, evidenced, deterministic context for three journeys: **discovery**, **order and logistics visibility**, **warranty and traceability**.
It is not the conversational agent. It decides nothing with a language model and invents nothing: the agent explains the structure it returns.

```
request → intent / flow → CommerceContextEngine → (authorization on the records) → reader → rules → structured context + evidence path → agent → user
```

## Architecture

| Layer | Where | Reuses |
|---|---|---|
| Engine | `backend/app/commerce/engine.py` `CommerceContextEngine` | — |
| Discovery | `commerce/discovery.py`, `commerce/discovery_reader.py` | canonical datasets; graph through the existing `Exporter` (no new Cypher) |
| Logistics | `commerce/logistics.py` | Phase 2 `ShipmentContextBuilder` and `LogisticsReader` (three additive methods: `order_lines`, `shipments_of_order`, `orders_of_customer`) |
| Warranty | `commerce/warranty.py` | Phase 3 `WarrantyContextBuilder` → `rules.evaluate` (the single source of truth) |
| Common model | `commerce/contract.py` | — |
| Access | `commerce/access.py` | `Role`, `User`, signed session |
| Agent adapter | `commerce/intent.py`, `commerce/service.py` `AgenticCommerceService` | the engine only |
| API | `api/routes/commerce.py` | existing auth, `require()`, error format |

Every reader exists twice with identical output: files (tests, offline) and graph (Neo4j, read-only). `CommerceContextEngine.from_files(...)` / `.from_graph(client)`.

## Common contract

Every context has `context_id, context_type, generated_at, data_status, source_records, evidence, confidence, missing, warnings`, a `decision` (`CommerceDecision`), an `evidence_path` and a `visibility` note.

* `decision.status`: `SUCCESS | NOT_FOUND | NOT_ELIGIBLE | REQUIRES_REVIEW | REQUIRES_CLARIFICATION | INSUFFICIENT_DATA`; `decision.decision` is the domain word (`RECOMMEND`, `NO_VALID_RECOMMENDATION`, `TRACKED`, `DELIVERED`, `ROUTE_NOT_DETERMINABLE`, `ELIGIBLE`, `NOT_ELIGIBLE` ...).
* `confidence = {level: COMPLETE|PARTIAL|INSUFFICIENT, verified, basis}`. `verified` is true only when nothing is missing and every source record is `REAL` or `SOURCE_DERIVED`. All current contexts include `SYNTHETIC_DEMO` records, so `verified` is false and `basis` says so.
* `context_id` is a hash of the request, the reference day, the outcome and the records used. The same request on the same data gives the same body; only `generated_at` follows the wall clock unless the engine is pinned with `as_of`.
* Missing data is listed in `missing`; unknown is never turned into zero, "available" or "likely".

## Discovery

`extract entities → retrieve by vocabulary → identify machine → validate fitment, approved source, availability → price → rank → recommend`.

* The machine is resolved only from an id, an owned machine instance or an explicit model identifier (`KFT-600`, `kft 600`). A family (`KFT`), a type word (`loader`) or a near miss (`X200`) produces `REQUIRES_CLARIFICATION` with options or suggestions; it is never used as the machine.
* Retrieval covers `name, description, aliases, common_names, technical_terms, symptoms, subcategory` (and category, part number). A part covering every term is a candidate; partial matches only stand in when nothing covers the request, and the count set aside is reported (`extracted.partial_matches_set_aside`).
* A candidate is recommended only if it has **no rejection reason**. Reasons kept per candidate, in order: `NOT_APPROVED`, `DEPRECATED`, `NO_FITMENT`, `NO_APPROVED_SOURCE`, `OUT_OF_REGION`, `NOT_AVAILABLE`, `AVAILABILITY_UNKNOWN`, `LOW_SEMANTIC_MATCH`. Each names its source record or says `ABSENCE_OF_RECORD`.
* Ranking among valid candidates is a weighted mean of `fitment_score .30, semantic_match_score .25, approval_score .20, availability_score .20, regional_score .05` (components that do not apply, e.g. region with no destination, are left out). Weights are returned in `scoring`. Ties break by part id.
* Evidence path: `Part → Fitment → ApprovedSource → Inventory → Price`.

## Logistics

`LogisticsContext` is the Phase 2 `ShipmentContext` plus the common contract. Progress, ETA, alternatives and the comparison are read from the route records; nothing in the application knows how long or how dear any mode is. A shipment with `route_resolution_status = ROUTE_NOT_DETERMINABLE` returns `INSUFFICIENT_DATA`, `requires_review = true`, no route/legs/ETA/alternatives, and still returns what is known (status, events, order, part). Evidence path: `Order → Shipment → Route → TrackingEvent`. With no reference, an end customer's request resolves among their own open shipments, or asks which one.

## Warranty

`WarrantyContext` is the Phase 3 context. `ELIGIBLE → SUCCESS`; the other outcomes keep their name as the status. Each `decision_factor` has `result`, `detail`, and `sources: [{entity, id}]`; a factor resting on the absence of a record (no earlier claim) names the record that was searched and `basis: ABSENCE_OF_RECORD`. Evidence path: `MachineInstance → Installation → WorkOrder → Dealer → WarrantyPolicy → Claim → Evidence`.

## Authorization

Account role → commerce role: `END_USER → END_CUSTOMER`; `ORDER_PROCESSOR → OEM`, or `DEALER` when a `dealer_id` is given. An account can narrow itself, never widen. Ownership is checked on the records before a context is built: order `customer_id`/`dealer_id`, machine `owner_id`, installation and claim dealer. For non-OEM callers, a record that does not exist and a record that is not theirs are refused identically (403). Visibility is a small table (`access.HIDDEN`) applied to a copy of the result and reported in `visibility.hidden_fields`: end customers do not see per-depot stock, internal shipment flags, per-leg freight cost or technician names.

Limit: the demo has no dealer account. A processor may act as any dealer by naming a `dealer_id` (processors already read every order); a real dealer login would link an account to a dealer.

## API (all POST, authenticated, `commerce.context` permission, JSON)

| Endpoint | Body |
|---|---|
| `/api/v1/commerce/discovery/context` | `request`, optional `machine_id`, `machine_instance_id`, `destination_country`, `user_role`, `dealer_id` |
| `/api/v1/commerce/logistics/context` | optional `shipment_id`, `order_id`, `user_role`, `dealer_id` |
| `/api/v1/commerce/warranty/context` | `claim_id`, or `machine_instance_id` + `part_id`; optional `user_role`, `dealer_id` |
| `/api/v1/commerce/request` | agent adapter: `request`, optional `intent` and any of the references above |

Business outcomes are in `decision.status` with HTTP 200. 401 not signed in, 403 refused, 422 malformed. Unknown fields are rejected.

## Known data facts

* The G001 pump `PRT-007` fits the KFT-600 with an approved source but has **no stock in any depot** in the demo data, so it is rejected `NOT_AVAILABLE`. For "hydraulic pump for my KFT-600" the recommendation is `PRT-097` (central lubrication pump, `hydraulic pump` is one of its aliases), reported with `semantic_match = MEDIUM` and a warning.
* The Phase 2 "pump" shipment `SHP-NET-0001` carries `NVM-1010-HY`, a hydraulic hose.
