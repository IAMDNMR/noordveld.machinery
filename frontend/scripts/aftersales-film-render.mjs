// Render one film using the existing Remotion installation, then encode delivery files.
// Usage (from frontend/): node scripts/aftersales-film-render.mjs aftersales
//                         node scripts/aftersales-film-render.mjs parts-portal
import { execFileSync } from 'node:child_process'
import { copyFileSync, mkdirSync } from 'node:fs'

const film = process.argv[2]
const compositions = { aftersales: 'AftersalesStory', 'parts-portal': 'PartsPortalStory' }
if (!Object.hasOwn(compositions, film)) throw new Error('Choose aftersales or parts-portal')
const entry = 'agentic-commerce/remotion/aftersales/index.tsx'
const masters = 'agentic-commerce/film-masters'
const sources = 'agentic-commerce/film-sources/aftersales'
mkdirSync(masters, { recursive: true })
mkdirSync('public/films', { recursive: true })
const remotion = (...args) =>
  execFileSync(process.execPath, ['node_modules/@remotion/cli/remotion-cli.js', ...args], {
    stdio: 'inherit',
  })
const ffmpeg = (...args) =>
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...args], { stdio: 'inherit' })

if (!process.argv.includes('--encode-only')) {
  console.log(`${film}: rendering 1080p film with voiceover and original score`)
  remotion(
    'render',
    entry,
    compositions[film],
    `${masters}/${film}-master.mp4`,
    `--public-dir=${sources}`,
    '--crf=18',
    '--concurrency=2',
    '--log=error',
  )
}
console.log(`${film}: encoding web film, captioned download and poster`)
ffmpeg(
  '-i',
  `${masters}/${film}-master.mp4`,
  '-i',
  `${sources}/${film}/captions.vtt`,
  '-map',
  '0:v',
  '-map',
  '0:a',
  '-map',
  '1:0',
  '-c:v',
  'libx264',
  '-preset',
  'fast',
  '-crf',
  '23',
  '-pix_fmt',
  'yuv420p',
  '-c:a',
  'aac',
  '-b:a',
  '160k',
  '-af',
  'loudnorm=I=-16:TP=-1.5:LRA=11',
  '-ar',
  '48000',
  '-c:s',
  'mov_text',
  '-metadata:s:s:0',
  'language=eng',
  '-movflags',
  '+faststart',
  `${masters}/${film}-web.mp4`,
)
ffmpeg(
  '-i',
  `${masters}/${film}-master.mp4`,
  '-vf',
  `subtitles=${sources}/${film}/captions.vtt:force_style='FontName=Arial,FontSize=12,MarginV=28,Outline=1,Shadow=0'`,
  '-c:v',
  'libx264',
  '-preset',
  'fast',
  '-crf',
  '20',
  '-pix_fmt',
  'yuv420p',
  '-c:a',
  'aac',
  '-b:a',
  '160k',
  '-af',
  'loudnorm=I=-16:TP=-1.5:LRA=11',
  '-ar',
  '48000',
  '-movflags',
  '+faststart',
  `${masters}/${film}-captioned.mp4`,
)
remotion(
  'still',
  entry,
  compositions[film],
  `${masters}/${film}-poster.jpg`,
  '--frame=100',
  `--public-dir=${sources}`,
  '--log=error',
)
copyFileSync(`${masters}/${film}-web.mp4`, `public/films/${film}.mp4`)
copyFileSync(`${masters}/${film}-poster.jpg`, `public/films/${film}.jpg`)
copyFileSync(`${sources}/${film}/captions.vtt`, `public/films/${film}.vtt`)
console.log(`${film}: complete`)
