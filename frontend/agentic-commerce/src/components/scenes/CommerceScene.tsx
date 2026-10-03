import { Check, HandCoins, MapPin, Package, Store, Truck, User, Wrench } from 'lucide-react'
import { clamp01, easeOut, lerp, seg } from '../../lib/math'
import { DrawPath, Glyph, Label, SCENE_H, SCENE_W, accent, accentInk, ink, ink2, ink3, line } from './primitives'

/*
  One continuous journey: Need → Seller → Product → Transaction → Delivery → Service.
  The teal line travels through it; a cursor follows the line, clicks each icon, and the click activates the step.
  At Delivery the click opens a compact fulfilment interaction, which collapses before the journey continues.
  Everything is a pure function of `p` (0–1), so it scrubs with scroll, renders in the film, and p = 1 is the finished state.
*/

const Y = 312
const X0 = 80
const STEP = 128
const NODES = [
  { label: 'Need', icon: User, caption: 'Need identified' },
  { label: 'Seller', icon: Store, caption: 'Right seller found' },
  { label: 'Product', icon: Package, caption: 'Right product selected' },
  { label: 'Transaction', icon: HandCoins, caption: 'Transaction completed' },
  { label: 'Delivery', icon: Truck, caption: 'Fulfilment arranged' },
  { label: 'Service', icon: Wrench, caption: 'Delivered and supported' },
].map((n, i) => ({ ...n, x: X0 + i * STEP }))
const LAST = NODES.length - 1
const DELIVERY = 4

/** The moment each icon is clicked */
const CLICK = [0.09, 0.2, 0.31, 0.42, 0.53, 0.945] as const
/** The line leaves the previous icon shortly after its click and reaches the next one just before it is clicked */
const lineFrom = (i: number): number => (i === LAST ? 0.84 : CLICK[i - 1] + 0.025)
const lineTo = (i: number): number => CLICK[i] - 0.02

/** Delivery interaction: options open, an option is chosen, the route plays, then it collapses */
const OPEN: readonly [number, number] = [0.545, 0.585]
const PICK = 0.65
const ROUTE: readonly [number, number] = [0.665, 0.75]
const CLOSE: readonly [number, number] = [0.795, 0.84]

const PW = 330
const PH = 244
/** The panel opens at the height of its options and grows to fit the route once an option is chosen */
const PH_OPEN = 182
const PX = NODES[DELIVERY].x - PW / 2
const PY = Y - 50 - PH
const OPTIONS = [
  { name: 'Express', eta: 'Tomorrow' },
  { name: 'Standard', eta: '2–3 days' },
  { name: 'Collect', eta: 'Today' },
] as const
const ROW_Y = (i: number): number => 58 + i * 36

const nodeTarget = (i: number) => ({ x: NODES[i].x + 5, y: Y + 3 })
const rowTarget = { x: PX + 130, y: PY + ROW_Y(0) + 16 }

const LEGS = [
  { a: 0.025, b: CLICK[0] - 0.012, from: { x: 160, y: 462 }, to: nodeTarget(0) },
  ...[1, 2, 3, 4].map((i) => ({ a: lineFrom(i) + 0.03, b: CLICK[i] - 0.012, from: nodeTarget(i - 1), to: nodeTarget(i) })),
  { a: CLICK[DELIVERY] + 0.03, b: PICK - 0.014, from: nodeTarget(DELIVERY), to: rowTarget },
  { a: CLOSE[0] - 0.005, b: CLICK[LAST] - 0.012, from: rowTarget, to: nodeTarget(LAST) },
]

const CLICKS = [
  ...CLICK.slice(0, LAST).map((c, i) => ({ at: c, ...nodeTarget(i) })),
  { at: PICK, ...rowTarget },
  { at: CLICK[LAST], ...nodeTarget(LAST) },
]

const cursorAt = (p: number) => {
  let pos: { x: number; y: number } = LEGS[0].from
  for (const leg of LEGS) {
    if (p < leg.a) break
    const t = seg(p, leg.a, leg.b)
    pos = { x: lerp(leg.from.x, leg.to.x, t), y: lerp(leg.from.y, leg.to.y, t) }
  }
  return pos
}

/** 1 at `at`, easing to 0 either side over `span` */
const bump = (p: number, at: number, span: number): number => clamp01(1 - Math.abs(p - at) / span)

const meta = { fontFamily: 'var(--font-sans)', fontSize: 'var(--scene-meta, 17px)', letterSpacing: '-0.01em' } as const

export function CommerceScene({ p }: { p: number }) {
  const tip = NODES.slice(1).reduce((sum, _, k) => sum + seg(p, lineFrom(k + 1), lineTo(k + 1)), 0)
  const tipX = lerp(NODES[0].x, NODES[LAST].x, tip / LAST)
  const moving = Math.max(0, ...NODES.slice(1).map((_, k) => clamp01(Math.min((p - lineFrom(k + 1)) / 0.01, (lineTo(k + 1) - p) / 0.01))))
  const current = CLICK.reduce((idx, c, i) => (p >= c ? i : idx), -1)

  const cursor = cursorAt(p)
  const cursorOpacity = seg(p, 0.02, 0.05) * (1 - seg(p, 0.955, 0.985))
  const cursorScale = 1 - 0.14 * Math.max(0, ...CLICKS.map((c) => bump(p, c.at, 0.02)))

  const open = seg(p, OPEN[0], OPEN[1], easeOut) * (1 - seg(p, CLOSE[0], CLOSE[1]))
  const pick = seg(p, PICK, PICK + 0.03, easeOut)
  const route = seg(p, ROUTE[0], ROUTE[1])
  const height = lerp(PH_OPEN, PH, seg(p, PICK, ROUTE[0] + 0.02))

  return (
    <svg viewBox={`0 0 ${SCENE_W} ${SCENE_H}`} role="presentation" aria-hidden="true" width="100%" height="100%">
      <DrawPath d={`M${NODES[0].x} ${Y} L${NODES[LAST].x} ${Y}`} t={1} stroke={ink2} width={1.5} dash="2 9" opacity={seg(p, 0, 0.06)} />
      <DrawPath d={`M${NODES[0].x} ${Y} L${NODES[LAST].x} ${Y}`} t={tip / LAST} stroke={accent} width={3} />
      {moving > 0 ? (
        <g opacity={moving}>
          <circle cx={tipX} cy={Y} r={16} fill="var(--accent-soft)" />
          <circle cx={tipX} cy={Y} r={6} fill={accent} />
        </g>
      ) : null}

      {NODES.map((n, i) => {
        const appear = seg(p, i * 0.012, i * 0.012 + 0.06)
        const reached = p >= CLICK[i]
        const act = seg(p, CLICK[i], CLICK[i] + 0.04, easeOut)
        const pop = 1 + 0.12 * Math.sin(Math.PI * seg(p, CLICK[i], CLICK[i] + 0.06, (t) => t))
        return (
          <g key={n.label}>
            <circle cx={n.x} cy={Y} r={50} fill="var(--accent-soft)" opacity={act * appear} />
            <Glyph icon={n.icon} x={n.x} y={Y + (1 - appear) * 14} size={54} scale={pop} color={reached ? accent : ink} opacity={appear} />
            <Label x={n.x} y={Y + 96} opacity={appear} fill={reached ? ink : ink2} className={i === current ? undefined : 'scene-label--minor'}>
              {n.label}
            </Label>
          </g>
        )
      })}

      {NODES.map((n, i) => {
        const inAt = CLICK[i] + 0.01
        const outAt = i === LAST ? 2 : CLICK[i + 1] - 0.005
        const opacity = seg(p, inAt, inAt + 0.025) * (1 - seg(p, outAt, outAt + 0.02))
        if (opacity < 0.01) return null
        return (
          <text key={n.caption} x={X0 - 8} y={150 + (1 - opacity) * 8} opacity={opacity} style={{ fontFamily: 'var(--font-sans)', fontSize: 'var(--scene-caption, 30px)', fontWeight: 600, letterSpacing: '-0.025em', fill: ink }}>
            {n.caption}
          </text>
        )
      })}

      {open > 0.01 ? (
        <g transform={`translate(${PX} ${PY + PH - height + (1 - open) * 14}) translate(${PW / 2} ${height}) scale(${0.94 + 0.06 * open}) translate(${-PW / 2} ${-height})`} opacity={open} style={{ filter: 'drop-shadow(0 18px 28px rgb(10 50 44 / 0.12))' }}>
          <rect width={PW} height={height} rx={16} fill="var(--paper)" stroke={line} strokeWidth={1} />
          <path d={`M${PW / 2 - 11} ${height} L${PW / 2} ${height + 11} L${PW / 2 + 11} ${height}`} fill="var(--paper)" stroke={line} strokeWidth={1} />
          <line x1={PW / 2 - 10} x2={PW / 2 + 10} y1={height} y2={height} stroke="var(--paper)" strokeWidth={2} />
          <text x={24} y={38} style={{ ...meta, fontWeight: 500, fill: ink3 }}>
            Delivery options
          </text>

          {OPTIONS.map((o, i) => {
            const y = ROW_Y(i)
            const on = seg(p, OPEN[0] + 0.01 + i * 0.012, OPEN[0] + 0.045 + i * 0.012)
            const chosen = i === 0 ? pick : 0
            const dim = i === 0 ? 1 : lerp(1, 0.4, pick)
            return (
              <g key={o.name} opacity={on * dim} transform={`translate(0 ${(1 - on) * 6})`}>
                {i === 0 ? <rect x={12} y={y} width={PW - 24} height={32} rx={9} fill="var(--accent-soft)" opacity={chosen} /> : null}
                <circle cx={36} cy={y + 16} r={8} fill="none" stroke={ink3} strokeWidth={1.4} opacity={1 - chosen} />
                {i === 0 ? (
                  <g opacity={chosen}>
                    <circle cx={36} cy={y + 16} r={8.5} fill={accent} />
                    <Glyph icon={Check} x={36} y={y + 16} size={12} color="#fff" strokeWidth={3} />
                  </g>
                ) : null}
                <text x={56} y={y + 22} style={{ ...meta, fontWeight: i === 0 ? 600 : 500, fill: ink }}>
                  {o.name}
                </text>
                <text x={PW - 24} y={y + 22} textAnchor="end" style={{ ...meta, fill: ink3 }}>
                  {o.eta}
                </text>
              </g>
            )
          })}

          <g opacity={seg(p, ROUTE[0] - 0.005, ROUTE[0] + 0.02)}>
            <DrawPath d="M36 196 L294 196" t={1} stroke={ink3} width={1.5} dash="2 8" />
            <DrawPath d="M36 196 L294 196" t={route} stroke={accent} width={2.5} />
            <circle cx={36} cy={196} r={4.5} fill={ink3} />
            <Glyph icon={MapPin} x={294} y={190} size={22} color={accent} strokeWidth={1.6} opacity={seg(route, 0.9, 1)} />
            <Glyph icon={Truck} x={lerp(36, 294, route)} y={178} size={22} color={ink} strokeWidth={1.5} opacity={1 - seg(route, 0.92, 1)} />
          </g>
          <text x={24} y={230} opacity={seg(p, ROUTE[0], ROUTE[0] + 0.02) * (1 - seg(p, ROUTE[1] - 0.01, ROUTE[1] + 0.01))} style={{ ...meta, fontWeight: 500, fill: ink3 }}>
            On its way
          </text>
          <text x={24} y={230} opacity={seg(p, ROUTE[1] - 0.01, ROUTE[1] + 0.02)} style={{ ...meta, fontWeight: 600, fill: accentInk }}>
            Arrives tomorrow
          </text>
        </g>
      ) : null}

      {CLICKS.map((c) => {
        const t = seg(p, c.at, c.at + 0.05, easeOut)
        return t > 0 && t < 1 ? <circle key={c.at} cx={c.x - 5} cy={c.y - 3} r={10 + 36 * t} fill="none" stroke={accent} strokeWidth={2} opacity={0.55 * (1 - t)} /> : null
      })}

      {cursorOpacity > 0.01 ? (
        <g transform={`translate(${cursor.x} ${cursor.y}) scale(${cursorScale})`} opacity={cursorOpacity} style={{ filter: 'drop-shadow(0 3px 5px rgb(10 50 44 / 0.28))' }}>
          <path d="M0 0 L0 20.5 L5.2 15.8 L8.8 24 L12.4 22.4 L8.8 14.4 L15.6 14.4 Z" fill={ink} stroke="#fff" strokeWidth={1.6} strokeLinejoin="round" />
        </g>
      ) : null}
    </svg>
  )
}
