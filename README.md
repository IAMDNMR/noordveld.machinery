# Noordveld Machinery B.V. — Agentic E-Commerce

A fictional Dutch machinery manufacturer, built for demonstration. Fictional company and demonstration data.

The project keeps all frontend source in `frontend/` and all backend source in `backend/`. The Studio dashboard is available at `/design-studio`; create an application at `/design-studio/new`.

Folder conventions and the required checks are documented in [Code standards](docs/CODE_STANDARDS.md).

| | Folder | What it is |
|---|---|---|
| **Frontend** | [`frontend/`](frontend/) | React 19, TypeScript, Vite. The website, Design Studio dashboard and editor, Parts Store, and Agentic Commerce experience. |
| **Backend** | [`backend/`](backend/) | Python. The Parts Intelligence and Agentic Commerce layer: catalogue and synthetic data, the Neo4j graph (schema, Cypher, validation, audits), and the FastAPI service that serves the Parts Store from the graph. |

The frontend is not the source of truth for business data. The Parts Store reads the backend API, which reads the Neo4j graph. Only the machine
pages and homepage still use data generated from the backend's master files (`frontend/src/data/catalog.generated.ts`); this is temporary.

## Structure

```
.
├── frontend/
│   ├── src/                     website, Studio dashboard and stages, Parts Store, shared chrome
│   ├── agentic-commerce/        second website entry and demo film (+ Remotion project)
│   ├── public/  assets-source/  static files, original media (assets-source is not committed)
│   ├── scripts/                 build-time generators for frontend data and film encoding
│   └── package.json, vite.config.ts, tsconfig.json
├── backend/
│   ├── app/                     FastAPI service: routes, services, graph repositories: api, core, graph, models, schemas, services, intelligence, agents
│   ├── data/
│   │   ├── catalogue/           supplied source catalogue (15 machines, 100 parts)
│   │   └── processed/           complete workbook: catalogue layers + synthetic demo layers + edge list
│   ├── graph/
│   │   ├── cypher/              the import package (1,840 nodes, 3,812 relationships)
│   │   ├── schema/              graph schema and contracts
│   │   ├── validation/          validation queries and expected results
│   │   └── audits/              readiness, quality, provenance, coverage, AuraDB run evidence
│   ├── scripts/                 graph build, offline Cypher check, AuraDB import and validation
│   ├── tests/
│   └── requirements.txt, .env.example
└── README.md
```

The three experiences stay distinct: **Parts Store** (find, view, buy), **Parts Intelligence** (understand, investigate, verify, explore; see
[`backend/INTELLIGENCE.md`](backend/INTELLIGENCE.md)) and **Agentic Commerce** (need to fulfilment).

Run commands for each half are in [`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md).

## Run the frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5180
npm run check
npm test
npm run build
```

## Run the backend (needed by the Parts Store)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000     # http://localhost:8000/health
python -m pip install -r requirements-dev.txt
python -m pytest
```

For local Design Studio project saving, run this backend command instead (PowerShell,
from `backend/`). It keeps the website's catalogue and demo sign-in and enables
SQLite project storage only in explicit local mode:

```powershell
$env:DESIGN_KNOWLEDGE_SOURCE = 'neo4j'
$env:DESIGN_STUDIO_LOCAL_DEV = '1'
$env:APP_ENV = 'local'
$studioDir = Join-Path $env:TEMP 'noordveld-studio-local-site'
New-Item -ItemType Directory -Force -Path $studioDir | Out-Null
$env:DESIGN_STUDIO_LOCAL_DB = Join-Path $studioDir 'studio.sqlite'
python -m uvicorn app.local_site:app --reload --port 8000
```

Projects survive server restarts at that path, but system temporary-file cleanup
can remove them. Export important work. Production storage remains disabled.


Design Studio reads reference packs and domain definitions from Neo4j when
`DESIGN_KNOWLEDGE_SOURCE=neo4j`. To import the versioned repository knowledge,
run `python scripts/import_design_knowledge.py` from `backend/`. The import
adds only `DK*` knowledge nodes and relationships, keeps existing versions,
and refuses changed content under the same version. Imported synthetic and
unverified references retain their provenance. Model additions are stored as
project-specific draft `DKProposedKnowledge` records and do not become verified
shared policy. If Neo4j is unavailable, the configured graph source reports an
error instead of silently switching to files.
