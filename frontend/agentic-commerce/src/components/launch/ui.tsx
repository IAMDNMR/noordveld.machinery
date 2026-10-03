import type { CSSProperties, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { CLICKS, cursorAt } from './timeline'
import { box, easeOut, seg, type Rect } from './motion'

/** Line-icon in a soft circle: the film's basic marker. */
export function Bubble({ icon: Icon, size = 56, on = false, style }: { icon: LucideIcon; size?: number; on?: boolean; style?: CSSProperties }) {
  return (
    <span className={`lf-bubble ${on ? 'is-on' : ''}`} style={{ width: size, height: size, ...style }}>
      <Icon size={Math.round(size * 0.46)} strokeWidth={1.6} aria-hidden="true" />
    </span>
  )
}

/** A positioned white surface. `lift` (0–1) is the hover state: it rises, gains a teal edge and a deeper shadow. */
export function Surface({ rect, lift = 0, radius = 18, style, children, className = '' }: { rect: Rect; lift?: number; radius?: number; style?: CSSProperties; children?: ReactNode; className?: string }) {
  return (
    <div
      className={`lf-surface ${className}`}
      style={box(rect, {
        borderRadius: radius,
        transform: `translateY(${-10 * lift}px) ${style?.transform ?? ''}`,
        borderColor: lift > 0.02 ? `rgb(0 191 165 / ${0.25 + 0.55 * lift})` : undefined,
        boxShadow: `0 1px 2px rgb(10 50 44 / 0.05), 0 ${22 + 26 * lift}px ${44 + 24 * lift}px -${24 - 6 * lift}px rgb(10 50 44 / ${0.22 + 0.14 * lift})`,
        ...style,
      })}
    >
      {children}
    </div>
  )
}

/** The press ripple that follows every click. */
export function Ripples({ t }: { t: number }) {
  return (
    <>
      {CLICKS.map((c) => {
        const u = seg(t, c.t, c.t + 0.7, easeOut)
        if (u <= 0 || u >= 1) return null
        return <span key={c.t} className="lf-ripple" style={{ left: c.x, top: c.y, width: 30 + 120 * u, height: 30 + 120 * u, opacity: 0.55 * (1 - u) }} />
      })}
    </>
  )
}

/** The cursor: a real pointer arrow that compresses on a press. */
export function Cursor({ t }: { t: number }) {
  const c = cursorAt(t)
  if (c.opacity < 0.01) return null
  return (
    <div className="lf-cursor" style={{ transform: `translate(${c.x}px, ${c.y}px) scale(${c.press})`, opacity: c.opacity }}>
      <svg width="30" height="36" viewBox="0 0 30 36" aria-hidden="true">
        <path d="M2 2 L2 28 L9.2 21.4 L14.2 33 L19.6 30.6 L14.6 19.2 L24.4 19.2 Z" fill="#0f1a18" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** A path that draws itself. `p` is 0–1. */
export function Draw({ d, p, stroke = 'var(--accent)', width = 2.5, dash, opacity = 1, cap = 'round' }: { d: string; p: number; stroke?: string; width?: number; dash?: string; opacity?: number; cap?: 'round' | 'butt' }) {
  if (p <= 0.001) return null
  return <path d={d} pathLength={1} fill="none" stroke={stroke} strokeWidth={width} strokeLinecap={cap} strokeDasharray={dash ?? '1'} strokeDashoffset={dash ? 0 : 1 - p} opacity={opacity} style={dash ? { clipPath: undefined } : undefined} />
}
