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

## Data: nothing invented

The master data lives in the backend: `../backend/data/catalogue/noordveld-parts-catalog.xlsx` is the source of truth, and
`../backend/data/processed/` holds the complete workbook. `npm run data` (needs `pip install openpyxl`) regenerates
`src/data/catalog.generated.ts` from the catalogue: 15 machines and 100 parts. The store and the film data are generated the same way by
`scripts/build-store-data.py` and `scripts/build-film-data.py`. **This local generated data is temporary**: the frontend will read the backend API instead.

* Machine names, models, plants and brand/origin are used exactly as written.
* Machine pages show only catalog fields: model, machine type, plant, brand/origin, plus the number of
  catalogued parts. **There are no horsepower, weight, capacity or dimension figures because the catalog has none.**
* Related parts are the catalog parts that list the model as compatible. KFT-120 has none in the catalog.
* Two things are editorial and live in `src/data/machines.ts` / `content.ts`: the grouping of machine
  types into Loading, Material handling and Conveying, and the five broad industry categories.
* Plant map positions come from approximate coordinates; the map is a schematic, no map API.

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
