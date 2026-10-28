# Assets

```
assets/
  machines/<model>/main.webp, detail.webp   one folder per catalogue model
  parts/<part-number>/main.webp             one folder per part, lower-case part number
  plants/<assen|lingen|coevorden>.webp
  editorial/<name>.webp                     machinery-at-work, mechanical-detail, engineering, work-environment, service
  brand/                                    logo.webp, logo-reversed.webp, mark.webp (PNG originals kept beside them)
  videos/<film>.mp4, <film>-mobile.mp4, <film>-poster.webp
```

Files are discovered at build time (`src/lib/assets.ts`). A missing file shows a placeholder; there are no failed requests. Append `?placeholders` to a page URL
to see each placeholder's expected path and ratio on screen. Dropping a file in the right folder replaces its placeholder; no code change.

## Formats and sizes

All raster images are WebP. Originals of everything converted or re-encoded are kept, outside git, in `frontend/assets-source/optimised-originals/`.

| Slot                                                       | Ratio                          | Target size                  |
| ---------------------------------------------------------- | ------------------------------ | ---------------------------- |
| Machine `main.webp` (cards, machine hero, featured visual) | 4:3, also shown at a 21:9 crop | 2400 x 1800 px, under 300 KB |
| Machine `detail.webp` (optional)                           | 4:3                            | 2000 x 1500 px, under 250 KB |
| Part `main.webp`                                           | 1:1                            | 800 x 800 px                 |
| Plant and editorial pictures                               | about 2:1                      | at most 1600 px wide         |
| Video posters                                              | 16:9                           | 1920 x 1080 px               |

Machine image direction: studio-lit machine on a warm neutral background, three-quarter view, no people, no text.

## Machine folders

| Folder              | Machine                       |
| ------------------- | ----------------------------- |
| `machines/bts-100/` | Belt Conveyor Module          |
| `machines/bts-250/` | Loader Arm Assembly (machine) |
| `machines/bts-500/` | Roller Conveyor               |
| `machines/bts-750/` | Transfer Cart                 |
| `machines/bts-900/` | Pallet Elevator               |
| `machines/kft-120/` | Pallet Truck                  |
| `machines/kft-200/` | Electric Forklift             |
| `machines/kft-450/` | Reach Truck                   |
| `machines/kft-600/` | Loader Arm Unit               |
| `machines/kft-800/` | Stacker Crane                 |
| `machines/nv-2100/` | Skid Steer Loader             |
| `machines/nv-3200/` | Compact Wheel Loader          |
| `machines/nv-4500/` | Wheel Loader                  |
| `machines/nv-6000/` | Telehandler                   |
| `machines/nv-7500/` | Articulated Loader            |

## Quality notes

- The machine images are 1200 px wide: fine in cards, slightly soft in the full-width 21:9 featured view on large screens. Regenerate at 2400 px wide if possible.
- `BTS-500`, `KFT-800` and `NV-4500` are 16:9, the others 4:3. The site crops to fit; regenerating those three at 4:3 gives the tightest consistency.
- Optional: a 1200 x 630 share image (`public/og-image.jpg`) for link previews, and the optional `machine.mp4` film shown on every machine page.
