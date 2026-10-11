# Agentic E-Commerce MVP (Phase 5): contracts, agent and workspace

The first vertical slice of the product on top of the validated Phase 4 commerce APIs and the live Neo4j graph.

```
User → Commerce Agent → intent → Discovery / Logistics / Warranty → Commerce Context Engine → Neo4j
     → evidence + decision → agent answer → UI
```

## 1. The Phase 4 contract map (frozen: Phase 5 changes none of it)

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/v1/commerce/discovery/context` | `request`, optional `machine_id`, `machine_instance_id`, `destination_country`, `user_role`, `dealer_id` | `DiscoveryContext` |
| `POST /api/v1/commerce/logistics/context` | `shipment_id` or `order_id` (+ scope) | `LogisticsContext` |
| `POST /api/v1/commerce/warranty/context` | `claim_id`, or `machine_instance_id` with `part_id` (+ scope) | `WarrantyContext` |
| `POST /api/v1/commerce/request` | `request`, optional `intent` and references (+ scope) | `{intent, intent_source, decision, context}` |

* **Common context fields** (`app/commerce/contract.py`): `context_id`, `context_type`, `generated_at`, `data_status`, `source_records[]`, `evidence[]`, `confidence{level, data_status, fact_verified, real_world_verified, basis}`, `missing[]`, `warnings[]`, `decision{status, decision, summary, facts, reasons, evidence, source_records, missing, warnings, recommended_next_action}`, `evidence_path[]`, `visibility{role, hidden_fields[]}`.
* **Statuses** (`decision.status`): `SUCCESS, NOT_FOUND, NOT_ELIGIBLE, REQUIRES_REVIEW, REQUIRES_CLARIFICATION, INSUFFICIENT_DATA`. Business outcomes are HTTP 200; HTTP errors are 401 (not signed in), 403 (not allowed: the same body for a record that does not exist and one that is not yours), 422 (malformed).
* **Discovery decisions**: `RECOMMEND, NO_AVAILABLE_RECOMMENDATION, NO_VALID_RECOMMENDATION, REQUIRES_CLARIFICATION`; part-level `product_match_status` includes `CANONICAL_MATCH`, `CANONICAL_TYPE_MISMATCH`, `ALIAS_ONLY_MATCH`, `PARTIAL_MATCH`; rejection codes `NO_FITMENT, NO_APPROVED_SOURCE, NOT_AVAILABLE, AVAILABILITY_UNKNOWN, CANONICAL_TYPE_MISMATCH, …`. Fields: `machine`, `candidate_parts`, `fitment_results`, `approved_sources`, `availability`, `pricing`, `recommended_part`, `compatible_part`, `alternatives`, `ranking`, `rejection_reasons`, `clarification`.
* **Logistics**: `shipment`, `order`, `order_lines`, `shipment_lines[]` (every order line on the shipment, each with its part), `parts[]`, `part` (set only for a single-line shipment), `shipment_kind` (`SINGLE_LINE | MULTI_LINE | NO_LINE_RECORDED`), `order_shipments[]`, `order_split`, route, legs, `planned_eta`, `transport_comparison`, `tracking_events`, `route_resolution_status`. **Multi-line shipment** (several order lines travel together, canonical model `ShipmentLine`) and **order split** (one order over several shipments) are different facts; an order with several shipments still returns `REQUIRES_CLARIFICATION`.
* **Warranty**: `decision.facts.outcome` is `ELIGIBLE | NOT_ELIGIBLE | REQUIRES_REVIEW | INSUFFICIENT_DATA`, produced by `app/lifecycle/rules.py` only; `decision_factors[]` (every check with PASS / FAIL / UNKNOWN and its sources), `installation`, `dealer`, `technician`, `work_order`, `fitment`, `approved_source`, `warranty_policy`, `coverage_start/end`, `replacement_history`, `prior_claims`, `claim`, `traceability`.
* **Authorization** (`app/commerce/access.py`): END_USER → `END_CUSTOMER` (own records only), ORDER_PROCESSOR → `OEM` (everything) or `DEALER` with a `dealer_id`. An account can narrow itself, never widen. Removed for a customer: `availability[*].warehouses`, `shipment.remediation_flags`, `route_legs[*].estimated_cost`, `technician.name`, `traceability.*.installed_by.name`.
* **Evidence**: `evidence_path[]` is an ordered chain of `{step, entity, id, relation_to_next, data_status}`; provenance is `source_records[]` with `data_status` and `source_record_id`. Synthetic demo data is labelled `SYNTHETIC_DEMO` and the confidence block says so (`real_world_verified` is false unless every record is supplied data).

## 2. What Phase 5 adds

| Where | What |
|---|---|
| `POST /api/v1/commerce/agent` | The Commerce Agent. Body: `message` (≤ 500), `state` (what the previous answer returned), optional scope. Same authentication, permission (`commerce.context`) and principal derivation as the other commerce routes; a refusal in any journey is a 403 for the whole request. |
| `app/commerce_agent/agent.py` | Understanding (deterministic cues; the model only routes a message the cues cannot), reference resolution, the engine calls. No domain rule. |
| `app/commerce_agent/answer.py` | The answer, composed from each context's own `decision.summary`, facts and evidence. Optional model rewording of the lead only. |
| `app/llm` | One new operation, `parse_commerce_request` (routing only: which of the three journeys), with its schema and rules. Gemini's schema converter keeps array `items`. |
| `frontend/src/api/commerce.ts`, `components/commerce/*`, `pages/CommercePage.tsx` | The workspace at `/commerce` (nav item **Commerce Assistant**). |
| `scripts/commerce_agent_flows.py` | The four user flows and the security flows through the real API against the live graph, with a before/after graph snapshot. |

Phase 4 behaviour changed in **no** respect: no existing field, status, rule or visibility entry was altered (the Phase 4 and 4H suites pass unchanged). The only edits to existing files are additive (the route, the dependency, the LLM protocol, the Gemini `items` fix, a nav entry).

### The agent response

```
intent        DISCOVERY | LOGISTICS | WARRANTY | MULTI_DOMAIN | CLARIFICATION | UNKNOWN
status        ANSWERED | PARTIAL | REQUIRES_CLARIFICATION | OUT_OF_SCOPE
answer        {text, lead, sections[{domain, title, status, decision, headline, lines[], notes[]}], synthetic_notice, grounding{mode TEMPLATE|LLM, validated, note}}
steps[]       what ran, in order: DISCOVERY → WARRANTY → LOGISTICS, with the resolution notes
contexts      the full, role-scoped Phase 4 contexts, by journey
evidence, evidence_paths, source_records, confidence, visibility, data_status, warnings, missing   (aggregated, tagged with the journey)
clarification {domain, question, options[]}
state         identifiers and the last search text (+ the question awaiting an answer); never a decision
understanding {intent, domains, source RULES|STATE|LLM|NONE, focus, references, reasons}
```

### Rules the agent follows
* **Intent.** Cue scores per journey; every journey scoring ≥ 2 runs (`MULTI_DOMAIN` when several). A follow-up with no cue of its own continues the previous journey. The model is consulted only when the cues find nothing, and only picks journeys: it cannot override a decisive match. Out of scope → `UNKNOWN` (declined, with what the agent can do). Some signal but no journey → `CLARIFICATION`.
* **References.** Identifiers (`SHP-…`, `ORD-…`, `CLM-…`, `MI-…`, `PRT-…`, a part number) are read from the message by pattern, never by the model. A part number is turned into a part id through the catalogue.
* **Search text.** In a multi-journey message only the search clause goes to discovery (urgency words removed); the other journeys use the whole message.
* **Warranty resolution.** Claim given → that claim. Machine and part given → the single claim recorded for that part is "the failed one" and is judged; no claim → the installation is judged on its own; several claims → a question. In a multi-journey message the machine comes from discovery's machine and the customer's own instances of it (one → used; several → a question), and the part is the installed part of the kind searched for (canonical matches only).
* **Logistics for an unordered part.** The commerce logistics context follows shipments and orders. A replacement nobody has ordered has no shipment, so the answer says that (`NO_SHIPMENT_FOR_UNORDERED_PART`); no delivery time is invented. (Route-based delivery estimates for a part are produced by Agentic Shopping, not by the commerce contexts.)
* **Answers.** Each section is `decision.summary` plus lines templated over returned values. A question the agent asks is not reworded. The language model may reword the lead (≤ 2 sentences) only if `is_grounded` accepts it (every number and identifier is in the evidence) and the sense check passes (each section's outcome survives and a recorded absence is not turned into a presence); otherwise the deterministic lead stays and `grounding.note` says why.

## 3. The workspace: one input, one answer

`/commerce`, signed-in users only (a signed-out visitor sees a sign-in prompt and no data). There are no domain tabs and no separate forms: the user asks in natural language and the assistant works out the journey.

* **One input** ("What can I help you with?", Enter or Ask) and **one answer area** directly beneath it. The answer shows a plain-language lead, then only the detail that is relevant (a shipment question shows no empty warranty or discovery panel): the part card, the order lines of a shipment, the warranty checks, the machines a part is approved for, the order and its lines when it has no shipment yet.
* **Clarification is conversational.** The question is asked once, inside the answer, with options only when the records support them (the customer's own machines, claims, shipments). Choosing one, or typing a short reply, continues the original request: the server keeps the waiting question (`state.pending_message`) and reads a short reply as its answer. A new request drops it.
* **Evidence stays in the answer**: a collapsed "Evidence and sources" box holds the evidence path, confidence, hidden-field note, evidence items and source records. The demonstration-data disclosure and how the answer was written (records or model wording) are shown under the answer.
* **Follow-ups keep context.** Suggested follow-up questions fit the answer (and are omitted when they would make no sense, e.g. shipment questions for an order with no shipment). Earlier turns collapse into "Earlier in this conversation". *Start over* clears the remembered references.
* **States.** Loading ("Checking the records…", previous answer dimmed), no-result (the backend's own statement, e.g. no shipment recorded yet), ambiguous (the clarification), out of scope (declined with starting points), error (403 "You do not have access to that record", network error with *Try again*).
* **Responsive.** One column; on a phone the Ask button goes full width, tables scroll, chips stack.
* Order processors get a small "View as" control (OEM or a dealer id); a customer's role is never sent.

The page formats the backend's contexts and holds no business data (the existing `noBusinessData` scan covers it: the starting questions name no machine, shipment or claim). Parts Intelligence and Agentic Shopping are untouched.

### Questions about one part and about orders (also answered in the same place)
* *Which machine uses this part?* (`PART_FITMENT`) and *Where did this part come from?* (`PART_ORIGIN`): `app/commerce/part_lookup.py` reads the fitment and approved-source records (a machine is listed only when a fitment record approves it; a source only when an approved-source record exists; anything not held is "not recorded", never a confirmed negative). The result carries the common contract (decision, evidence, evidence path, source records, confidence).
* *Where is order HCME-ORD-000001?*: an order the shop placed is recognised, and the logistics reader reads its owner through the account that placed it (`PLACED_BY` → `ACTS_FOR` → customer) after the existing `ORDERED_BY` link, so a customer sees their own shop order. It reports the order, its lines and "no shipment recorded yet" when there is none.

### Added in the Waterfall audit (see [WATERFALL_TRACEABILITY.md](WATERFALL_TRACEABILITY.md))
* **Potential routes (`ROUTE_OPTIONS`)**: "How long to ship to Lagos?", "Can you deliver to the USA?" with no shipment or order named. `app/commerce/route_options.py` reads the transport lanes the network records to a place (city, country or region; `network_routes()` on both logistics readers, one read-only query) and lists each route with its own days, cost and legs, fastest first. They are labelled potential routes: none is assigned to a shipment, and the numbers are the route records' own demonstration values. A place with no lane gets no route. A shipment or order number in the message always wins.
* **Comparison and lateness**: "compare sea and air", "by air", "alternatives" show the recorded alternative routes; a shipment past its planned ETA with no delivery is stated as such (no new ETA is invented).
* **Discovery**: a word the catalogue does not know is read as the closest catalogue word when one is close (every change is listed in the answer's notes); an unmatched machine identifier is named; "I need a …" is routed by rules; a trailing "delivered to <place>" is not part of the part search.
* **Warranty wording**: the check that decided a verdict is introduced as the check that failed, was incomplete or needs review, not as a bare requirement.

## 4. Validation

* `tests/test_commerce_agent.py` (75 tests): intents, discovery, logistics (single, multi-line, split, delivered, unresolved), warranty G001–G008, multi-domain, evidence, wording guard, the API, customer/dealer/OEM isolation, malformed requests.
* `frontend/src/components/commerce/commerce.test.tsx` (13 tests): the workspace over a mocked API.
* `scripts/commerce_agent_flows.py`: Flows A to D, the security and OEM flows, through the real FastAPI app against live Neo4j, with and without the model; the graph snapshot (counts, protected counts, checksum, fingerprint) is compared before and after.

## 5. Limits
* No delivery estimate for a specific part that has not been ordered: the Assistant lists the network's potential routes to the place instead (Agentic Shopping computes route-based delivery for a part).
* Discovery clarifications that ask for a machine offer no options: the user types the model.
* The model-wording guard is a conservative check (outcomes and absences), not a proof; the deterministic text is always the fallback and is what the evidence tab backs.
* Synthetic demonstration data throughout.
