import { machineImageUrl } from '../../../../src/lib/assets'
import { filmData as D } from './launchData'
import { box, easeInOut, fall, lerp, rise, seg, spring, window01 } from './motion'

/* ───────── The hook, and the narration that carries the story ───────── */

const FRAME = { x: 260, y: 110, w: 1080, h: 640 }

/**
 * Before anything is said: the machine, working. Then it stops. The colour drains, one quiet status appears, and the
 * picture gives way to the white page where the need is spoken. `t` is viewer time (the hook runs before the story).
 */
export function Hook({ t }: { t: number }) {
  if (t > 3.6) return null
  const img = machineImageUrl(D.machine.slug, 'main')
  const appear = rise(t, 0, 0.8)
  const down = seg(t, 1.0, 1.6, easeInOut)
  const chip = seg(t, 1.25, 2.0, spring)
  const exit = seg(t, 2.45, 3.3, easeInOut)
  const pulse = Math.max(0, Math.sin(Math.PI * seg(t, 1.3, 2.3, (u) => u)))
  return (
    <div style={{ ...box(FRAME), opacity: appear * (1 - exit), transform: `scale(${lerp(1, 0.9, exit)})`, transformOrigin: '50% 50%' }}>
      <div className="lf-hook">
        {img ? <img src={img} alt="" style={{ transform: `scale(${lerp(1.12, 1.02, seg(t, 0, 3.3, (u) => u))})`, filter: `saturate(${lerp(1, 0.25, down)}) brightness(${lerp(1, 0.9, down)})` }} /> : null}
        <i className="lf-hook__veil" style={{ opacity: down * 0.55 }} />
      </div>
      <div className="lf-hook__chip" style={{ opacity: Math.min(1, chip * 1.5), transform: `translateY(${(1 - chip) * 18}px)` }}>
        <span className="lf-hook__dot" style={{ boxShadow: `0 0 0 ${8 * pulse}px rgb(217 119 6 / ${0.22 * pulse})` }} />
        <strong>{D.machine.model}</strong>
        <span>Machine down</span>
      </div>
    </div>
  )
}

/** One short line per chapter, low on the screen. `t` is story time. */
const LINES = [
  { a: 4.6, b: 8.3, text: 'Not a product search. A problem, in plain words.' },
  { a: 9.7, b: 12.5, text: 'It knows the machine.' },
  { a: 13.1, b: 17.9, text: 'It finds the part that fits, from the catalogue, not by guesswork.' },
  { a: 18.8, b: 23.9, text: 'It checks where the part actually is.' },
  { a: 24.3, b: 28.9, text: 'It picks the fastest way to get it there.' },
  { a: 34.6, b: 37.3, text: 'One click to confirm.' },
  { a: 38.1, b: 41.4, text: 'And it stays with the machine after the sale.' },
] as const

export function Narration({ t }: { t: number }) {
  return (
    <>
      {LINES.map((l) => {
        const o = window01(t, l.a, l.b, 0.45)
        if (o < 0.01) return null
        return (
          <p key={l.text} className="lf-narration" style={{ opacity: o, transform: `translateY(${(1 - rise(t, l.a, l.a + 0.6)) * 10 + (1 - fall(t, l.b - 0.45, l.b)) * -6}px)` }}>
            {l.text}
          </p>
        )
      })}
    </>
  )
}
