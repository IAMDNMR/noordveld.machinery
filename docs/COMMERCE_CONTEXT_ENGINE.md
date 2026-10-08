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
* `confidence = {level, data_status, fact_verified, real_world_verified, basis}` keeps four things apart. `level` is completeness (COMPLETE / PARTIAL / INSUFFICIENT). `data_status` is what kind of data the records are (`SYNTHETIC_DEMO`, `SOURCE_DERIVED`, `MIXED` ...). `fact_verified` is true when every fact in the decision was checked against graph records that agree with each other, **including on synthetic demo data**: it says the graph is internally consistent. `real_world_verified` is true only when nothing is missing and every record is `REAL` or `SOURCE_DERIVED`. Unresolved requests, missing route or missing warranty facts are `fact_verified = false`; a definite negative (not eligible, right part out of stock) is `true`.
* `context_id` is a hash of the request, the reference day, the outcome and the records used. The same request on the same data gives the same body; only `generated_at` follows the wall clock unless the engine is pinned with `as_of`.
* Missing data is listed in `missing`; unknown is never turned into zero, "available" or "likely".

## Discovery

`extract entities → retrieve by vocabulary → identify machine → canonical product check → fitment → approved source → availability → price → rank → recommend`.

**Rule: an alias never overrides canonical product semantics.** Authority, highest first: canonical product / category / type (`Part.name`, `technical_terms`, `part_number`, subcategory and category names) → machine fitment (the FITS record) → approved source → availability → semantic relevance → ranking. Aliases, common names, symptoms and the (generated) description only *identify* a candidate. Each candidate gets a `product_match` status:

| status | meaning | can be recommended |
|---|---|---|
| `CANONICAL_MATCH` | every request term is in the part's canonical name / category / type | yes |
| `CANONICAL_TYPE_MISMATCH` | covered only by alias text, and a term that names a product class (hydraulic, pump ...) conflicts with the part's canonical class | never, not even as an alternative |
| `ALIAS_ONLY_MATCH` | covered by alias text only, no class conflict | never; shown in `unconfirmed_matches` for the user to confirm |
| `PARTIAL_MATCH` | some terms not covered | never |

* The machine is resolved only from an id, an owned machine instance or an explicit model identifier. A family (`KFT`), a type word (`loader`) or a near miss (`X200`) is `REQUIRES_CLARIFICATION`; the near miss may be *suggested*, never used.
* Each candidate is stated as separate facts, not one score: `product_match`, `fitment`, `approved_source`, `availability` (`AVAILABLE | UNAVAILABLE | UNKNOWN`), `recommendation`, plus `flags {MATCHED, PRODUCT_MATCH, COMPATIBLE, APPROVED, AVAILABLE, RECOMMENDED, REJECTED}`.
* Rejection reasons, in order of authority: `CANONICAL_TYPE_MISMATCH | ALIAS_ONLY_MATCH | LOW_SEMANTIC_MATCH`, `NOT_APPROVED | DEPRECATED`, `NO_FITMENT`, `NO_APPROVED_SOURCE | OUT_OF_REGION`, `NOT_AVAILABLE | AVAILABILITY_UNKNOWN`. Each names its record or says `ABSENCE_OF_RECORD`.
* Decisions: `RECOMMEND`; `NO_AVAILABLE_RECOMMENDATION` (the right part exists, fits and is approved, but is unavailable or its stock is unknown: `compatible_part` names it, `alternatives` lists only other parts that pass the same checks, and no part of a different kind is substituted); `NO_VALID_RECOMMENDATION`; `REQUIRES_CLARIFICATION`.
* Ranking, among parts that passed every gate: weighted mean of `fitment .30, semantic_match .25, approval .20, availability .20, regional .05` (components that do not apply are left out), ties by part id. Weights are returned in `scoring`.
* Evidence path: `Part → Fitment → ApprovedSource → Inventory → Price` (for the recommended part, or for the compatible part when it cannot be offered).

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

* "hydraulic pump for my KFT-600": `PRT-007` (piston pump, Hydraulics) is the right part: it fits, has an approved source, and has **no stock in any depot**. The result is `NO_AVAILABLE_RECOMMENDATION` with `compatible_part = PRT-007`. `PRT-097` (central lubrication pump) and `PRT-078` (water pump) carry the alias "hydraulic pump" but belong to other categories: `CANONICAL_TYPE_MISMATCH`, kept as diagnostics only.
* The Phase 2 "pump" shipment `SHP-NET-0001` carries `NVM-1010-HY`, a hydraulic hose.

## Live validation

`python backend/scripts/commerce_live_validate.py [--out report.json] [--offline] [--full-detail]` (read-only; helpers in `scripts/commerce_validation_lib.py`).

**Online run:** connectivity (host, port, DNS, TCP, authentication, database) → `snapshot_before` → **pass 1** → `snapshot_after_pass1` → **pass 2** → `snapshot_after_pass2` → determinism. A pass contains:
* **entity counts** for 29 entities (Part … FeaturedScenario): canonical vs graph, difference, status, and the missing ids. Id sets are compared, not only totals. Records written by the running app (`source_id = APP-SESSION`) are counted apart as `graph_app_written`.
* **field-level comparison** of every registry dataset (all 46, including Phase 1–3 and the network datasets) with the same canonical-field-to-graph-property mapping the ingestion uses, plus the relationship edges each record needs and provenance (`data_status`, `source_record_id`). Every difference is `dataset / record_id / field / canonical_value / graph_value / difference_type` with type `MISSING_IN_GRAPH | MISSING_IN_CANONICAL | VALUE_MISMATCH | TYPE_MISMATCH | NORMALIZATION_ONLY | IGNORED_BOOKKEEPING`. An absent graph property where the canonical record states a value is `MISSING_IN_GRAPH`.
* **normalisation**: only the named rules in `RULES` (list order, numeric type/tolerance, empty-equivalent, date/timestamp format, country-code case, specification-name casefold, FITS `CONFIRMED→APPROVED`, SUPPLIED_BY `ACTIVE*→APPROVED`, import bookkeeping). Each applied rule is counted in `normalization.normalization_rules_applied`; the protected catalogue allows only list order, numeric type/tolerance and specification-name casefold. There is no catch-all bucket.
* **protected comparison**: machines, parts, categories, specifications, plants, legacy references, assemblies, plus the supplied FITS and SUPPLIED_BY relationships, part category links and search aliases.
* engine(files) vs engine(graph) on every scenario; discovery D001…, logistics per shipment (expected/actual status and route, ETA, alternatives), warranty G001–G008 (expected/actual decision, matching/mismatching factors); authorization (test, role, resource, expected, actual); the four API routes; evidence-chain and provenance checks.

**Read-only:** the only graph handle is `ReadOnlyGraph` (no write method; a query containing a write keyword raises before it is sent; every query is counted). Static and behavioural tests enforce it.

**Classification** (`final_classification`, exit code): `PHASE 4H COMPLETE` (0) only if Neo4j was reached and every criterion in `acceptance` is PASS twice; `PHASE 4H FAILED — LIVE VALIDATION FOUND PRODUCT/DATA ISSUES` (1) if Neo4j was reached and anything failed; `PHASE 4H BLOCKED — LIVE NEO4J UNREACHABLE` (2) if DNS, TCP, authentication or the database failed, or in OFFLINE mode. BLOCKED, SKIPPED and FAIL are never reported as PASS.

**Offline:** `--offline` runs the same machinery against an in-memory twin of the canonical files. It proves the validator and the engine logic; it is not Neo4j, reports `mode = OFFLINE`, `live_graph_verified = false`, and is always BLOCKED.

`tests/test_commerce_validator.py` tests the validator (counts, field comparison, normalisation, protected comparison, snapshots, determinism, JSON, unreachable/authentication/blocked, mismatch, mutation guard). `tests/test_commerce_live.py` runs the live checks and **skips** (never passes) when Neo4j is unreachable.
