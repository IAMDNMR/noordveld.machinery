# Backend

Python. Parts Intelligence and Agentic Commerce: data, graph, and (next phase) the API.

Status: **architecture only.** `app/main.py` exposes `/health`; no business logic yet.

## Layout

| Path | Purpose |
|---|---|
| `app/main.py` | API entry point (health route only) |
| `app/api/routes/` | HTTP routes, one module per resource (later) |
| `app/core/` | configuration (`config.py` reads `backend/.env`; the password never appears in repr or logs) |
| `app/graph/` | Neo4j client, named queries and repositories (later) |
| `app/services/`, `app/intelligence/`, `app/agents/` | business logic, Parts Intelligence, Agentic Commerce orchestration (later) |
| `app/models/`, `app/schemas/` | domain models and API schemas (later) |
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
python -m uvicorn app.main:app --reload --port 8000      # API scaffolding: http://localhost:8000/health
python -m unittest discover -s tests -t .                # scaffold checks
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
