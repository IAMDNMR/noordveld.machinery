import { LayoutGrid, Scale, Search, ShoppingBag, SlidersHorizontal } from 'lucide-react'
import { easeOut, seg } from '../../lib/math'
import { DrawPath, Glyph, Label, SCENE_H, SCENE_W, accent, ink, ink3 } from './primitives'

const STEPS = [
  { name: 'Search', icon: Search },
  { name: 'Browse', icon: LayoutGrid },
  { name: 'Filter', icon: SlidersHorizontal },
  { name: 'Compare', icon: Scale },
  { name: 'Purchase', icon: ShoppingBag },
] as const
const ROW_Y = 392
const rowX = (i: number): number => 120 + i * 140

export function EcommerceScene({ p }: { p: number }) {
  const phase = Math.min(STEPS.length - 1, Math.floor(p * STEPS.length))
  const local = p * STEPS.length - phase
  const settle = easeOut(Math.min(1, local * 3))
  const active = STEPS[phase]
  const done = seg(p, 0.92, 1)
  const railProgress = phase === 0 ? 0 : (phase - 1 + settle) / (STEPS.length - 1)

  return (
    <svg viewBox={`0 0 ${SCENE_W} ${SCENE_H}`} role="presentation" aria-hidden="true" width="100%" height="100%">
      {/* Focal glyph: the current step, drawn large */}
      <circle cx={400} cy={170} r={112} fill="var(--accent-soft)" opacity={seg(p, 0, 0.06)} />
      <circle cx={400} cy={170} r={112 + 26 * (1 - settle)} fill="none" stroke={accent} strokeWidth={1.5} opacity={0.35 * (1 - settle) * seg(p, 0, 0.06)} />
      <Glyph icon={active.icon} x={400} y={170} size={118} color={accent} scale={0.82 + 0.18 * settle} opacity={settle} strokeWidth={1.1} />

      <Label x={400} y={338} size={30} weight={600} fill={ink} opacity={settle}>
        {active.name}
      </Label>

      {/* Step rail */}
      <DrawPath d={`M${rowX(0)} ${ROW_Y} L${rowX(4)} ${ROW_Y}`} t={1} stroke={ink3} width={1.25} opacity={0.45} />
      <DrawPath d={`M${rowX(0)} ${ROW_Y} L${rowX(4)} ${ROW_Y}`} t={railProgress} stroke={accent} width={3} />
      {STEPS.map((s, i) => {
        const reached = i <= phase
        return (
          <g key={s.name}>
            <circle cx={rowX(i)} cy={ROW_Y} r={5} fill={reached ? accent : 'var(--paper)'} stroke={reached ? accent : ink3} strokeWidth={1.5} />
            <Label x={rowX(i)} y={ROW_Y + 40} fill={i === phase ? ink : ink3} weight={i === phase ? 600 : 500}>
              {s.name}
            </Label>
          </g>
        )
      })}

      {done > 0 ? <circle cx={rowX(4)} cy={ROW_Y} r={10 + 6 * done} fill="none" stroke={accent} strokeWidth={2} opacity={1 - done * 0.4} /> : null}
    </svg>
  )
}
