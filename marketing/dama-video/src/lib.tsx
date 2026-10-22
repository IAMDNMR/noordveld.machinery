import React from 'react'
import { Easing, interpolate } from 'remotion'

export const C = {
  deep: '#050B24',
  navy: '#0A1640',
  ink: '#0B1533',
  blue: '#2B4BFF',
  sky: '#2E8BEF',
  cyan: '#22B8E8',
  teal: '#20D3C2',
  ice: '#7CD3F7',
  bg: '#F3F6FE',
  white: '#FFFFFF',
  amber: '#FFB020',
  red: '#FF4D5E',
  green: '#15B079',
  muted: '#5B6785',
}
/** Triangle colours sampled from the Nextgenlytics logo. */
export const TRI = ['#0B1A4A', '#1E3A8A', '#2B4BFF', '#2E8BEF', '#22B8E8', '#7CD3F7']
export const FONT = '"DM Sans", system-ui, sans-serif'
export const W = 1080
export const H = 1920

export const outE = Easing.bezier(0.16, 1, 0.3, 1)
export const inOutE = Easing.bezier(0.65, 0, 0.35, 1)
export const inE = Easing.bezier(0.55, 0, 1, 0.45)

/** 0 -> 1 between seconds a and b (clamped, eased). */
export const p = (t: number, a: number, b: number, ease = outE) =>
  interpolate(t, [a, b], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease })
export const lerp = (a: number, b: number, k: number) => a + (b - a) * k

/** Overshooting pop (0 -> 1 with a small bounce), deterministic. */
export const pop = (t: number, a: number, dur = 0.5) => {
  const x = Math.min(1, Math.max(0, (t - a) / dur))
  if (x <= 0) return 0
  const c = 1.9
  return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2)
}

export function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0
    return s / 4294967296
  }
}

/** Right-pointing triangle, like the logo's data particles. */
export const triPoints = (s: number) => `${-s * 0.5},${-s * 0.55} ${s * 0.62},0 ${-s * 0.5},${s * 0.55}`

export const Abs: React.FC<{ style?: React.CSSProperties; children?: React.ReactNode }> = ({ style, children }) => (
  <div style={{ position: 'absolute', inset: 0, ...style }}>{children}</div>
)

/** A line of text that rises out of a mask. */
export const Rise: React.FC<{
  t: number
  at: number
  dur?: number
  children: React.ReactNode
  style?: React.CSSProperties
}> = ({ t, at, dur = 0.7, children, style }) => {
  const k = p(t, at, at + dur)
  return (
    <div style={{ overflow: 'hidden', paddingBottom: '0.12em', ...style }}>
      <div style={{ transform: `translateY(${(1 - k) * 110}%)`, opacity: k > 0 ? 1 : 0 }}>{children}</div>
    </div>
  )
}

/** Word-by-word reveal for headlines. */
export const Words: React.FC<{
  t: number
  at: number
  text: string
  step?: number
  style?: React.CSSProperties
  accent?: (word: string, i: number) => React.CSSProperties | undefined
}> = ({ t, at, text, step = 0.07, style, accent }) => (
  <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: '0.26em', ...style }}>
    {text.split(' ').map((w, i) => {
      const k = p(t, at + i * step, at + i * step + 0.6)
      return (
        <span key={i} style={{ display: 'inline-block', overflow: 'hidden', paddingBottom: '0.1em' }}>
          <span
            style={{
              display: 'inline-block',
              transform: `translateY(${(1 - k) * 105}%) rotate(${(1 - k) * 6}deg)`,
              ...accent?.(w, i),
            }}
          >
            {w}
          </span>
        </span>
      )
    })}
  </div>
)

/** Slow-drifting field of logo triangles (background texture). */
export const TriField: React.FC<{
  t: number
  seed: number
  count: number
  opacity?: number
  colors?: string[]
  size?: [number, number]
  drift?: number
  area?: { x: number; y: number; w: number; h: number }
}> = ({ t, seed, count, opacity = 1, colors = TRI, size = [10, 26], drift = 18, area = { x: 0, y: 0, w: W, h: H } }) => {
  const r = rng(seed)
  const items = Array.from({ length: count }, () => ({
    x: r(), y: r(), s: lerp(size[0], size[1], r()), c: colors[Math.floor(r() * colors.length)],
    a: r() * 360, sp: 0.4 + r(), ph: r() * 6.28, o: 0.35 + r() * 0.65,
  }))
  return (
    <svg width={W} height={H} style={{ position: 'absolute', inset: 0, opacity }}>
      {items.map((d, i) => {
        const x = area.x + d.x * area.w + Math.sin(t * 0.5 * d.sp + d.ph) * drift
        const y = area.y + d.y * area.h + Math.cos(t * 0.4 * d.sp + d.ph) * drift
        return (
          <polygon key={i} points={triPoints(d.s)} fill={d.c} opacity={d.o}
            transform={`translate(${x} ${y}) rotate(${d.a + t * 12 * (d.sp - 0.9)})`} />
        )
      })}
    </svg>
  )
}

export const Chip: React.FC<{ children: React.ReactNode; color?: string; bg?: string; style?: React.CSSProperties }> = ({
  children, color = C.white, bg = 'rgba(255,255,255,0.12)', style,
}) => (
  <div style={{
    display: 'inline-flex', alignItems: 'center', gap: 14, padding: '14px 26px', borderRadius: 999,
    background: bg, color, fontSize: 30, fontWeight: 600, letterSpacing: 0.3, whiteSpace: 'nowrap', ...style,
  }}>
    {children}
  </div>
)
