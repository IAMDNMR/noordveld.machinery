# Images and films: status and what to generate

Drop a file in the folder shown and it replaces its placeholder automatically. No code change. Formats: `.webp` (best), `.jpg`, `.png` or `.avif`.
Append `?placeholders` to any page URL to see which slots are still empty and their expected size.

## Already in place

| Asset | Status |
| --- | --- |
| Logo (`src/assets/brand/`) | Done. Transparent and reversed versions are generated from your file; original kept in `assets-source/brand/`. |
| 15 machine images | Done (BTS-750 and BTS-900 added from your downloads): all 15 models. Converted to WebP (11.6 MB → 2.1 MB). Originals in `assets-source/machines/`. |
| 3 plant images | Done: Assen, Lingen, Coevorden. |
| 5 editorial images | Done: machinery-at-work, mechanical-detail, engineering, work-environment, service. |
| Agentic E-Commerce film | Done (`public/evolution-film-*.mp4`). |

## Still needed

No images or films are missing.

### Films

Done: hero, brand, machinery, engineering and service are in `src/assets/videos/` (desktop and mobile cuts plus posters). Only the optional `machine.mp4` (shown on every machine page) is not made.

## Quality notes on what you already made

* **Resolution:** the machine images are 1200 px wide. They look good in cards, but the featured NV-4500 (full width, 21:9) and the machine page heroes will look soft on large or retina screens. If you regenerate or upscale, aim for 2400 px wide.
* **Aspect ratio:** `BTS-500`, `KFT-800` and `NV-4500` are 16:9; the other ten are 4:3. The site crops to fit, so nothing breaks, but regenerating those three at 4:3 gives the tightest consistency.
* **Optional:** a 1200 × 630 share image (`public/og-image.jpg`) for link previews.
