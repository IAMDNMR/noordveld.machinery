import type { CSSProperties, ReactNode } from 'react'
import { AbsoluteFill, Audio, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import film from '../../../film-sources/workflow/film.json'
import timing from '../../../film-sources/workflow/timing.json'

/*
  The workflow film: the real application screens (captured from the running app), the scene text and the voice-over clips all live in
  film-sources/workflow (film.json, timing.json, shots/, vo/, music.mp3). This file is only the motion design: nothing in it is business data.
  Render: npm run film:workflow  (public dir = film-sources/workflow)
*/

export const WORKFLOW_FPS = film.fps
export const WORKFLOW_FRAMES = Math.ceil(timing.total * film.fps)

type Key = number[] // [progress, x, y, visible width] in page pixels of the screenshot
type Highlight = number[] // [from, to, x, y, w, h]
interface Shot { image: string; w: number; h: number; until: number; camera: Key[]; highlights: Highlight[] }
interface Scene { id: string; kind: string; vo: string; title: string; kicker?: string; image?: string; rail?: number; chips?: string[]; words?: string[]; shots?: Shot[] }
const SCENES = film.scenes as Scene[]
/** The chapter number shown on each screen scene (hook and outro are not numbered) */
const NUMBERS = SCENES.map((_, i) => SCENES.slice(0, i + 1).filter((x) => x.kind === 'screen').length)

const INK = '#16201e'
const INK2 = '#4a4f53'
const INK3 = '#6b7175'
const TEAL = '#00bfa5'
const TEAL_INK = '#00756a'
const PAPER = '#f5f3ee'
const FONT = "'Inter Variable', Inter, system-ui, sans-serif"

const ease = Easing.bezier(0.33, 0, 0.2, 1)
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
const ramp = (t: number, a: number, b: number) => interpolate(t, [a, b], [0, 1], { ...clamp, easing: ease })
const win = (t: number, a: number, b: number, edge: number) => Math.min(ramp(t, a, a + edge), 1 - ramp(t, b - edge, b))

/* Browser frame geometry (canvas pixels) */
const FRAME = { x: 700, y: 150, w: 1124, h: 703, bar: 42 }
const ASPECT = FRAME.w / FRAME.h

function cameraAt(keys: Key[], p: number, imgH: number): { x: number; y: number; w: number } {
  let k = 0
  while (k < keys.length - 2 && p >= keys[k + 1][0]) k++
  const a = keys[k]
  const b = keys[Math.min(k + 1, keys.length - 1)]
  const u = b[0] === a[0] ? 1 : interpolate(p, [a[0], b[0]], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) })
  const w = a[3] + (b[3] - a[3]) * u
  const x = a[1] + (b[1] - a[1]) * u
  const y = Math.min(a[2] + (b[2] - a[2]) * u, Math.max(0, imgH - w / ASPECT))
  return { x, y, w }
}

function Glow({ t }: { t: number }) {
  const p = t / timing.total
  return (
    <div style={{ position: 'absolute', width: 1500, height: 1500, left: interpolate(p, [0, 1], [-200, 1100]), top: interpolate(p, [0, 1], [500, -300]), borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(0,191,165,0.16), rgba(0,191,165,0))' }} />
  )
}

function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Img src={staticFile(dark ? 'logo-reversed.png' : 'logo.png')} style={{ position: 'absolute', left: 96, top: 40, height: 56 }} />
  )
}

function Rail({ active, t }: { active: number; t: number }) {
  return (
    <div style={{ position: 'absolute', right: 96, top: 50, display: 'flex', gap: 8 }}>
      {film.rail.map((r, i) => {
        const on = i === active
        const done = i < active
        return (
          <span key={r} style={{ padding: '7px 16px', borderRadius: 999, fontSize: 17, fontWeight: 600, border: `1px solid ${on ? TEAL_INK : 'rgba(22,32,30,0.12)'}`,
            background: on ? TEAL_INK : done ? 'rgba(0,191,165,0.12)' : 'rgba(255,255,255,0.7)', color: on ? '#fff' : done ? TEAL_INK : INK3, transform: `scale(${on ? 1 + 0.05 * win(t, 0, 0.6, 0.3) : 1})` }}>
            {r}
          </span>
        )
      })}
    </div>
  )
}

/** The voice-over as captions: the sentences shown one after another across the clip, in proportion to their length. */
function Captions({ text, t, start, seconds }: { text: string; t: number; start: number; seconds: number }) {
  const parts = text.match(/[^.!?]+[.!?]+/g) ?? [text]
  const total = parts.reduce((n, s) => n + s.length, 0)
  let at = start
  for (const s of parts) {
    const len = (s.length / total) * seconds
    if (t >= at && t < at + len + 0.25) {
      const o = win(t, at, at + len + 0.25, 0.2)
      return (
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 44, display: 'flex', justifyContent: 'center', opacity: o }}>
          <p style={{ margin: 0, maxWidth: 1400, padding: '12px 26px', borderRadius: 14, background: 'rgba(22,32,30,0.82)', color: '#fff', fontSize: 28, fontWeight: 500, lineHeight: 1.35, textAlign: 'center' }}>{s.trim()}</p>
        </div>
      )
    }
    at += len
  }
  return null
}

function Browser({ shots, p }: { shots: Shot[]; p: number }) {
  const starts = shots.map((_, i) => (i === 0 ? 0 : shots[i - 1].until))
  return (
    <div style={{ position: 'absolute', left: FRAME.x, top: FRAME.y, width: FRAME.w, height: FRAME.h + FRAME.bar, borderRadius: 20, overflow: 'hidden', background: '#fff',
      boxShadow: '0 2px 4px rgba(10,50,44,0.06), 0 50px 90px -40px rgba(10,50,44,0.45)', border: '1px solid rgba(22,32,30,0.08)' }}>
      <div style={{ height: FRAME.bar, display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', borderBottom: '1px solid rgba(22,32,30,0.08)', background: '#fbfaf7' }}>
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => <i key={c} style={{ width: 12, height: 12, borderRadius: '50%', background: c, display: 'inline-block' }} />)}
        <span style={{ marginLeft: 18, padding: '4px 16px', borderRadius: 8, background: '#f0eee8', fontSize: 15, color: INK3 }}>noordveld-machinery.vercel.app</span>
      </div>
      <div style={{ position: 'relative', width: FRAME.w, height: FRAME.h, overflow: 'hidden', background: PAPER }}>
        {shots.map((s, i) => {
          const a = starts[i]
          const local = interpolate(p, [a, s.until], [0, 1], clamp)
          const o = (i === 0 ? 1 : ramp(p, a - 0.02, a + 0.03)) * (i === shots.length - 1 ? 1 : 1 - ramp(p, s.until - 0.02, s.until + 0.03))
          if (o <= 0.001) return null
          const cam = cameraAt(s.camera, local, s.h)
          const scale = FRAME.w / cam.w
          return (
            <div key={s.image} style={{ position: 'absolute', inset: 0, opacity: o }}>
              <Img src={staticFile(s.image)} style={{ position: 'absolute', left: -cam.x * scale, top: -cam.y * scale, width: s.w * scale, height: s.h * scale }} />
              {s.highlights.map((h, j) => {
                const v = win(local, h[0], h[1], 0.06)
                if (v <= 0.001) return null
                const grow = 1 + 0.04 * (1 - ramp(local, h[0], h[0] + 0.08))
                return (
                  <div key={j} style={{ position: 'absolute', left: (h[2] - cam.x) * scale - 8, top: (h[3] - cam.y) * scale - 8, width: h[4] * scale + 16, height: h[5] * scale + 16, borderRadius: 14,
                    border: `3px solid ${TEAL}`, opacity: v, transform: `scale(${grow})`, boxShadow: `0 0 0 9999px rgba(15,26,24,${0.22 * v}), 0 0 28px rgba(0,191,165,0.45)` }} />
                )
              })}
            </div>
          )
        })}
      </div>
      <i style={{ position: 'absolute', left: 0, bottom: 0, height: 4, width: `${p * 100}%`, background: TEAL }} />
    </div>
  )
}

function ScreenScene({ scene, index, t, seconds }: { scene: Scene; index: number; t: number; seconds: number }) {
  const p = Math.min(1, Math.max(0, t / seconds))
  const enter = (at: number, lift = 30): CSSProperties => ({ opacity: ramp(t, at, at + 0.5), transform: `translateY(${(1 - ramp(t, at, at + 0.7)) * lift}px)` })
  return (
    <>
      <div style={{ position: 'absolute', left: 96, top: 250, width: 560 }}>
        <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: TEAL_INK, fontFamily: 'ui-monospace, Consolas, monospace', ...enter(0.1) }}>{String(index).padStart(2, '0')}</p>
        <p style={{ margin: '14px 0 0', fontSize: 20, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: TEAL_INK, ...enter(0.2) }}>{scene.kicker}</p>
        <h2 style={{ margin: '18px 0 0', fontSize: 64, lineHeight: 1.04, letterSpacing: '-0.035em', fontWeight: 650, color: INK, whiteSpace: 'pre-line', ...enter(0.35, 40) }}>{scene.title}</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 34 }}>
          {(scene.chips ?? []).map((c, i) => (
            <span key={c} style={{ padding: '10px 18px', borderRadius: 999, background: '#fff', border: '1px solid rgba(22,32,30,0.12)', fontSize: 20, fontWeight: 600, color: INK2, ...enter(1.0 + i * 0.25, 16) }}>
              <b style={{ color: TEAL, marginRight: 8 }}>●</b>{c}
            </span>
          ))}
        </div>
      </div>
      <div style={{ ...enter(0.15, 50) }}>
        <Browser shots={scene.shots ?? []} p={p} />
      </div>
    </>
  )
}

function HookScene({ scene, t, seconds }: { scene: Scene; t: number; seconds: number }) {
  const down = ramp(t, 1.4, 2.4)
  const chip = ramp(t, 1.8, 2.5)
  const pulse = Math.max(0, Math.sin(t * 4))
  return (
    <AbsoluteFill style={{ background: '#0f1a18' }}>
      <Img src={staticFile(scene.image ?? '')} style={{ position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${interpolate(t, [0, seconds], [1.14, 1.0])})`,
        filter: `saturate(${1 - 0.75 * down}) brightness(${1 - 0.25 * down})` }} />
      <AbsoluteFill style={{ background: 'linear-gradient(180deg, rgba(15,26,24,0.1) 30%, rgba(15,26,24,0.8))', opacity: 0.4 + 0.6 * down }} />
      <Brand dark />
      <div style={{ position: 'absolute', left: 96, bottom: 200, display: 'flex', alignItems: 'center', gap: 16, padding: '16px 28px 16px 22px', borderRadius: 999, background: '#fff', fontSize: 28, opacity: chip, transform: `translateY(${(1 - chip) * 20}px)` }}>
        <i style={{ width: 14, height: 14, borderRadius: '50%', background: '#d97706', boxShadow: `0 0 0 ${10 * pulse}px rgba(217,119,6,0.25)`, display: 'inline-block' }} />
        <strong style={{ color: INK }}>{scene.kicker}</strong>
        <span style={{ color: INK3 }}>Machine down</span>
      </div>
      <h1 style={{ position: 'absolute', left: 96, bottom: 280, margin: 0, fontSize: 132, letterSpacing: '-0.05em', fontWeight: 650, color: '#fff', opacity: ramp(t, 2.6, 3.3), transform: `translateY(${(1 - ramp(t, 2.6, 3.4)) * 40}px)` }}>{scene.title}</h1>
    </AbsoluteFill>
  )
}

function OutroScene({ scene, t }: { scene: Scene; t: number }) {
  const line = ramp(t, 0.2, 2.0)
  return (
    <AbsoluteFill>
      <svg viewBox="0 0 1920 1080" width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <path d="M-80 930 C 320 860, 620 1010, 980 920 S 1600 850, 2000 915" pathLength={1} fill="none" stroke={TEAL} strokeWidth={4} strokeLinecap="round" strokeDasharray="1" strokeDashoffset={1 - line} opacity={0.6} />
      </svg>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 200, display: 'flex', flexDirection: 'column', alignItems: 'center', fontSize: 170, lineHeight: 0.98, letterSpacing: '-0.055em', fontWeight: 650 }}>
        {(scene.words ?? []).map((w, i) => {
          const e = ramp(t, 0.6 + i * 0.35, 1.5 + i * 0.35)
          return (
            <span key={w} style={{ display: 'block', overflow: 'hidden', paddingBottom: 14 }}>
              <span style={{ display: 'inline-block', transform: `translateY(${(1 - e) * 105}%)`, color: i === 1 ? TEAL_INK : INK }}>{w}</span>
            </span>
          )
        })}
      </div>
      <p style={{ position: 'absolute', left: 0, right: 0, top: 640, textAlign: 'center', margin: 0, fontSize: 44, fontWeight: 500, color: INK2, opacity: ramp(t, 1.9, 2.6) }}>{scene.title}</p>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 735, display: 'flex', justifyContent: 'center', opacity: ramp(t, 2.6, 3.3), transform: `translateY(${(1 - ramp(t, 2.6, 3.4)) * 16}px)` }}>
        <Img src={staticFile('logo.png')} style={{ height: 92 }} />
      </div>
      <p style={{ position: 'absolute', left: 0, right: 0, top: 850, textAlign: 'center', margin: 0, fontSize: 20, color: INK3, opacity: ramp(t, 3.2, 3.8) }}>{film.disclaimer}</p>
    </AbsoluteFill>
  )
}

/** Music under the voice: lower while someone is speaking. */
function musicVolume(f: number, fps: number): number {
  const t = f / fps
  const speaking = timing.scenes.reduce((v, s) => Math.max(v, win(t, s.vo_start - 0.25, s.vo_start + s.vo_seconds + 0.35, 0.3)), 0)
  return 0.42 - 0.27 * speaking
}

export function WorkflowFilm(): ReactNode {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const now = frame / fps
  return (
    <AbsoluteFill style={{ background: PAPER, fontFamily: FONT, color: INK, overflow: 'hidden' }}>
      <Glow t={now} />
      <Audio src={staticFile('music.mp3')} volume={(f) => musicVolume(f, fps)} />
      {SCENES.map((scene, i) => {
        const tm = timing.scenes[i]
        const from = Math.round(tm.start * fps)
        const dur = Math.round(tm.seconds * fps)
        const n = NUMBERS[i]
        const t = now - tm.start
        const o = i === 0 ? 1 - ramp(t, tm.seconds - 0.4, tm.seconds) : win(t, 0, tm.seconds, 0.4)
        return (
          <Sequence key={scene.id} from={from} durationInFrames={dur + Math.round(0.1 * fps)}>
            <AbsoluteFill style={{ opacity: i === SCENES.length - 1 ? ramp(t, 0, 0.4) : o }}>
              {scene.kind === 'hook' ? <HookScene scene={scene} t={t} seconds={tm.seconds} /> : null}
              {scene.kind === 'screen' ? (
                <>
                  <Brand />
                  <Rail active={scene.rail ?? 0} t={t} />
                  <ScreenScene scene={scene} index={n} t={t} seconds={tm.seconds} />
                </>
              ) : null}
              {scene.kind === 'outro' ? <OutroScene scene={scene} t={t} /> : null}
            </AbsoluteFill>
            <Sequence from={Math.round((tm.vo_start - tm.start) * fps)}>
              <Audio src={staticFile(`vo/${scene.id}.mp3`)} />
            </Sequence>
          </Sequence>
        )
      })}
      {SCENES.map((scene, i) => (scene.kind === 'outro' ? null : <Captions key={scene.id} text={scene.vo} t={now} start={timing.scenes[i].vo_start} seconds={timing.scenes[i].vo_seconds} />))}
    </AbsoluteFill>
  )
}
