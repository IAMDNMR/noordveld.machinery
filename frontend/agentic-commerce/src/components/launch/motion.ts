import type { CSSProperties } from 'react'
import { clamp01, easeInOut, easeOut, lerp, seg } from '../../lib/math'

export { clamp01, easeInOut, easeOut, lerp, seg }

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

/** Spring-like: settles with a small overshoot. */
export const spring = (t: number): number => {
  const c1 = 1.25
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}
export const easeLinear = (t: number): number => t

/** 0 → 1 over [a, b] */
export const rise = (t: number, a: number, b: number, ease = easeOut): number => seg(t, a, b, ease)
/** 1 → 0 over [a, b] */
export const fall = (t: number, a: number, b: number, ease = easeInOut): number => 1 - seg(t, a, b, ease)
/** Visible in [a, b], with soft edges of `edge` seconds */
export const window01 = (t: number, a: number, b: number, edge = 0.5): number => Math.min(seg(t, a, a + edge, easeInOut), 1 - seg(t, b - edge, b, easeInOut))

export const lerpRect = (a: Rect, b: Rect, u: number): Rect => ({ x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), w: lerp(a.w, b.w, u), h: lerp(a.h, b.h, u) })

export const box = (r: Rect, extra?: CSSProperties): CSSProperties => ({ position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h, ...extra })

/** Entrance: fades in while rising into place, with a touch of overshoot on the scale. */
export const enter = (t: number, at: number, dur = 0.8, lift = 26): CSSProperties => {
  const o = seg(t, at, at + dur * 0.7, easeOut)
  const s = seg(t, at, at + dur, spring)
  return { opacity: o, transform: `translateY(${(1 - s) * lift}px) scale(${0.97 + 0.03 * s})`, visibility: o > 0.002 ? 'visible' : 'hidden' }
}
