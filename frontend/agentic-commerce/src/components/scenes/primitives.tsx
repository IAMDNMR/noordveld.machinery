import type { LucideIcon } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'

export const SCENE_W = 800
export const SCENE_H = 500

export const ink = 'var(--ink)'
export const ink2 = 'var(--ink-2)'
export const ink3 = 'var(--ink-3)'
export const line = 'var(--line-strong)'
export const accent = 'var(--accent)'
export const accentInk = 'var(--accent-ink)'

export const labelStyle: CSSProperties = {
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--scene-label, 20px)',
  fill: ink2,
  fontWeight: 500,
  letterSpacing: '-0.01em',
}

interface GlyphProps {
  icon: LucideIcon
  /** centre of the glyph in scene units */
  x: number
  y: number
  size?: number
  color?: string
  opacity?: number
  scale?: number
  strokeWidth?: number
}

/** A real icon (Lucide, SF-Symbols-like line weight) placed by its centre. */
export function Glyph({ icon: Icon, x, y, size = 56, color = ink, opacity = 1, scale = 1, strokeWidth = 1.25 }: GlyphProps): ReactNode {
  return (
    <g opacity={opacity} transform={`translate(${x} ${y}) scale(${scale})`}>
      <Icon x={-size / 2} y={-size / 2} size={size} color={color} strokeWidth={strokeWidth} />
    </g>
  )
}

interface LabelProps {
  x: number
  y: number
  children: ReactNode
  opacity?: number
  anchor?: 'start' | 'middle' | 'end'
  fill?: string
  size?: number
  weight?: number
  className?: string
}

export function Label({ x, y, children, opacity = 1, anchor = 'middle', fill, size, weight, className }: LabelProps): ReactNode {
  return (
    <text x={x} y={y} textAnchor={anchor} opacity={opacity} className={className} style={{ ...labelStyle, ...(fill ? { fill } : null), ...(size ? { fontSize: size } : null), ...(weight ? { fontWeight: weight } : null) }}>
      {children}
    </text>
  )
}

interface DrawPathProps {
  d: string
  /** 0–1 of the path revealed */
  t: number
  stroke?: string
  width?: number
  dash?: string
  opacity?: number
}

/** Draw-on line using pathLength normalisation. With `dash`, a faint dashed guide sits underneath. */
export function DrawPath({ d, t, stroke = ink, width = 2, dash, opacity = 1 }: DrawPathProps): ReactNode {
  return (
    <g opacity={opacity}>
      {dash ? <path d={d} fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeDasharray={dash} opacity={0.4} /> : null}
      <path d={d} fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" pathLength={1} strokeDasharray={`${t} 1.001`} />
    </g>
  )
}
