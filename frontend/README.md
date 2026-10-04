# Noordveld Machinery B.V. — frontend

A fictional Dutch machinery manufacturer, built for demonstration. React 19, TypeScript, Vite, React Router.
Fictional company and demonstration data.

## Run

```bash
npm install
npm run dev          # http://localhost:5180
npm run typecheck
npm run lint
npm run build        # dist/  (single-page app: serve index.html for unknown paths)
npm run preview
```

Everything is one project and one server (`npm run dev`, port 5180). The nav bar and footer are shared components (`src/components/chrome/`) used by both pages.

## Routes

| Route | Page |
| --- | --- |
| `/` | Homepage (hero, machines, built for the work and industries, company, plants, service, parts, Agentic E-Commerce teaser, final CTA) |
| `/machines` | All 15 machines, grouped |
| `/machines/:model` | One reusable template for all 15 (`nv-2100` … `bts-900`) |
| `/agentic-commerce/` | Agentic Commerce: the evolution hero, how commerce evolved, the demo film. A second page of the same site (`agentic-commerce/`), with the same nav bar and footer: the pinned evolution hero, the theory section and the demo film. |
| `/legal`, `/privacy` | Short demonstration notices |

Nav items Industries, Service, Parts and Company scroll to sections on the homepage.

## Data: nothing hardcoded

**The frontend holds no business data.** Machines, parts, prices, stock, suppliers, dealers, customers, delivery and
recommendations all come from the backend API (`src/api/`, proxied to `localhost:8000` in dev), which reads the Neo4j graph.
Start the API before opening the site. Change the graph and the pages change, with no frontend code change.

* Website (home sections, `/machines`, `/machines/:model`): `GET /api/v1/site/overview`, loaded once and shared (`src/data/site.ts`).
  Machine families, brands, acquisition years, plants and part counts are the graph's; headings such as "Three plants" are computed.
* Agentic Shopping (`/agentic-shopping`): `/api/v1/agent/*` (request, steps, example requests).
* Agentic E-Commerce launch film: `GET /api/v1/showcase/launch-film` (`agentic-commerce/src/components/launch/launchData.ts` loads it
  before the film's acts load).
* Synthetic demo records keep their "(demo)" names and data status; machine application profiles are labelled as demo data.
* Map positions are city-centre coordinates supplied by the backend (geography, not business data). The graph stores no coordinates.
* `src/lib/noBusinessData.test.ts` fails if a part number, machine code, record id, price or demo record name is written into any
  frontend source file. The one reviewed exception is the abstract "options A, B, C" concept illustration on the Agentic E-Commerce page.

### Parts Intelligence (`/parts-intelligence`)

Question workspace and part investigation drawer (12 lazily loaded tabs) over `/api/v1/intelligence`. State is in the URL (`?q=`, `?part=`, `?tab=`), so
refresh and back/forward work. Code: `src/components/intelligence/`, `src/api/intelligence*.ts`, `src/pages/PartsIntelligencePage.tsx`. It reuses the
Parts Store's `PartImage`. Nothing in it names a catalogue entry (tested). Architecture and limits: [`../backend/INTELLIGENCE.md`](../backend/INTELLIGENCE.md).

### Parts Store (API-driven)

`src/api/` is the only code that calls the network (typed client, parts, filters, cart quote). `src/lib/storeQuery.ts` maps the URL to API filters,
`src/lib/assets.ts` resolves part photos (`src/assets/parts/<part-number>/main.jpg`; no file means the Noordveld placeholder, no component change needed).
Routes: `/parts-store`, `/parts-store/:partNumber`, `/parts-store/checkout` (a prepared review only; order placement is not connected).
`npm test` runs unit tests, including an audit that fails if any store source contains a part number or machine model.

* Machine pages show only graph fields: model, machine type, family, plant, brand, plus the number of recorded parts.
  **There are no horsepower, weight, capacity or dimension figures.**
* Related parts are the parts recorded as fitting the machine (FITS). KFT-120 has none.

## Images and films

All media are placeholders that already have their final layout. Add a file and the placeholder is replaced
automatically, with no code change and no failed requests for missing files (`src/lib/assets.ts`).
Specs are in `src/assets/README.md`, and each of the 15 `src/assets/machines/<model>/` folders has its own.

* `MachineImagePlaceholder`, `PlantImagePlaceholder`, `EditorialPlaceholder`, `VideoPlaceholder`: `src/components/media/Placeholders.tsx`
* Append `?placeholders` to a URL to see each slot's expected path and ratio on screen.
* Films (hero, brand, machinery, engineering, service) are in `src/assets/videos/` and play muted and looping while on screen, with mobile cuts and poster fallbacks. See `src/assets/videos/README.md`.

## Design system

Tokens in `src/styles/tokens.css`: warm white, graphite and charcoal carry the identity; teal `#00BFA5` is used
only for primary actions, links, active states and small highlights. Breakpoints: 760 / 1100 / 1440 px.
Motion is slow and weighted, and respects `prefers-reduced-motion`.

## Not included (later phases)

Backend API integration, AI, real inventory, payments, supplier integrations, portals, CMS.
