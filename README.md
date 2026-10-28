# Noordveld Machinery

Machinery, Aftersales, Parts Portal and Spark: parts intelligence and assisted commerce.

Source is separated into `frontend/` (React, Vite and TypeScript) and `backend/` (FastAPI).

## Run locally

From `frontend/`:

```sh
npm install
npm run dev
```

From `backend/`, in the configured Python environment:

```sh
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The website is available at http://localhost:5180. Keep credentials in the backend environment; never commit them.

## Checks

From `frontend/`:

```sh
npm run check
npm test
npm run build
```

From `backend/`:

```sh
python -m pytest
```

Catalogue and operational records use the configured Neo4j connection. Demo commercial records are labelled in the interface. Orders require explicit user confirmation.
