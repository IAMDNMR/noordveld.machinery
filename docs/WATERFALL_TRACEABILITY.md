# Project Waterfall: requirements traceability and POC completion audit

Audit date 2026-10-11, branch `phase5-agentic-commerce` (worktree of `agentic-commerce`). Method: documents and code read, every claim below re-run (tests, live API as three signed-in demo users, live Neo4j, browser).

**How to read the evidence.** *Focused* = a test file named in the row. *Live API* = the real FastAPI app, real session cookie, live Neo4j (`scripts/commerce_agent_flows.py`, `scripts/commerce_live_validate.py`). *Browser* = the running app in the in-app browser. *Mocked* means the test replaces a dependency; a mocked test is never counted as live evidence. *Skipped* tests are listed in section 7 and are never counted as passes.

**Requirement source.** The repo does not hold the original numbered acceptance criteria for phases 1 to 10. Every requirement below is therefore marked **R** (reconstructed from the repository's own requirement documents: `docs/AGENTIC_ECOMMERCE_AUDIT.md`, `docs/ORDER_FLOW.md`, `docs/data-foundation/*`, `docs/LOGISTICS_NETWORK.md`, `docs/LIFECYCLE_WARRANTY.md`, `docs/COMMERCE_CONTEXT_ENGINE.md`, `backend/INTELLIGENCE.md`, `README.md`) or **U** (stated by the user in this project's prompts). Nothing is marked as an original requirement unless the user wrote it.

## 1. Architecture (preserved, unchanged)

| Experience | Stages | Entry |
|---|---|---|
| Parts Intelligence | KNOW, INVESTIGATE, VERIFY, UNDERSTAND | `/parts-intelligence`, `/api/v1/intelligence/*` |
| Agentic Shopping | NEED, EVALUATE, RECOMMEND, PURCHASE | `/agentic-shopping`, `/api/v1/agent/*` |
| Commerce Assistant | one conversational entry for discovery, logistics, warranty | `/commerce`, `POST /api/v1/commerce/agent` |
| Parts Store | catalogue, cart, checkout | `/parts-store`, `/parts-store/checkout` |
| Orders and fulfilment | direct-order lifecycle, allocation, dealer service | `/orders`, `/api/v1/orders/*` |

Parts Intelligence, Agentic Shopping and the Phase 4 context endpoints were not modified in this audit (`git diff` below, section 8).

## 2. Provenance classes

REAL, SOURCE_DERIVED, DERIVED, SYNTHETIC_DEMO, TEST_DATA, INTERNAL_REFERENCE_ONLY, UNKNOWN, NOT_CONNECTED. Live graph: 10,578 nodes, 50,965 relationships. Everything operational (dealers, routes, shipments, work orders, claims, warranties, prices, stock) is `SYNTHETIC_DEMO`; the catalogue is `SOURCE_DERIVED`. No `REAL` operational record exists. Every Commerce answer carries the demonstration disclosure and `confidence.real_world_verified = false`. **Not connected:** carrier tracking, ERP stock, payment provider, live GPS, customs systems, a real warranty or CRM system.

## 3. Phase-by-phase matrix

Status: PASS, PARTIAL, FAIL, NOT VERIFIED.

| # | Phase | Requirement (src) | Expected outcome | Implementation (front / back / graph) | Evidence | Status | Gap, action, retest |
|---|---|---|---|---|---|---|---|
| 1 | Homepage and evolution | Landing page presents the product; evolution video replaces the old hero and timeline (U, commit b1b4048) | Home renders, five videos, nav to all experiences | `HomePage`, `agentic-commerce/src/*`; `/site/overview` | Browser: `/` renders "Built for demanding work.", 5 videos, nav; `test_site.py` 5; vitest | PARTIAL | `npm run lint` reports 12 pre-existing errors in the untouched evolution/launch-film components (`LaunchFilmPlayer.tsx` ref-in-render and a11y, `EvolutionVideoSlot.tsx` missing captions, `CommerceEvolutionHero.tsx`), none on the Commerce paths. Accepted limitation: not changed here (film code, out of the POC scope); retest `npm run lint`. |
| 2 | Auth and roles | Sign-in by demo user; END_USER sees own records, ORDER_PROCESSOR operates; dealer/OEM scope (R) | 401 signed out, 403 other customer's record, role never widened | `session`, `SignInPage`; `app/api/routes/accounts.py`, `commerce/access.py` | `test_roles.py` 24, `test_commerce_api.py` 42, `test_commerce_agent.py` isolation tests; Live API: Anna 403 on Lars's shipment/claim/machine (flow "Security"); Browser: customer got 403 on `SHP-NET-0001` | PASS | none |
| 3 | Synthetic data and Neo4j graph | Canonical, idempotent, provenance-labelled data; integrity checksum (R) | Counts stable, protected nodes untouched | `app/canonical/*`, `backend/data/canonical`, 72-check EU foundation | `test_canonical_*` 49, `test_eu_foundation` 5, `test_integrity_checksum` 3; Live: checksum `f685de95…` unchanged before/after every flow run | PASS | none |
| 4 | Parts Store | Browse, filter, part detail, search, images (R) | 100 parts, filters, detail pages | `PartsStorePage`, `PartDetailPage`; `/parts`, `/catalogue/filters` | `test_api.py` 13, `store.test.ts` 11; Browser: `/parts-store` lists parts, `/parts`, `/catalogue/filters` 200 | PASS | Dev-server console shows `403` for a `@fontsource` file served through the worktree's `node_modules` junction. Environment artefact (vite `fs` allow-list), not an app defect; production build succeeds. |
| 5 | Parts Intelligence | Evidence-led answers over a controlled graph query layer; model never writes Cypher; clarification, not guesses (R) | Intent registry, fixed Cypher, grounded answers | `app/intelligence/*`, `PartsIntelligencePage` | `tests/test_intelligence_*` 212, `tests/parts_intelligence`; vitest 17; Browser: page loads | PASS | Not modified. |
| 6 | Graph visualisation | Part/machine/supplier/dealer graph views (R) | `GET /intelligence/parts/{key}/graph` returns bounded nodes/edges | `PartWorkspace` graph tab | Covered inside `test_intelligence_api.py` and vitest; no dedicated browser drag/zoom run | PARTIAL | Rendering was not exercised in the browser in this audit. NOT VERIFIED visually; backend contract PASS. |
| 7 | Agentic Shopping | NEED, EVALUATE, RECOMMEND, PURCHASE; deterministic ranking; route-based delivery; cart handoff (U/R) | Eligibility rules, ranking fixture tests | `app/agent/*`, `AgenticShoppingPage` | `test_agent*` 67, `test_agentic_shopping` 28, `test_ranking` 7, vitest 14 | PASS | Not modified. Route-based delivery estimate for an unordered part lives here, not in the Commerce Assistant (see B). |
| 8 | Cart and checkout | Persisted cart, quantity limits, checkout to direct order (R) | Add, change, remove, checkout | `cartMachine`, `CheckoutPage`; `/me/cart`, `/checkout` | `cartMachine.test` 4, `checkout.test` 3, `cart.test` 1, `test_direct_order*` 67 | PARTIAL | Browser add-to-cart and a real checkout were not run (they write to the demo account and place an order). Known inconsistency recorded in the audit: quantity limits 99 vs 999 between `routes/orders.py` and `schemas/cart.py`; not changed. |
| 9 | Orders and fulfilment | Order lifecycle NEW to COMPLETED, atomic allocation, exceptions, dealer service, UNKNOWN stock never zero (R, `docs/ORDER_FLOW.md`) | Status transitions, allocation transaction | `OrdersPage`, `OrderDetailPage`; `app/services/order_flow.py` | `test_direct_order` 51, `test_direct_order_graph` 16, vitest `direct.test` 6, `roles.test` 9; Live: `HCME-ORD-000001` owner sees status ALLOCATED, lines, no shipment | PASS | none |
| 10 | Integrated POC | The three business outcomes through one place, with evidence and provenance (U) | Section 4 | `/commerce` | Section 4 | READY WITH ACCEPTED LIMITATIONS | See section 6. |

## 4. The three business outcomes

### A. Parts discovery (R: audit req. 1; U)

| Case | Result | Evidence |
|---|---|---|
| Valid request, machine, approved part, stock, price | RECOMMEND with fitment, approved source, availability, price, ranking, rejected parts and why | Live flow A; Browser "I need a hydrualic pomp for KFT-200" recommends NVM-1050-HY with ranking |
| **Misspelling** ("hydrualic pomp") | **Was a gap**: "No part in the catalogue matches". Now each word is read as the closest word the catalogue itself uses, only for words not in the catalogue and with a close match; every change is shown ("Read “pomp” as “pump”") | `correct_spelling`; tests `test_discovery_reads_a_misspelt…`, `test_spelling_correction_leaves_unknown_words…`; Browser |
| Unknown part ("flux capacitor") | NO_VALID_RECOMMENDATION, nothing offered, word left alone | test above; live probe |
| **Invalid machine id** ("XYZ-999") | Asks for the machine **and now says** "“XYZ-999” is not a machine model in the catalogue; nothing was assumed" | `test_discovery_names_an_invalid_machine_identifier…`; live probe |
| Ambiguous machine (family or type) | Clarification with options; typed reply continues the request | Live flow E; tests |
| Natural phrasing "I need a …" without a keyword | **Was a gap**: rules did not route it (it relied on the model). Rules now route it | `test_discovery_reads_a_misspelt…` (messages begin “I need a …”) |
| Canonical type mismatch / alias-only match | Never recommended; reported with the reason | `test_discovery_never_offers…`; Browser shows "Not offered, and why" |
| Approved part out of stock | NO_AVAILABLE_RECOMMENDATION, no substitution, reason | `test_discovery_an_approved_part_that_is_out_of_stock…` |
| Missing catalogue data | Reported as missing, never zero | `test_commerce_engine.py` 85 |
| Conflicting evidence | Fitment decides, text/aliases never define type | `test_commerce_engine.py` |
| Parts Intelligence evidence-led | Unchanged, 212 tests | section 3 row 5 |
| Agentic Shopping eligibility | Unchanged, 95 tests | section 3 row 7 |

**Status: PASS.** Limitation: spelling correction uses the catalogue's own vocabulary; a typo with no close catalogue word is left as typed.

### B. Orders and logistics visibility (R: audit req. 2; U)

Chain verified end to end: order → order lines → (allocation) → shipment → route → legs → destination → tracking events. Live scenario table (OEM user; customer isolation shown):

| Scenario | Shipment / order | Result |
|---|---|---|
| NL: shop order with no shipment | `HCME-ORD-000001` | Owner sees status ALLOCATED, its lines and "no shipment recorded yet"; another customer 403; OEM sees it |
| **Japan origin, 91-day sea vs air** | `SHP-NET-0001` | IN_TRANSIT on `RTE-NET-JPNL-SEA-ECO` (SEA, ECONOMY), 1 of 4 legs, planned ETA 2026-11-19, no live position (stated). Recorded alternatives: `RTE-NET-JPNL-AIR-EXP` AIR 6 days, 12,675 EUR (85 days faster); `RTE-NET-JPNL-SEA-STD` 45 days, 3,785 EUR. The 91 days exist on that one route record only (`docs/LOGISTICS_NETWORK.md`); no built-in per-mode duration exists in code (test-enforced). Air twin `SHP-NET-0002` linked as the second shipment of the split order |
| W. Europe (UK, delivered) | `SHP-NET-0004` | DELIVERED via `RTE-NET-NLUK-AIR`, ETA = actual 2026-09-23 |
| USA (in transit, overdue) | `SHP-NET-0003` | DEPARTED_PORT on `RTE-NET-NLUSHOU-SEA`, 2 of 4 legs, planned ETA 2026-10-09; **now reported as 2 days past the planned ETA with no delivery recorded and no new ETA** (previously said only "2 days ago") |
| Unknown route | `SHP-0010`, `SHP-0001` (11 seeded) | INSUFFICIENT_DATA / `ROUTE_NOT_DETERMINABLE`; the answer names no route, ETA or faster option |
| Non-existent shipment | `SHP-DOES-NOT-EXIST` | NOT_FOUND |
| Cross-role | all `SHP-NET-*` | Customers 403, OEM 200; `SHP-0010` owner Lars 200, Anna 403 |
| **Africa and other destinations with no shipment** | Lagos, Tema, Durban, Mombasa, Casablanca, USA cities, UK, Zurich, Oslo | **Was a gap**: no way to see Africa logistics at all. New `ROUTE_OPTIONS`: the routes the network records to the place (air 5 / sea 31 days for Lagos; four US destinations; five African ones), each with its own days, cost and legs, labelled **potential routes, none assigned to a shipment** |
| Compare sea and air | any shipment with alternatives | **Was a gap**: shown only for "faster"; now also for "compare", "sea or air", "by air", "alternatives" |
| Unavailable stock | discovery | NO_AVAILABLE_RECOMMENDATION with the stock reason |

Potential versus assigned route: a shipment has exactly one assigned route; `alternative_routes` are recorded alternatives, and `ROUTE_OPTIONS` are lanes for a place with nothing assigned. Both say so.

**Status: PASS WITH ACCEPTED LIMITATIONS.** (1) No Africa *shipment* exists in the graph (lanes only); creating one would be a graph write and was not authorised. (2) A shipment uses one route; split shipments are modelled as several shipments of one order. (3) Delivery time for a specific unordered part is produced by Agentic Shopping, not by the Commerce Assistant; the Assistant gives the network's routes instead. (4) No carrier integration, no live position. (5) The 11 seeded shipments stay `ROUTE_NOT_DETERMINABLE`.

### C. Warranty and component traceability (R: audit req. 3; U)

All verdicts come from `app/lifecycle/rules.py` (ELIGIBLE, NOT_ELIGIBLE, REQUIRES_REVIEW, INSUFFICIENT_DATA); the agent only words them. Live (OEM view; customers lack technician name):

| Case | Claim | Verdict | Reason shown |
|---|---|---|---|
| Authorised dealer, inside period, one work order for two components | CLM-G001 | ELIGIBLE | all checks pass with their sources |
| Installed by a service partner | CLM-G002 | NOT_ELIGIBLE | dealer DLR-002 is SERVICE_PARTNER (dealer attribution) |
| Expired | CLM-G003 | NOT_ELIGIBLE | coverage 2025-02-10 to 2026-02-10; failure 2026-05-01 |
| Second claim, same part | CLM-G004-2 | REQUIRES_REVIEW | prior claim CLM-G004-1 |
| Replaced twice (A→B→C) | CLM-G005 | REQUIRES_REVIEW | replacement history shown |
| Missing documentation | CLM-G006 | INSUFFICIENT_DATA | "Missing: technician, work order, installation record. Nothing is assumed in their place." |
| Unverified/ambiguous component | CLM-G007 | NOT_ELIGIBLE | not an approved part |
| Installed part not approved for the machine (installation ≠ fitment) | CLM-G008 | NOT_ELIGIBLE | no fitment record approves it |
| Unknown claim | CLM-NOPE | NOT_FOUND | "No warranty claim … is recorded" |

Traceability surfaces in the answer: installation date, dealer and authorisation, technician certification, work order, coverage window, replacement history, prior claims, and the check list (PASS/FAIL/UNKNOWN) with sources; follow-ups "who installed it", "installed correctly", "replaced before" are answered from the same records.

**Fixed:** the headline read like a positive claim ("Not eligible: The warranty period is active: Coverage ended…"). It now reads "Not eligible. The check “The warranty period is active” failed: Coverage ended on 2026-02-10…". Wording only; the verdict and the rules are unchanged.

**Status: PASS.** Limitation: all installation, work-order, technician and claim records are `SYNTHETIC_DEMO`; no real warranty system is connected; no photo/PDF evidence attachments exist.

## 5. What this audit changed

Additive, Commerce Assistant layer only; no Phase 4 context field, status or rule changed.

| Change | Files |
|---|---|
| Logistics: comparison on request, overdue statement | `app/commerce_agent/agent.py` (`focus_of`, cues), `answer.py` |
| Discovery: spelling reading, invalid-machine statement, "I need a …" rule, delivery tail removed from the part search | `agent.py` (`correct_spelling`, `DELIVERY_TAIL`), `answer.py` |
| Warranty headline wording | `answer.py` (`_warranty_headline`) |
| `ROUTE_OPTIONS` (potential routes to a place) | `app/commerce/route_options.py`, `network_routes()` on both logistics readers, `ROUTES_NETWORK` query (read-only), agent hook, `answer.py`; UI `RouteOptionsView`, `api/commerce.ts` |
| Tests | `tests/test_commerce_agent.py` (+17), `commerce.test.tsx` (+1), live flow H in `scripts/commerce_agent_flows.py` |

## 6. Known limitations and unconnected systems
No carrier or GPS feed; no real stock system (stock is synthetic and `UNKNOWN` is never zero); no payment provider; no real warranty or CRM system; Africa has lanes but no tracked shipment; no split-line shipment beyond several shipments per order; a typo with no close catalogue word is not corrected; the evolution/launch-film components carry 12 lint errors; dev-server font 403 in this worktree is environmental; browser add-to-cart/checkout and graph-visual interaction were not exercised; branches `phase4h-remediation` and `phase5-agentic-commerce` are local and unpushed.

## 7. Test results
* Backend full suite: **954 passed, 0 failed, 59 skipped** (77 min). The skips are the live-Neo4j and credential-gated tests that only run when a graph is configured for pytest; the same behaviour was run live separately (below), so the skips are not counted as passes.
* `tests/test_commerce_agent.py`: 94 passed (was 79).
* Frontend: vitest 295 passed (10 files); `tsc -b` clean; `vite build` succeeds; `npm run lint`: 0 errors in `src/`, 12 pre-existing errors in the untouched `agentic-commerce/` film components.
* Live agent flows (real API, live Neo4j, three users): 10/10 PASS (A to H, Security, OEM); graph unchanged (10,578 nodes, 50,965 relationships, checksum `f685de95…`).
* Live Phase 4H validator: all checks PASS, engine(files) == engine(graph), snapshot and checksum unchanged, only read queries sent.
* Browser: home, parts store, parts intelligence load; Commerce Assistant misspelling flow recommends NVM-1050-HY; customer gets 403 on another customer's shipment.

## 8. Scope guard
`git diff --stat 63771c5 -- backend/app/intelligence backend/app/agent backend/app/commerce/discovery.py backend/app/commerce/logistics.py backend/app/commerce/warranty.py backend/app/api/routes/commerce.py` is empty: Parts Intelligence, Agentic Shopping and the Phase 4 context builders and endpoints are untouched. `backend/.env` is not staged.
