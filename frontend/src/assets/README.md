# Assets

```
assets/
  machines/<model>/main.webp, detail.webp   (15 folders, one per catalogue model)
  plants/<assen|lingen|coevorden>.webp
  brand/            logo.png, logo-reversed.png, mark.png
  videos/<hero|brand|machinery|engineering|machine>.mp4
```

Files are discovered at build time (`src/lib/assets.ts`). Missing file = placeholder shown; no failed requests.
Append `?placeholders` to a page URL to see each placeholder's expected path and ratio on screen.
