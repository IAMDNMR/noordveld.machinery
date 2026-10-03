# Noordveld Machinery B.V. — Agentic E-Commerce

A fictional Dutch machinery manufacturer, built for demonstration. Fictional company and demonstration data.

The project has two independent halves.

| | Folder | What it is |
|---|---|---|
| **Frontend** | [`frontend/`](frontend/) | React 19, TypeScript, Vite. The website, the Parts Store UI and the Agentic Commerce experience (scroll-driven evolution hero, theory section, demo film). |
| **Backend** | [`backend/`](backend/) | Python. The Parts Intelligence and Agentic Commerce layer: catalogue and synthetic data, the Neo4j graph (schema, Cypher, validation, audits), and the API scaffolding that will serve the frontend. |

The frontend is not the source of truth for business data. It still presents data generated from the backend's master files
(`frontend/src/data/*.generated.ts`, built by `frontend/scripts/`); this is temporary and will be replaced by calls to the backend API.

## Structure

```
.
├── frontend/
│   ├── src/                     website, Parts Store, shared chrome
│   ├── agentic-commerce/        second page of the site: evolution hero, theory, demo film (+ Remotion project)
│   ├── public/  assets-source/  static files, original media (assets-source is not committed)
│   ├── scripts/                 build-time generators for frontend data and film encoding
│   └── package.json, vite.config.ts, tsconfig.json
├── backend/
│   ├── app/                     FastAPI scaffolding (health route only): api, core, graph, models, schemas, services, intelligence, agents
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

Run commands for each half are in [`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md).

## Run the frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5180
npm run typecheck
npm run build
```

## Run the backend scaffolding

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000     # http://localhost:8000/health
python -m unittest discover -s tests -t .
```
