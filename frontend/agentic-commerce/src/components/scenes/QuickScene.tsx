import { House, Timer, Truck, Warehouse } from 'lucide-react'
import { easeOut, lerp, seg } from '../../lib/math'
import { DrawPath, Glyph, Label, SCENE_H, SCENE_W, accent, ink, ink2, ink3, line } from './primitives'

const HOME = { x: 640, y: 235 }
const POINTS = [
  { dx: -540, dy: -150 },
  { dx: -440, dy: 150 },
  { dx: -340, dy: -40 },
  { dx: -230, dy: 175 },
  { dx: -170, dy: -150 },
  { dx: -580, dy: 40 },
] as const
const NEAREST = 4
const STEPS = ['Inventory', 'Nearby availability', 'Fulfilment', 'Delivery'] as const
const STEP_X = [90, 232, 470, 626] as const
const CLOCK_R = 30
const CLOCK_LEN = 2 * Math.PI * CLOCK_R

export function QuickScene({ p }: { p: number }) {
  const appear = seg(p, 0, 0.12)
  const squeeze = seg(p, 0.14, 0.58)
  const factor = lerp(1, 0.36, squeeze)
  const route = seg(p, 0.6, 0.74)
  const ride = seg(p, 0.74, 0.96, easeOut)
  const time = lerp(1, 0.12, seg(p, 0.58, 0.96))
  const activeStep = p < 0.26 ? 0 : p < 0.6 ? 1 : p < 0.74 ? 2 : 3

  // Distance compression: every inventory point is pulled toward the customer
  const pos = POINTS.map((pt) => ({ x: HOME.x + pt.dx * factor, y: HOME.y + pt.dy * factor }))
  const from = pos[NEAREST]
  const bend = { x: (from.x + HOME.x) / 2, y: from.y + 30 }
  const routePath = `M${from.x} ${from.y} Q${bend.x} ${bend.y} ${HOME.x} ${HOME.y}`
  const rider = {
    x: (1 - ride) ** 2 * from.x + 2 * (1 - ride) * ride * bend.x + ride * ride * HOME.x,
    y: (1 - ride) ** 2 * from.y + 2 * (1 - ride) * ride * bend.y + ride * ride * HOME.y,
  }

  return (
    <svg viewBox={`0 0 ${SCENE_W} ${SCENE_H}`} role="presentation" aria-hidden="true" width="100%" height="100%">
      {[110, 200, 290, 380].map((r, i) => (
        <circle key={r} cx={HOME.x} cy={HOME.y} r={r} fill="none" stroke={line} strokeWidth={1.25} strokeDasharray="3 9" opacity={appear * (1 - i * 0.18)} />
      ))}

      {POINTS.map((pt, i) => {
        const lit = i === NEAREST && p > 0.5
        return (
          <g key={i}>
            <line x1={HOME.x + pt.dx} y1={HOME.y + pt.dy} x2={pos[i].x} y2={pos[i].y} stroke={ink3} strokeWidth={1.5} opacity={0.28 * squeeze * appear} />
            <Glyph icon={Warehouse} x={pos[i].x} y={pos[i].y} size={lit ? 38 : 28} color={lit ? accent : ink2} opacity={appear} strokeWidth={lit ? 1.6 : 1.4} />
          </g>
        )
      })}

      <DrawPath d={routePath} t={route} stroke={accent} width={3} />
      {ride > 0 && ride < 1 ? <Glyph icon={Truck} x={rider.x} y={rider.y - 22} size={30} color={accent} strokeWidth={1.6} /> : null}

      <circle cx={HOME.x} cy={HOME.y} r={34} fill="var(--accent-soft)" opacity={appear} />
      <Glyph icon={House} x={HOME.x} y={HOME.y} size={34} color={ride >= 1 ? accent : ink} opacity={appear} strokeWidth={1.5} />

      <g transform="translate(86 78)" opacity={seg(p, 0.5, 0.62)}>
        <circle r={CLOCK_R} fill="none" stroke={line} strokeWidth={4} />
        <circle r={CLOCK_R} fill="none" stroke={accent} strokeWidth={4} strokeLinecap="round" strokeDasharray={`${CLOCK_LEN * time} ${CLOCK_LEN}`} transform="rotate(-90)" />
        <Glyph icon={Timer} x={0} y={0} size={22} color={ink} strokeWidth={1.8} />
        <text x={52} y={7} style={{ fontFamily: 'var(--font-sans)', fontSize: 'var(--scene-label, 20px)', fontWeight: 500, fill: ink2 }}>
          Time to your door
        </text>
      </g>

      {STEPS.map((s, i) => (
        <Label key={s} x={STEP_X[i]} y={466} anchor="start" fill={i === activeStep ? ink : ink3} weight={i === activeStep ? 600 : 500}>
          {s}
        </Label>
      ))}
      <circle cx={STEP_X[activeStep] + 4} cy={482} r={3} fill={accent} />
    </svg>
  )
}
