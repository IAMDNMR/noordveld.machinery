import { Boxes, Check, Cog, History, MapPin, Search, Timer, Tractor, Warehouse } from 'lucide-react'
import { machineImageUrl } from '../../../../src/lib/assets'
import { filmData as D } from './launchData'
import { box, clamp01, easeInOut, easeLinear, enter, fall, lerp, lerpRect, rise, seg, spring, type Rect } from './motion'
import { P, QUERY } from './timeline'
import { Bubble, Draw, Surface } from './ui'

/* ───────── Acts 1–3: the need, understanding it, the machine ───────── */

const CHIPS = [
  { icon: Tractor, label: 'Machine', value: D.machine.model },
  { icon: Cog, label: 'Part', value: 'Hydraulic hose' },
  // Not typed: the location comes from the customer's account
  { icon: MapPin, label: 'Location', value: D.customer.city },
  { icon: Timer, label: 'Urgency', value: 'Machine down' },
] as const

const WAKE_DOTS = [
  [300, 300],
  [1300, 320],
  [230, 640],
  [1390, 620],
  [520, 770],
  [1110, 790],
  [1460, 440],
  [150, 450],
] as const

const MINI: Rect = { x: 100, y: 200, w: 220, h: 170 }
const MACHINE_IMG: Rect = { x: 180, y: 160, w: 640, h: 580 }

export function ActNeed({ t }: { t: number }) {
  // The field: born in the middle of the page, then rises to the top and widens for the query
  const grow = seg(t, 3.5, 4.5, easeInOut)
  const f = lerpRect(P.field0, P.field1, grow)
  const fieldOut = fall(t, 8.9, 9.6)
  const focus = rise(t, 3.3, 3.6)
  const typed = Math.floor(seg(t, 4.3, 6.3, easeLinear) * QUERY.length)
  const showCaret = focus > 0.5 && fieldOut > 0.5 && Math.floor(t * 2) % 2 === 0
  const pressed = t > 7.05 && t < 7.3
  const headOut = fall(t, 3.5, 4.4)
  const words = ['I need', 'something.']

  return (
    <>
      <div className="lf-head" style={{ left: 0, top: 255, width: 1600, opacity: headOut, transform: `translateY(${(1 - headOut) * -50}px)` }}>
        {words.map((w, i) => {
          const e = seg(t, 0.35 + i * 0.3, 1.3 + i * 0.3, spring)
          return (
            <span key={w} className="lf-mask">
              <span style={{ display: 'inline-block', transform: `translateY(${(1 - e) * 110}%)`, opacity: clamp01(e * 2) }}>{w}</span>
            </span>
          )
        })}
      </div>

      {/* The interface wakes up around the field */}
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true" style={{ opacity: fall(t, 5.0, 6.2) }}>
        {WAKE_DOTS.map(([x, y], i) => {
          const a = rise(t, 3.35 + i * 0.07, 3.9 + i * 0.07)
          return (
            <g key={i} opacity={a}>
              <circle cx={x} cy={y - 12 * grow} r={4 * a} fill="var(--accent)" opacity={0.6} />
              <circle cx={x} cy={y - 12 * grow} r={12 + 10 * a} fill="var(--accent)" opacity={0.1 * a} />
            </g>
          )
        })}
      </svg>

      <div
        className={`lf-field ${focus > 0.5 ? 'is-focus' : ''}`}
        style={{
          ...box(f),
          opacity: rise(t, 1.5, 2.3) * fieldOut,
          transform: `translateY(${(1 - rise(t, 1.5, 2.4, spring)) * 24 - (1 - fieldOut) * 30}px)`,
          boxShadow: `0 0 0 ${5 * focus}px rgb(0 191 165 / ${0.16 * focus}), 0 24px 48px -26px rgb(10 50 44 / 0.28)`,
        }}
      >
        <Search size={30} strokeWidth={1.6} className="lf-field__icon" aria-hidden="true" />
        <span className="lf-field__text">
          {typed > 0 ? QUERY.slice(0, typed) : null}
          {showCaret ? <i className="lf-caret" /> : null}
        </span>
        <span className="lf-field__go" style={{ opacity: seg(t, 4.5, 5.1), transform: `scale(${pressed ? 0.9 : 1})`, background: pressed ? 'var(--accent-ink)' : undefined }}>
          <Search size={26} strokeWidth={2} aria-hidden="true" />
        </span>
      </div>
    </>
  )
}

export function ActUnderstand({ t }: { t: number }) {
  const exit = fall(t, 8.75, 9.4)
  return (
    <>
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true">
        {CHIPS.map((_, i) => {
          const cx = P.chipX(i) + P.chipW / 2
          const p = rise(t, 7.1 + i * 0.3, 7.9 + i * 0.3, easeInOut)
          return <Draw key={i} d={`M800 226 C800 280 ${cx} 270 ${cx} ${P.chipY}`} p={p} width={2} opacity={exit * 0.8} />
        })}
      </svg>
      {CHIPS.map((c, i) => {
        if (i === 0) return null
        const e = enter(t, 7.3 + i * 0.3, 0.8)
        return (
          <Surface key={c.label} rect={{ x: P.chipX(i), y: P.chipY, w: P.chipW, h: P.chipH }} style={{ ...e, opacity: (e.opacity as number) * exit }} radius={16}>
            <ChipBody icon={c.icon} label={c.label} value={c.value} />
          </Surface>
        )
      })}
    </>
  )
}

function ChipBody({ icon, label, value }: { icon: (typeof CHIPS)[number]['icon']; label: string; value: string }) {
  return (
    <div className="lf-chip">
      <Bubble icon={icon} size={52} on />
      <div>
        <p className="lf-eyebrow">{label}</p>
        <p className="lf-chip__value">{value}</p>
      </div>
    </div>
  )
}

/** The machine chip is the one thing that survives: it grows into the machine card, then shrinks into the chain. */
export function ActMachine({ t }: { t: number }) {
  const chipRect: Rect = { x: P.chipX(0), y: P.chipY, w: P.chipW, h: P.chipH }
  const expand = seg(t, 8.8, 9.9, easeInOut)
  const shrink = seg(t, 12.0, 13.0, easeInOut)
  const r = lerpRect(lerpRect(chipRect, P.card, expand), MINI, shrink)
  const chipE = enter(t, 7.3, 0.8)
  const chipContent = fall(t, 8.8, 9.3)
  const tag = rise(t, 9.2, 9.9) * fall(t, 12.0, 12.5)
  const miniOut = fall(t, 16.3, 16.9)
  const body = rise(t, 9.6, 10.2) * fall(t, 11.8, 12.4)
  const press = seg(t, 8.7, 8.8) * fall(t, 8.8, 9.0)

  if (t < 7.2 || t > 17) return null

  const imgRect = lerpRect(MACHINE_IMG, { x: MINI.x + 10, y: MINI.y + 10, w: MINI.w - 20, h: 100 }, shrink)
  const img = machineImageUrl(D.machine.slug, 'main')
  const reveal = seg(t, 9.5, 10.8, easeInOut)

  const tiles = [
    { icon: Cog, label: 'Parts', value: String(D.machine.partsFitted), sub: 'parts fitted' },
    { icon: Check, label: 'Fitment', value: 'In catalogue', sub: 'stated per model' },
    { icon: History, label: 'Legacy reference', value: `${D.machine.legacyMapped} mapped`, sub: 'old part numbers' },
    { icon: Boxes, label: 'Availability', value: `${D.machine.inStock} of ${D.machine.partsFitted}`, sub: 'parts in stock' },
    { icon: Warehouse, label: 'Location', value: D.machine.plant, sub: D.machine.country },
  ] as const
  const tileRect = (i: number): Rect => (i < 4 ? { x: P.tilesX[i % 2], y: P.tilesY[Math.floor(i / 2)], w: P.tile.w, h: P.tile.h } : { x: P.tilesX[0], y: P.tilesY[2], w: 560, h: P.tile.h })

  return (
    <>
      <div className="lf-qtag" style={{ opacity: tag, transform: `translateY(${(1 - tag) * -14}px)` }}>
        <Search size={20} strokeWidth={1.8} aria-hidden="true" />
        {QUERY}
      </div>

      <Surface rect={r} radius={lerp(16, 22, expand)} style={{ ...chipE, opacity: (chipE.opacity as number) * miniOut, transform: `scale(${1 - 0.03 * press})` }}>
        <div style={{ opacity: chipContent }}>
          <ChipBody icon={CHIPS[0].icon} label={CHIPS[0].label} value={CHIPS[0].value} />
        </div>
      </Surface>

      {expand > 0.4 ? (
        <>
          <div className="lf-img" style={{ ...box(imgRect), borderRadius: lerp(14, 10, shrink), clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0 round 14px)`, opacity: miniOut }}>
            {img ? <img src={img} alt="" style={{ transform: `scale(${lerp(1.14, 1, seg(t, 9.5, 13, easeInOut))})` }} /> : <div className="lf-img__none" />}
          </div>
          <p className="lf-mini" style={{ opacity: rise(t, 12.8, 13.3) * miniOut, left: MINI.x + 14, top: MINI.y + 124 }}>
            {D.machine.model}
            <small>{D.machine.type}</small>
          </p>

          <div style={{ opacity: body }}>
            <div style={{ position: 'absolute', left: 880, top: 160, ...enter(t, 9.8, 0.8, 18) }}>
              <p className="lf-eyebrow">Machine</p>
              <h3 className="lf-title">{D.machine.name}</h3>
            </div>
            {tiles.map((tile, i) => {
              const e = enter(t, 10.2 + i * 0.22, 0.8, 22)
              const isParts = i === 0
              const hv = isParts ? rise(t, 10.9, 11.4) : 0
              const pr = isParts ? seg(t, 11.7, 11.8) * fall(t, 11.8, 12.0) : 0
              return (
                <Surface key={tile.label} rect={tileRect(i)} lift={hv} radius={14} style={{ ...e, transform: `${e.transform} scale(${1 - 0.03 * pr})`, background: isParts && t > 11.75 ? 'var(--accent-soft)' : undefined }}>
                  <div className="lf-tile">
                    <p className="lf-eyebrow">
                      <tile.icon size={18} strokeWidth={1.7} aria-hidden="true" />
                      {tile.label}
                    </p>
                    <p className="lf-tile__value">{tile.value}</p>
                    <p className="lf-tile__sub">{tile.sub}</p>
                  </div>
                </Surface>
              )
            })}
          </div>
        </>
      ) : null}
    </>
  )
}
