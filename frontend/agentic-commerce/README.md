# From buying what you know to solving what you need

Phase 1: the Commerce Evolution and Agentic E-Commerce introduction page. React + TypeScript + Vite.
Brand colour: teal `#00BFA5` (tokens in `src/styles/tokens.css`).

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm run typecheck    # tsc
npm run lint         # oxlint
npm run build        # production build to dist/
```

## The film

One 30-second film, built as a deterministic Remotion composition (`src/film/`): icons, type and a drifting teal light,
no photography. The page plays the rendered files with no clicks (muted, looping, only while on screen);
reduced-motion visitors get a poster with controls.

```bash
npm run film:preview           # Remotion Studio
npm run film:render            # public/evolution-film-16x9.mp4   (1920x1080)
npm run film:render:square     # public/evolution-film-1x1.mp4    (1080x1080, used on phones)
npm run film:render:vertical   # out/evolution-9x16.mp4           (1080x1920)
npm run film:poster            # public/evolution-film-*.jpg posters
```

Rendered files are large; encode for the web with
`npx remotion ffmpeg -i in.mp4 -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p -movflags +faststart -an out.mp4`.

## Demonstration data

The recommendation interaction (`src/lib/recommend.ts`) runs on fixed sample data and simple arithmetic.
It is not connected to inventory, suppliers, payments or any model. `CommerceRecommendation` is the
interface a real source can implement later.

## Asset slots

`VisualPlaceholder` (`src/components/ui/Placeholders.tsx`) marks backdrop slots for generated imagery
(commerce, quick-commerce, agentic-commerce) with purpose, size, ratio and direction. Add
`?placeholders` to the URL to see them on screen.
