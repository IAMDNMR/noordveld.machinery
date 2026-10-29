// Web-encodes the workflow film master into public/ (the Spark page's "From need to order" slot): film, poster and captions.
// Usage (from frontend/, after `npm run film:workflow`): node scripts/workflow-film-encode.mjs
import { execFileSync } from 'node:child_process'
import { copyFileSync } from 'node:fs'

const master = 'agentic-commerce/film-masters/workflow-16x9.mp4'
const ffmpeg = (...args) => execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...args], { stdio: 'inherit' })

ffmpeg('-i', master, '-c:v', 'libx264', '-preset', 'slow', '-crf', '26', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-movflags', '+faststart', 'public/agentic-workflow-film.mp4')
// poster: the closing title card, once every line has appeared
ffmpeg('-ss', '96', '-i', master, '-frames:v', '1', '-q:v', '3', 'public/agentic-workflow-film.jpg')
copyFileSync('agentic-commerce/film-sources/workflow/captions.vtt', 'public/agentic-workflow-film.vtt')
