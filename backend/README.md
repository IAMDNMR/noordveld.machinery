# Backend

Python. Parts Intelligence and Agentic Commerce: data, graph, and the catalogue API that the Parts Store reads.

The API only **reads** the validated Neo4j graph; it has no second catalogue and never writes. Layers: routes (`app/api`) call services
(`app/services`), which call repositories (`app/graph/repositories`), which run the named Cypher in `app/graph/queries` through `GraphClient`.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/parts` | search, filter (`category`, `machine`, `availability`, `orderable`), sort, paginate |
| `GET /api/v1/parts/{key}` | part detail by part number or id: fitment, specifications, legacy references, price, stock, suppliers, compliance, assemblies, related |
| `GET /api/v1/catalogue/filters` | categories, machines and availability states with live counts |
| `POST /api/v1/cart/quote` | prices part ids and quantities; stateless, places no order |
| `GET /health`, `/health/ready` | liveness; readiness (graph reachable) |

Errors are `{"error": {"code", "message"}}`. Unknown values stay `null`; nothing is defaulted, inferred or converted to zero. Related parts carry the
graph relationship that links them and never imply interchangeability.

## Layout

| Path | Purpose |
|---|---|
| `app/main.py` | app factory: CORS, error handlers, routers |
| `app/api/` | routes and dependencies |
| `app/core/` | configuration (`config.py` reads `backend/.env`; the password never appears in repr or logs) |
| `app/graph/` | Neo4j client, named queries, repositories |
| `app/services/`, `app/intelligence/`, `app/agents/` | services (search, detail, cart quote); `intelligence/` and `agents/` are reserved |
| `app/models/`, `app/schemas/` | API response models |
| `data/catalogue/` | `noordveld-parts-catalog.xlsx`: the supplied catalogue |
| `data/processed/` | `noordveld-complete-dataset-synthetic-demo.xlsx`: catalogue layers plus synthetic demo layers (`SYN_` sheets) |
| `graph/cypher/` | the Neo4j import package, files `00` to `25`, idempotent |
| `graph/schema/` | graph schema and relationship, identifier and provenance contracts |
| `graph/validation/` | validation queries, expected results, read-only pre-flight inspection |
| `graph/audits/` | readiness, quality, provenance and coverage reports, and the AuraDB run evidence |
| `scripts/` | graph build, offline check, AuraDB import / validation / report |

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env ; then fill in the Neo4j values
```

## Run

```bash
python -m uvicorn app.main:app --reload --port 8000      # http://localhost:8000/docs
python -m pip install -r requirements-dev.txt
python -m pytest                                         # API tests run against the live graph; skipped without Neo4j credentials
```

## Graph tooling (run from `backend/`)

```bash
python scripts/graph_build.py          # rebuild audits, schema, Cypher and validation from data/ (never contacts Neo4j)
python scripts/graph_cypher_check.py   # offline check: structure and idempotency of graph/cypher
python scripts/aura_import.py preflight   # read-only inspection of the AuraDB database
python scripts/aura_validate.py           # read-only post-import validation
```

`aura_import.py import` writes to AuraDB and only proceeds into an empty database. The graph is already imported and validated
(1,840 nodes, 3,812 relationships; see `graph/audits/neo4j_import_report.md`).

## Data rules

Fitment comes only from the catalogue. Suppliers, dealers, stock, prices, orders, shipments and service are synthetic demo data and carry
`data_status = SYNTHETIC_DEMO`. Missing stays missing, conditional stays conditional, nothing is inferred. See `graph/schema/`.
