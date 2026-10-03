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
| `app/intelligence/grounding.py` | rejects model wording that adds numbers, identifiers or claims not in the evidence, or recites every item |
| `app/intelligence/provenance.py` | `data_status` → data class vocabulary |
| `app/intelligence/workspace.py` | the part workspace tabs, insights, graph view, KPIs, suggested questions |
| `app/graph/queries/intelligence.py` | **all** Cypher: read-only, parameterised, bounded (tests enforce this) |
| `app/graph/repositories/intelligence.py` | one method per named query |
| `app/llm/` | provider-independent `LLMClient` (`parse_question`, `resolve_entities`, `generate_grounded_response`); `gemini.py` is the first provider |

## Intents

`PART_SEARCH`, `PART_TO_MACHINE`, `MACHINE_TO_PART`, `PART_TO_CATEGORY`, `PART_TO_ASSEMBLY`, `ASSEMBLY_TO_PART`, `PART_TO_PART`, `PART_TO_SUPPLIER`,
`PART_TO_DEALER`, `PART_TO_LOCATION`, `PART_TO_INVENTORY`, `PART_TO_COMPLIANCE`, `PART_PROVENANCE`, `PART_GRAPH`, `MACHINE_GRAPH`,
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

## Language model (Gemini)

Configured only in `backend/.env`: `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`). The key is sent in a request header, never logged,
never returned and never reaches the browser. The free tier allows 15 requests/minute; the client limits itself to 12 and, when limited, unreachable
or given a bad response, the question is answered deterministically. At most two calls are made per question (understanding only if the rules cannot
decide, then wording).

> `gemini-2.5-flash` is no longer served to newly created API keys (HTTP 404). Set `GEMINI_MODEL` to a current model, for example
> `gemini-3.1-flash-lite`; nothing else changes.

## Tests

`python -m pytest` from `backend/`: unit tests (rules, registry, Cypher read-only/bounded/parameterised audit, grounding, Gemini client with a mock
transport, routing, ambiguity, unsupported questions, data-truth cases) and, when Neo4j is configured, API tests against the live graph. A live
Gemini test runs only when `GEMINI_API_KEY` is set.

## Known limitations

* Understanding without the model is keyword-based; unusual phrasing needs the model or a rephrase.
* "Request identification" is not offered: there is no backend flow for it. Parts needing identification show what must be confirmed (Identify part).
* The graph links assemblies to parts, not to machines, so machine association of an assembly is reported as not connected.
* Geographic questions return stated city/country only; no distance or coverage reasoning.
* Each question makes several round trips to Aura; typical answers take 0.5 to 2 seconds.
