# Code organization and checks

All browser source lives in `frontend/`; all Python service source lives in `backend/`.

## Frontend

- `src/pages/`: route composition and page styles.
- `src/components/studio/dashboard/`: project cards and accessible management dialogs.
- `src/components/studio/views/`: the nine Studio stages and application preview.
- `src/components/studio/model/`: pure definition parsing, editing, and validation.
- `src/components/studio/canvas/`: reusable component registry, renderer, and screen canvas.
- `src/components/studio/diagrams/`: process and entity relationship diagrams and layout functions.
- `src/api/`: typed HTTP clients; components do not assemble service URLs themselves.
- `src/store/`, `src/hooks/`, `src/lib/`: session state, shared hooks, and pure helpers.
- `agentic-commerce/`: the existing second website entry and Remotion film source; still inside the frontend folder.
- `config/vite.studio.ts`: the optional separate Studio preview configuration.

Use React function components, TypeScript strict checking, named domain types, semantic controls, explicit loading/error/empty states, and cancellation for reads tied to a component lifetime. Derive state from props where possible. Keep persistence and authorization on the server. Comments explain intentional effect triggers or narrow linter exceptions. The existing supplied evolution video still needs a verified caption asset; its exception is documented in that component.

From `frontend/` (Node 22.12 or newer):

```powershell
npm ci
npm run check
npm test
npm run build
```

`check` runs TypeScript, Oxlint with warnings rejected, and Prettier. `npm run format` applies the shared format. Original media, generated catalogue data, and build outputs are excluded from formatting.

## Backend

Routes in `app/api/routes/` validate requests and enforce identity, organization permissions, and project access. Business logic lives in domain/service modules. Schemas live in `app/schemas/`; project store adapters live in `app/design_studio/`. Generated-app Python/JavaScript templates remain next to their generator because they are exported artifacts, not website source.

Project management uses optimistic revision checks and audit events in every store adapter. Archive and Trash preserve immutable history. Trash has no automatic expiration or permanent-delete endpoint. Restoring design content cannot implicitly change a project's lifecycle. Lifecycle metadata is excluded from design approval digests and omitted on older project documents.

From `backend/`:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check app
python -m ruff format --check app scripts/serve_studio.py
python scripts/test_offline.py -q
```

The offline runner disables external connections and `.env` loading. Database/model integration tests remain opt-in; skipped external tests do not establish production readiness. Ruff currently covers maintained application source and the Studio launch helper; historical data/import scripts are retained separately.

## Local Studio and dashboard

From the repository root, start the backend and frontend in separate terminals:

```powershell
python backend/scripts/serve_studio.py --port 8000
npm --prefix frontend run dev
```

Open `/design-studio` for the project dashboard and `/design-studio/new` to create an application. Existing project URLs are unchanged. The dashboard refreshes when focused, every 30 seconds while visible, or using Refresh. It derives stage progress, validation issues, approval status, and activity from saved projects; an optional runtime indicator reflects the actual local launcher.

The launch helper enables local mode and defaults to the existing `noordveld-studio-local-site/studio.sqlite` temporary data location. It honors explicit storage environment variables. For this workspace's migrated Neo4j projects, keep `DESIGN_STUDIO_LOCAL_GRAPH_NAMESPACE=studio-local-site` and `DESIGN_KNOWLEDGE_SOURCE=neo4j` when starting the backend. Never switch storage namespaces to conceal a connection problem.

For a separate frontend port, `npm --prefix frontend run dev:studio` uses 5202 and proxies to 8022 by default. Override `STUDIO_WEB_PORT` and `STUDIO_API_TARGET` if needed. Use a separate explicit local database path for isolated testing.

The cleanup manifest is `docs/CODE_CLEANUP_2026_10_19.json`. Unreachable legacy screens were removed after dependency checks; working Studio models and diagrams were moved. Original deleted source and duplicate assets were backed up under the temporary directory recorded in that manifest. Source catalogue, knowledge releases, operational APIs, and user projects are retained.
