# Films

| Film | Files | Where it plays |
| --- | --- | --- |
| `hero` | `hero.mp4`, `hero-mobile.mp4`, `hero-poster.webp` | Homepage hero (full bleed) |
| `brand` | `brand*.mp4`, `brand-poster.webp` | Closing section of the homepage |
| `machinery` | `machinery*.mp4`, `machinery-poster.webp` | "Built for the work" section |
| `engineering` | `engineering*.mp4`, `engineering-poster.webp` | Engineering section |
| `service` | `service*.mp4`, `service-poster.webp` | Service section |
| `machine` | optional, not yet made | Every machine page (placeholder until added) |

* Desktop files are 1920×1080 (H.264, no audio, about 2.5–4 MB). `-mobile` files are 960×540 (about 0.6–1 MB), used on phones and when the browser asks to save data.
* Behaviour: muted, looping, plays only while on screen. Below-the-fold films start downloading about 500 px before they scroll into view.
* Fallbacks: reduced motion or Save-Data shows the poster only (no video is downloaded); a video error shows the poster; no file at all shows the placeholder.
* Films are shown in a smaller frame that is feathered into the page on all four sides, over a large ghost word (`word` in `src/data/content.ts`). The generator's corner mark is part of the files; the four section films hide it by enlarging the frame 14% from the top-left (`--crop` in `src/components/media/media.css`), which pushes the mark out of view; the hero keeps a smaller crop and relies on a stronger bottom-right fade because its film also has a "Noordveld" end-logo there. If watermark-free exports replace the files, set `--crop: 1` and drop the corner fade.
* Originals (as downloaded) are kept in `assets-source/videos/`.

Re-encode an original:

```bash
npx remotion ffmpeg -i assets-source/videos/hero-original.mp4 -an -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p -movflags +faststart src/assets/videos/hero.mp4
npx remotion ffmpeg -i assets-source/videos/hero-original.mp4 -an -vf scale=960:-2 -c:v libx264 -preset slow -crf 29 -pix_fmt yuv420p -movflags +faststart src/assets/videos/hero-mobile.mp4
npx remotion ffmpeg -ss 1.2 -i assets-source/videos/hero-original.mp4 -frames:v 1 poster.png
```

Then save `poster.png` as `hero-poster.webp` (quality about 80).
