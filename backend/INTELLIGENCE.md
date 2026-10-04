# Parts Intelligence

An AI + knowledge-graph layer for investigating parts, machines, fitment, suppliers, dealers, assemblies, compliance, stock and relationships.
Neo4j is the factual layer, the backend is the control layer, the language model only understands and words.

```
question → intent + entities → controlled query router → fixed Cypher → Neo4j → evidence + provenance
        → validation → deterministic answer (optionally reworded by the model, then checked) → UI
```

**The language model never writes or runs Cypher.** It is never connected to the database. It may (1) classify a question that the keyword rules
cannot, naming an intent from the registry and the entity names the user wrote, and (2) reword an answer that the backend has already
produced from evidence. Everything else (entity lookup, the query, the numbers, provenance) is deterministic Python and Cypher.

## Layout

| Path | Role |
|---|---|
| `app/intelligence/rules.py` | deterministic intent and mention extraction, tried first; most questions never reach the model |
| `app/intelligence/registry.py` | the intent registry: required/optional entities, queries used, result type, allowed relationship path, provenance |
| `app/intelligence/resolver.py` | entity resolution against Neo4j; several equal matches become candidates, never a silent choice |
| `app/intelligence/handlers.py` | one function per intent: runs the intent's fixed queries, shapes results, records evidence |
| `app/intelligence/service.py` | orchestration, intent refinement from the entities found, clarification, grounded wording |
| `app/intelligence/grounding.py` | builds the structured evidence object the wording receives; rejects wording that adds numbers, identifiers or claims not in the evidence, recites every item, or **denies a value the result holds** |
| `app/intelligence/contract.py` | the result-type contract: an intent returns only its declared entity type (`registry.RESULT_KINDS`); anything else is supporting evidence |
| `app/intelligence/provenance.py` | `data_status` → data class vocabulary |
| `app/intelligence/workspace.py` | the part workspace tabs, insights, graph view, KPIs, suggested questions |
| `app/graph/queries/intelligence.py` | **all** Cypher: read-only, parameterised, bounded (tests enforce this) |
| `app/graph/repositories/intelligence.py` | one method per named query |
| `app/llm/` | provider-independent `LLMClient`; `prompts.py` (shared prompts), `structured.py` (schemas, validation, rate limit, metrics), `groq.py` (default provider), `gemini.py` (optional); `create_llm` is the only place a provider is chosen |

## Intents

`PART_SEARCH`, `PART_TO_MACHINE`, `MACHINE_TO_PART`, `PART_TO_CATEGORY`, `PART_TO_ASSEMBLY`, `ASSEMBLY_TO_PART`, `PART_TO_PART`, `PART_TO_SUPPLIER`,
`PART_TO_DEALER`, `PART_TO_LOCATION`, `PART_TO_WAREHOUSE`, `WAREHOUSE_STOCK`, `PART_TO_INVENTORY`, `PART_TO_COMPLIANCE`, `PART_PROVENANCE`, `PART_GRAPH`, `MACHINE_GRAPH`,
`SUPPLIER_GRAPH`, `DEALER_GRAPH`, `DATA_QUALITY`, `UNSUPPORTED`. Each is documented in `registry.py`. An intent the registry does not know
is rejected and no query runs. Unsupported or unclear questions get a clarification, never a guess.

## API (`/api/v1/intelligence`)

| Endpoint | Purpose |
|---|---|
| `POST /query` | `{question, selected?, limit?}` → intent, entities, answer, structured results, evidence, provenance, graph path, warnings, actions, clarification |
| `GET /suggestions` | example questions built from the graph itself (so they never name anything the graph lacks) |
| `GET /kpis` | whole-graph counts, calculated in Neo4j |
| `GET /parts/{key}` | overview, status, valid actions |
| `GET /parts/{key}/fitment` · `/relationships` · `/assemblies` · `/suppliers` · `/dealers` · `/inventory` · `/compliance` · `/provenance` · `/insights` · `/graph` | one per workspace tab, loaded only when the tab is opened |

## Data truth

* Only explicit relationships are reported. A supplier that exists is not "supplying" without `SUPPLIED_BY`; two parts with similar names are never
  "alternatives", "replacements" or "interchangeable" (`CO_ORDERED_WITH`, `RELATED_COMPONENT`, `SAME_NAME_GROUP_AS` are shown with what they mean).
* City and country are stated values of a record; sharing one is never presented as a business relationship.
* Missing stock is `NOT_CONNECTED` / unknown, never zero. Missing fulfilment is "Not configured". Missing values read "Not available".
* Data classes: `REAL`, `SOURCE_DERIVED`, `DERIVED`, `SYNTHETIC_DEMO`, `USER_PROVIDED`, `TEST_DATA`, `INTERNAL_REFERENCE_ONLY`, `UNKNOWN`, `NOT_CONNECTED`,
  taken from each node's and relationship's `data_status`. Synthetic demo data is always labelled. No confidence percentages are produced.
* Insights and KPIs are counted in Neo4j or Python, not by the model.
* Every answer anchored on one entity carries a `subject`: its identity in a few facts (a part's number, name, category, catalogue status,
  source and data class; a machine's name, type and family; a supplier's or dealer's stated location), and the answer text names it. A list of
  machines or suppliers never appears without saying which part it belongs to. Searches and whole-catalogue answers have no subject.
* "Does X fit Y?" answers for that pair only. No stored fitment reads "not established", never "does not fit".
* When several candidates match, the one whose full name the question spells out is used; otherwise the user is asked. Nothing is guessed.

## Result types and evidence (the answer contract)

Every intent declares what it returns (`registry.RESULT_KINDS`): machines for `PART_TO_MACHINE`, suppliers for `PART_TO_SUPPLIER`, dealers for `PART_TO_DEALER`,
warehouses for `PART_TO_WAREHOUSE`, warehouse and dealer stock records for `PART_TO_INVENTORY` and `PART_TO_LOCATION` ("where is it available": suppliers are
`PART_TO_SUPPLIER`), parts for `WAREHOUSE_STOCK`, `PART_TO_PART`, `MACHINE_TO_PART` and the listing intents, assemblies, compliance requirements,
orders (and shipments for one order) and service plans likewise. A query may walk through other nodes; those are **supporting evidence**, not result cards.
`contract.enforce_result_kinds` removes anything else after every handler and logs it; a test runs one real question per intent and fails if it ever has to.

The wording step receives a structured evidence object (`grounding.grounding_records`): the subject, the total, and for every result its kind, name,
relationship, data class and **every fact** (units, primary supplier, lead time, fitment, status). Missing values are left out, never written as zero.
After the model writes its sentence the backend checks it against the result (`grounding.contradicts`): a quantity or lead time denied while the result
holds one, a primary supplier denied while one is marked, "no <entity>" while the result lists that entity, or synthetic compliance data worded as established
certification. A contradictory sentence is never shown: the deterministic, evidence-backed answer is used instead.

Absence is worded as what it is: "not established in the current graph", never a flat "no". Compliance data that is `SYNTHETIC_DEMO` is stated as
"recorded, but SYNTHETIC_DEMO, and does not establish real-world certification".

## Entity types that can anchor a question

| Entity | Decision | Why |
|---|---|---|
| Part, machine, supplier, dealer, assembly, order | SUPPORTED | explicit relationships, safe queries |
| Warehouse | SUPPORTED (`WAREHOUSE_STOCK`) | `(Part)-[AVAILABLE_AT]->(Warehouse)` with recorded units; resolved by id or name, never by city; a warehouse that is not uniquely named is asked about |
| Shipment | SUPPORTED WITH CLARIFICATION (not built) | reachable only through its order (`HAS_SHIPMENT`); a shipment id would resolve to its order and answer through `ORDER_STATUS`. Today it asks for the order number |
| Compliance requirement | SUPPORTED WITH CLARIFICATION (not built) | `HAS_COMPLIANCE` edges exist, but every requirement is `SYNTHETIC_DEMO`; "must meet" would imply an obligation the graph does not state, so only "has a recorded link to" could be answered, labelled demo |
| Service plan | SUPPORTED WITH CLARIFICATION (not built) | `REQUIRES_PART` and `FOR_MACHINE` exist; plans and intervals are demo data, not maintenance instructions |

No synthetic relationship is created to make any of these answerable.

## Language model (Groq by default)

Configured only in `backend/.env`: `LLM_PROVIDER` (`groq` default, or `gemini`), `GROQ_API_KEY`, `GROQ_MODEL` (default `qwen/qwen3.8-27b`),
optionally `GEMINI_API_KEY` / `GEMINI_MODEL`, `LLM_REQUESTS_PER_MINUTE`, `LLM_TIMEOUT`. The key is sent only in a request header, never logged, never
returned and never reaches the browser. Every question passes through the model first (no keyword routing); its output is validated against a
strict JSON schema and the approved intent list before anything runs. If the model is unavailable the API answers 503 `llm_unavailable`; if its
output is invalid, 502 `llm_invalid_response`. Calls per request: Parts Intelligence 2 (understanding, grounded wording); Agentic Shopping 1
(understanding; its explanation is built from graph evidence). Identical requests are understood once per process. Token budget: replies are
capped per call type and the wording call receives at most 12 compact evidence records (the summary plus 11 results, every fact kept). The understanding request lists each intent by a one-line hint (`registry.HINTS`), not its full description: 8,608 → 5,598 characters, and the provider-reported request size 1,607 → 1,051 tokens (about 35% less) with two more intents. A reply that is malformed or cut off is retried once with a larger output cap (`question_retry`, 480 tokens; at temperature 0 the same cap would truncate the same way); a second failure is `502 llm_invalid_response`. There is no other router to fall back to, and nothing is queried or invented in that case. Overloads (5xx) are retried twice; a short per-minute rate
limit is waited out once; invalid keys and daily quotas are never retried.

## Tests

`python -m pytest` from `backend/`: unit tests (registry, Cypher read-only/bounded/parameterised audit, grounding, provider layer with a mocked
transport in `tests/test_llm_providers.py`, routing, ambiguity, unsupported questions, data-truth cases) and, when Neo4j is configured, API tests
against the live graph. Live-model tests spend real quota and run only with `RUN_LLM_LIVE_TESTS=true`.

Audits (from `backend/`, read-only): `python scripts/pi_data_audit.py <label>` writes `graph/audits/pi_data_audit_<label>.json` (label, relationship
and data-class counts, part coverage, gaps, integrity checks). `python scripts/pi_question_suite.py <label>` runs the 60-question matrix through the
real model and graph and writes `graph/audits/pi_question_suite_<label>.{json,md}`.

## Known limitations

* Understanding without the model is keyword-based; unusual phrasing needs the model or a rephrase.
* "Request identification" is not offered: there is no backend flow for it. Parts needing identification show what must be confirmed (Identify part).
* The graph links assemblies to parts, not to machines, so machine association of an assembly is reported as not connected.
* Geographic questions return stated city/country only; no distance or coverage reasoning.
* Each question makes several round trips to Aura; typical answers take 0.5 to 2 seconds.
