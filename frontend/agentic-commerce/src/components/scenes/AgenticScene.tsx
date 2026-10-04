import { CircleCheck, Euro, MapPin, PackageCheck, Puzzle, ScanSearch, Target, Truck } from 'lucide-react'
import { lerp, seg } from '../../lib/math'
import { DrawPath, Glyph, Label, SCENE_H, SCENE_W, accent, accentInk, ink, ink2, ink3, line } from './primitives'

const REQUIREMENT = ['My machine is down.', 'Budget · Urgency', 'Availability · Location'] as const
const CENTER = { x: 600, y: 250 }
const FACTORS = [
  { name: 'Context', icon: ScanSearch },
  { name: 'Compatibility', icon: Puzzle },
  { name: 'Availability', icon: PackageCheck },
  { name: 'Price', icon: Euro },
  { name: 'Location', icon: MapPin },
  { name: 'Delivery', icon: Truck },
] as const
const OPTIONS = [
  { name: 'A', meta: 'Best availability' },
  { name: 'B', meta: 'Fastest fulfilment' },
  { name: 'C', meta: 'Lowest cost' },
] as const

const text = { fontFamily: 'var(--font-sans)', fill: ink } as const

export function AgenticScene({ p }: { p: number }) {
  const lines = REQUIREMENT.map((_, i) => seg(p, i * 0.06, i * 0.06 + 0.1))
  const settle = seg(p, 0.34, 0.5)
  const graph = seg(p, 0.26, 0.4) * (1 - seg(p, 0.58, 0.68))
  const opts = seg(p, 0.62, 0.74)
  const best = seg(p, 0.84, 0.95)

  return (
    <svg viewBox={`0 0 ${SCENE_W} ${SCENE_H}`} role="presentation" aria-hidden="true" width="100%" height="100%">
      <g transform={`translate(40 ${lerp(170, 126, settle)})`} opacity={lerp(1, 0.4, settle)}>
        {REQUIREMENT.map((t, i) => (
          <text key={t} x={0} y={i * 44 + (1 - lines[i]) * 14} opacity={lines[i]} style={{ ...text, fontSize: 28, fontWeight: i === 0 ? 600 : 400, letterSpacing: '-0.02em' }}>
            {t}
          </text>
        ))}
      </g>

      <g opacity={graph}>
        {FACTORS.map((f, i) => {
          const a = -Math.PI / 2 + (i * Math.PI * 2) / FACTORS.length
          const x = CENTER.x + Math.cos(a) * 135
          const y = CENTER.y + Math.sin(a) * 150
          const on = seg(p, 0.3 + i * 0.022, 0.38 + i * 0.022)
          return (
            <g key={f.name} opacity={on}>
              <DrawPath d={`M${CENTER.x} ${CENTER.y} L${x} ${y}`} t={on} stroke={accent} width={1.5} opacity={0.6} />
              <circle cx={x} cy={y} r={30} fill="var(--scene-mask, var(--paper))" />
              <Glyph icon={f.icon} x={x} y={y} size={36} color={ink} strokeWidth={1.5} />
              <Label x={x} y={y + (Math.sin(a) < -0.2 ? -44 : 54)} size={19} fill={ink2}>
                {f.name}
              </Label>
            </g>
          )
        })}
        <circle cx={CENTER.x} cy={CENTER.y} r={42} fill="var(--accent-soft)" />
        <Glyph icon={Target} x={CENTER.x} y={CENTER.y} size={44} color={accent} strokeWidth={1.5} />
      </g>

      <g opacity={opts}>
        {OPTIONS.map((o, i) => {
          const y = 120 + i * 108 + (1 - opts) * 18
          const isBest = i === 0
          const o2 = isBest ? 1 : lerp(1, 0.4, best)
          return (
            <g key={o.name} transform={`translate(440 ${y})`} opacity={o2}>
              <line x1={0} x2={320} y1={-34} y2={-34} stroke={line} strokeWidth={1} />
              <text x={0} y={0} style={{ ...text, fontSize: 25, fontWeight: 600, letterSpacing: '-0.02em', fill: isBest && best > 0.5 ? accentInk : ink }}>
                Option {o.name}
              </text>
              <text x={0} y={30} style={{ ...text, fontSize: 'var(--scene-meta, 19px)', fill: ink3 }}>
                {o.meta}
              </text>
              {isBest ? <Glyph icon={CircleCheck} x={300} y={-8} size={30} color={accent} strokeWidth={1.6} opacity={best} /> : null}
            </g>
          )
        })}
        <text x={760} y={78} textAnchor="end" opacity={best} style={{ ...text, fontSize: 19, fontWeight: 500, fill: accentInk }}>
          Best match for your requirement
        </text>
      </g>
    </svg>
  )
}
