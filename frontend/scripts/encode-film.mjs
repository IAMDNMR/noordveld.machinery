// Web-encodes the full-quality film masters (agentic-commerce/film-masters) into public/.
import { execFileSync } from 'node:child_process'

const cuts = [
  ['16x9', 'evolution-film-16x9'],
  ['1x1', 'evolution-film-1x1'],
]
for (const [master, out] of cuts) {
  execFileSync(
    'npx',
    ['remotion', 'ffmpeg', '-y', '-i', `agentic-commerce/film-masters/${master}.mp4`, '-c:v', 'libx264', '-preset', 'slow', '-crf', '24', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', `public/${out}.mp4`],
    { stdio: 'inherit', shell: true },
  )
}
