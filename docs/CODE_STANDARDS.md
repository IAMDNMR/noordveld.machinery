# Code organization and checks

All browser source lives in `frontend/`; all Python service source lives in `backend/`.

## Frontend

- `src/pages/`: route composition and page styles.
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

Routes in `app/api/routes/` validate requests and enforce identity, organization permissions, and project access. Business logic lives in domain/service modules. Schemas live in `app/schemas/`; business data access lives in repository modules.

Project management uses optimistic revision checks and audit events in every store adapter. Archive and Trash preserve immutable history. Trash has no automatic expiration or permanent-delete endpoint. Restoring design content cannot implicitly change a project's lifecycle. Lifecycle metadata is excluded from design approval digests and omitted on older project documents.

From `backend/`:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check app
python -m ruff format --check app scripts/serve_studio.py
python scripts/test_offline.py -q
```

The offline runner disables external connections and `.env` loading. Database/model integration tests remain opt-in; skipped external tests do not establish production readiness. Ruff currently covers maintained application source; historical data/import scripts are retained separately.
