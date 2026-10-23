# Aftersales and Parts Portal films

Two original 1920×1080, 24 fps motion-graphics films. The narrated stories use the
site's existing photography, product images, logo, Inter font and teal identity.

The Aftersales film explains the wider business operating model: OEM, dealer and
customer responsibilities, dealer onboarding, dealer systems and OEM portals,
parts supply and returns, service jobs, warranty claims, and the installed base.
It does not present those processes as already implemented product features.

The Parts Portal film explains the application's current scope: machine and
part search, all ten catalogue categories, part details and fitment, recorded
prices and availability, direct checkout, delivery options and order status.
Prices and delivery promises are not invented. Example data remains labelled.

## Editorial coverage

| Aftersales business explainer                                   | Parts Portal walkthrough                                 |
| --------------------------------------------------------------- | -------------------------------------------------------- |
| Why the relationship continues after the machine sale           | One place for machine parts and ordering                 |
| Manufacturer, independent dealer and customer responsibilities  | Manufacturer, model and part search                      |
| Dealer checks, agreements, access, training and data validation | All ten current catalogue categories                     |
| Dealer-owned systems and the OEM portal layer                   | Part number, description, category and recorded fitment  |
| Parts identification, supply, back orders, delivery and returns | Recorded price, stock and supply/source information      |
| Diagnosis, job planning, repair and service history             | Cart, customer, delivery, receiver and full order review |
| Warranty evidence, review, decision and reimbursement           | Transport, dispatch context and recorded order status    |
| Customer/machine/dealer installed-base data and shared history  | Clearly labelled demonstration data                      |
| Service continuity and the lifetime customer relationship       |                                                          |

The business explainer describes an illustrative operating model. It is not a
claim that dealer onboarding, service booking or warranty reimbursement is
already implemented by this website. The existing Spark and Agentic Commerce
films are not changed by this work.

## Rebuild

From `frontend/`, using the already installed Remotion, FFmpeg, edge-tts, NumPy
and SciPy dependencies:

```sh
python scripts/aftersales-film-audio.py
node scripts/aftersales-film-render.mjs aftersales
node scripts/aftersales-film-render.mjs parts-portal
```

Edit `agentic-commerce/film-sources/aftersales/story.json` for narration and
chapter headings. Voice-over uses `en-US-AndrewNeural`, as in the existing
Agentic Commerce film. The audio script sends only this public narration to
Microsoft's online TTS service. Cached scene audio and word boundaries regenerate
when the narration or voice settings change. Timing and caption cues derive from
the returned word boundaries, not an estimated reading speed.

The original workflow film's local score synthesizer supplies the quiet music
bed. No downloaded music, new package dependencies or API credentials are used.

## Deliverables

- `public/films/{aftersales,parts-portal}.mp4`: web-encoded films, voice-over,
  music and embedded English subtitles.
- Matching `.jpg` posters and `.vtt` English captions for native web playback.
- `agentic-commerce/film-masters/*-captioned.mp4`: presentation/download versions
  with visible captions, including when the player cannot display subtitle tracks.
- `agentic-commerce/film-masters/*-master.mp4`: high quality clean masters.
- Source scene audio, timing, captions and transcripts remain in
  `agentic-commerce/film-sources/aftersales/` for future edits.

Completed video, poster and caption files are copied together to `public/films`
only after rendering and encoding. Both web and download audio is normalised.
Use `--encode-only` on the render script to re-encode an existing master.
Masters are already excluded from Git by the repository's existing ignore rule.
The website players load on demand, never autoplay, have native controls and
enable the English captions by default. Existing films remain unchanged.

## Changed-file map

- `src/components/media/OverviewVideoSlot.tsx` and `overview-video-slot.css`:
  replace the placeholder with responsive native playback and caption controls.
- `src/sections/aftersales/Hero.tsx` and `src/pages/PartsStorePage.tsx`:
  select the appropriate film for each page.
- `src/sections/aftersales/aftersales.test.tsx`: update the existing film test;
  no extra test cases are added.
- `agentic-commerce/remotion/aftersales/{index,CinematicFilms,BusinessVisuals}.tsx`:
  composition setup, shared motion design, business and catalogue graphics.
- `scripts/aftersales-film-{audio.py,render.mjs}`: reproducible narration,
  score, timing, subtitles, rendering, encoding and final asset publication.
- `agentic-commerce/film-sources/aftersales/story.json`: the authored stories.
- Matching `aftersales.json` / `parts-portal.json` and `*-transcript.txt`:
  generated scene timing, caption cues and narration transcripts.
- `film-sources/aftersales/aftersales/{0..8}.mp3` and matching `.words.json`:
  nine narrated scenes and their word timing/cache metadata.
- `film-sources/aftersales/parts-portal/{0..6}.mp3` and matching `.words.json`:
  seven narrated scenes and their word timing/cache metadata.
- Each source subfolder's `music.mp3` and `captions.vtt`: score and captions.
- `public/films/aftersales.{mp4,jpg,vtt}` and
  `public/films/parts-portal.{mp4,jpg,vtt}`: the six website deliverables.
- This README: rebuilding, editorial boundaries and the file handoff.

Backend files, credentials, dependencies, deployment configuration, existing
videos and unrelated concurrent Studio changes are outside this film work.
