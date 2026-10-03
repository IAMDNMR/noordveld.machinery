import { Check, ClipboardCheck, Cog, HandCoins, LifeBuoy, RefreshCw, ShoppingCart, Store, Tractor, Truck, User, Warehouse, Wrench } from 'lucide-react'
import { Noordveld } from './Logo'
import { PICKUP, arrival } from './acts2'
import { filmData as D } from './launchData'
import { box, easeInOut, enter, fall, lerp, lerpRect, rise, seg, spring, type Rect } from './motion'
import { P } from './timeline'
import { Bubble, Draw, Surface } from './ui'

/* ───────── Acts 7–10: the system takes over, transaction, service, reveal ───────── */

const PIPE = [
  { icon: User, label: 'Need', done: 'Need understood' },
  { icon: Tractor, label: 'Machine', done: 'Fitment checked' },
  { icon: Cog, label: 'Part', done: 'Part identified' },
  { icon: Warehouse, label: 'Sourcing', done: 'Sourcing checked' },
  { icon: Truck, label: 'Fulfilment', done: 'Fulfilment selected' },
  { icon: HandCoins, label: 'Transaction', done: 'Transaction prepared' },
] as const

const PIPE_SIZE = 150
const pipeRect = (i: number): Rect => ({ x: P.pipeX(i) - PIPE_SIZE / 2, y: P.pipeY - PIPE_SIZE / 2, w: PIPE_SIZE, h: PIPE_SIZE })
/** Where each card starts before the system gathers it into the line */
const SCATTER = [
  [-120, -170],
  [60, 190],
  [-40, -210],
  [150, 150],
  [-90, 200],
  [110, -160],
] as const

const TOTAL = Math.round((D.part.priceExVat + D.delivery.express.price) * 100) / 100
const euro = (n: number) => `€${n.toFixed(2)}`

export function ActAgentic({ t }: { t: number }) {
  if (t < 28.9 || t > 34.6) return null
  const line = seg(t, 30.2, 33.0, easeInOut)
  const out = fall(t, 33.3, 34.0)
  const checkoutRect: Rect = P.checkout
  const morph = seg(t, 33.5, 34.5, easeInOut)
  const lead = P.pipeX(0) + (P.pipeX(5) - P.pipeX(0)) * line

  return (
    <>
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true" style={{ opacity: out }}>
        <Draw d={`M${P.pipeX(0)} ${P.pipeY} L${P.pipeX(5)} ${P.pipeY}`} p={1} stroke="var(--line-strong)" width={1.5} dash="0.004 0.012" opacity={rise(t, 29.6, 30.2)} />
        <Draw d={`M${P.pipeX(0)} ${P.pipeY} L${P.pipeX(5)} ${P.pipeY}`} p={line} width={3.5} />
        {line > 0.01 && line < 0.995 ? (
          <g>
            <circle cx={lead} cy={P.pipeY} r={22} fill="var(--accent)" opacity={0.14} />
            <circle cx={lead} cy={P.pipeY} r={7} fill="var(--accent)" />
          </g>
        ) : null}
      </svg>

      {PIPE.map((n, i) => {
        const base = 29.45 + i * 0.11
        const e = seg(t, base, base + 0.9, spring)
        const act = rise(t, 30.2 + (i / 5) * 2.8 + 0.05, 30.2 + (i / 5) * 2.8 + 0.55)
        const [sx, sy] = SCATTER[i]
        const last = i === PIPE.length - 1
        const r = last ? lerpRect(pipeRect(i), checkoutRect, morph) : pipeRect(i)
        return (
          <div key={n.label}>
            <Surface
              rect={r}
              radius={lerp(22, 26, last ? morph : 0)}
              style={{
                opacity: Math.min(1, e * 1.4) * (last ? 1 : out),
                transform: `translate(${(1 - e) * sx}px, ${(1 - e) * sy}px) scale(${0.9 + 0.1 * e + 0.05 * act * (1 - act)})`,
                borderColor: act > 0.5 ? 'rgb(0 191 165 / 0.6)' : undefined,
              }}
            >
              <div className="lf-pipe" style={{ opacity: last ? 1 - morph : 1 }}>
                <Bubble icon={n.icon} size={64} on={act > 0.5} />
                <p className="lf-pipe__label">{n.label}</p>
                {act > 0.5 ? (
                  <span className="lf-pipe__tick" style={{ transform: `scale(${seg(t, 30.2 + (i / 5) * 2.8 + 0.1, 30.2 + (i / 5) * 2.8 + 0.5, spring)})` }}>
                    <Check size={16} strokeWidth={3} aria-hidden="true" />
                  </span>
                ) : null}
              </div>
            </Surface>
            <p className="lf-pipe__done" style={{ left: P.pipeX(i) - 120, top: P.pipeY + 100, opacity: act * out, transform: `translateY(${(1 - act) * 10}px)` }}>
              {n.done}
            </p>
          </div>
        )
      })}

      <div className="lf-message" style={{ opacity: out }}>
        <p style={enter(t, 31.3, 0.9, 20)}>It doesn’t just help you search.</p>
        <p className="is-strong" style={enter(t, 32.0, 0.9, 20)}>
          It moves the journey forward.
        </p>
      </div>
    </>
  )
}

export function ActTransaction({ t }: { t: number }) {
  if (t < 34.0 || t > 38.6) return null
  const out = fall(t, 37.5, 38.3)
  const click = 36.4
  const hover = rise(t, 35.9, 36.25) * (t < click ? 1 : 0)
  const press = seg(t, click - 0.05, click) * fall(t, click, click + 0.2)
  const done = seg(t, click + 0.05, click + 0.7, easeInOut)
  const ring = seg(t, click + 0.3, click + 1.0, easeInOut)
  const cont = P.cont
  const btn: Rect = { x: cont.x + (cont.w - 72) * done * 0.5, y: cont.y, w: lerp(cont.w, 72, done), h: cont.h }
  const rows: [string, string, string?][] = [
    ['Selected part', D.part.no, D.part.name],
    ['Quantity', '1'],
    ['Fulfilment', `Express · ${D.stock.find((x) => x.id === D.delivery.from)?.city ?? ''} to ${D.customer.city}`],
    ['Delivery', arrival(D.delivery.express.days)],
  ]
  const rowH = 82

  return (
    <div style={{ opacity: out }}>
      <Surface rect={P.checkout} radius={26} style={{ opacity: rise(t, 34.45, 34.55) }} />
      <div style={{ opacity: rise(t, 34.4, 34.9) }}>
        <p className="lf-eyebrow" style={{ position: 'absolute', left: P.checkout.x + 40, top: P.checkout.y + 34 }}>
          <ShoppingCart size={18} strokeWidth={1.7} aria-hidden="true" />
          Order summary
        </p>
        {rows.map(([k, v, sub], i) => (
          <div key={k} className="lf-row" style={{ left: P.checkout.x + 40, top: P.checkout.y + 84 + i * rowH, width: P.checkout.w - 80, ...enter(t, 34.5 + i * 0.17, 0.7, 14) }}>
            <span>{k}</span>
            <strong>
              {v}
              {sub ? <small>{sub}</small> : null}
            </strong>
          </div>
        ))}
        <div className="lf-row lf-row--total" style={{ left: P.checkout.x + 40, top: P.checkout.y + 84 + 4 * rowH + 8, width: P.checkout.w - 80, ...enter(t, 35.6, 0.7, 14) }}>
          <span>Total</span>
          <strong>
            {euro(TOTAL)}
            <small>excl. VAT</small>
          </strong>
        </div>
      </div>

      <div
        className="lf-btn"
        style={{
          ...box(btn),
          borderRadius: lerp(14, 36, done),
          transform: `translateY(${-5 * hover}px) scale(${1 - 0.04 * press})`,
          opacity: rise(t, 35.2, 35.8),
          background: done > 0.5 ? 'var(--accent-ink)' : undefined,
          boxShadow: `0 ${12 + 12 * hover}px ${28 + 12 * hover}px -14px rgb(0 117 106 / ${0.4 + 0.2 * hover})`,
        }}
      >
        <span style={{ opacity: fall(t, click, click + 0.18) }}>Continue</span>
        <svg viewBox="0 0 72 72" width="72" height="72" style={{ position: 'absolute', left: (btn.w - 72) / 2, top: 0, opacity: done }} aria-hidden="true">
          <circle cx="36" cy="36" r="30" fill="none" stroke="rgb(255 255 255 / 0.4)" strokeWidth="3" />
          <Draw d="M36 6 A30 30 0 1 1 35.99 6" p={ring} stroke="#fff" width={3} />
          <Draw d="M24 37 L33 46 L49 28" p={seg(t, click + 0.65, click + 1.1, easeInOut)} stroke="#fff" width={4} />
        </svg>
      </div>
      <p className="lf-confirm" style={{ top: cont.y + cont.h + 10, opacity: rise(t, click + 0.8, click + 1.3), transform: `translateY(${(1 - rise(t, click + 0.8, click + 1.3)) * 10}px)` }}>
        Order confirmed
      </p>
    </div>
  )
}

const SVC_CHAIN = [
  { icon: Tractor, label: 'Machine', value: D.machine.model },
  { icon: Cog, label: 'Part', value: D.part.no },
  { icon: Wrench, label: 'Service', value: 'Machine support' },
  { icon: Store, label: 'Dealer', value: PICKUP?.name ?? 'Not configured' },
  { icon: User, label: 'Customer', value: D.customer.name },
] as const

const SVC_OPTIONS = [
  { icon: Wrench, name: 'Service' },
  { icon: ClipboardCheck, name: 'Maintenance' },
  { icon: RefreshCw, name: 'Replacement' },
  { icon: LifeBuoy, name: 'Support' },
] as const

export function ActService({ t }: { t: number }) {
  if (t < 37.4 || t > 42.6) return null
  const out = fall(t, 41.5, 42.3)
  const hours = D.machine.serviceInterval.map((h) => h.toLocaleString('en-US')).join(' · ')
  return (
    <div style={{ opacity: out }}>
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true">
        {SVC_CHAIN.slice(0, -1).map((_, i) => (
          <Draw key={i} d={`M${P.svcX(i) + 46} ${P.svcY} L${P.svcX(i + 1) - 46} ${P.svcY}`} p={rise(t, 38.2 + i * 0.27, 38.65 + i * 0.27, easeInOut)} width={2.5} />
        ))}
      </svg>
      {SVC_CHAIN.map((n, i) => {
        const e = enter(t, 37.9 + i * 0.27, 0.7, 20)
        const lit = n.label === 'Service'
        return (
          <div key={n.label} className="lf-node" style={{ left: P.svcX(i) - 140, top: P.svcY - 38, ...e }}>
            <Bubble icon={n.icon} size={76} on style={lit ? { boxShadow: `0 0 0 ${10 * rise(t, 39.4, 40)}px rgb(0 191 165 / ${0.16 * rise(t, 39.4, 40)})` } : undefined} />
            <p className="lf-eyebrow">{n.label}</p>
            <p className="lf-node__value">{n.value}</p>
          </div>
        )
      })}

      <Surface rect={{ x: 320, y: 500, w: 960, h: 280 }} radius={22} style={enter(t, 39.3, 0.9, 30)}>
        <div className="lf-svc">
          <p className="lf-eyebrow">{D.machine.model} · {D.machine.plant}</p>
          <h3 className="lf-title lf-title--sm">Machine support</h3>
          <ul>
            {SVC_OPTIONS.map((o, i) => (
              <li key={o.name} style={enter(t, 39.9 + i * 0.2, 0.7, 14)}>
                <o.icon size={22} strokeWidth={1.6} aria-hidden="true" />
                {o.name}
              </li>
            ))}
          </ul>
          <p className="lf-fact__sub" style={{ opacity: rise(t, 40.8, 41.3) }}>
            Planned service intervals in the dataset: {hours} hours (demo)
          </p>
        </div>
      </Surface>
    </div>
  )
}

const WAVE = 'M-60 580 C 260 470, 500 690, 800 570 S 1330 460, 1660 560'
const BEZ: readonly (readonly [number, number])[][] = [
  [[-60, 580], [260, 470], [500, 690], [800, 570]],
  [[800, 570], [1100, 450], [1330, 460], [1660, 560]],
]
/** A point on the wave at fraction d (0–1) of its length, so the dots sit exactly on the line. */
const onWave = (d: number): { x: number; y: number } => {
  const [a, b, c, e] = BEZ[d < 0.5 ? 0 : 1]
  const u = (d < 0.5 ? d : d - 0.5) * 2
  const m = 1 - u
  const f = (i: 0 | 1) => m * m * m * a[i] + 3 * m * m * u * b[i] + 3 * m * u * u * c[i] + u * u * u * e[i]
  return { x: f(0), y: f(1) }
}
const WAVE_DOTS = [0.14, 0.32, 0.5, 0.68, 0.86] as const

export function ActReveal({ t }: { t: number }) {
  if (t < 41.4) return null
  const line = seg(t, 41.9, 43.5, easeInOut)
  const dim = lerp(1, 0.4, seg(t, 43.8, 45))
  const words = ['AGENTIC', 'COMMERCE']
  const sub = enter(t, 44.4, 0.9, 16)
  const logo = enter(t, 45.3, 0.9, 12)
  return (
    <>
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true" style={{ opacity: dim }}>
        <Draw d={WAVE} p={line} width={3.5} />
        {WAVE_DOTS.map((d, i) => {
          const on = seg(line, d, d + 0.04)
          const { x, y } = onWave(d)
          return on > 0 ? <circle key={i} cx={x} cy={y} r={7 * on} fill="var(--accent)" /> : null
        })}
        {line > 0.01 && line < 0.99 ? <circle cx={onWave(line).x} cy={onWave(line).y} r={9} fill="var(--accent)" /> : null}
      </svg>

      <div className="lf-wordmark" style={{ top: 70 }}>
        {words.map((w, i) => {
          const e = seg(t, 43.2 + i * 0.35, 44.4 + i * 0.35, spring)
          return (
            <span key={w} className={`lf-mask ${i === 1 ? 'is-accent' : ''}`}>
              <span style={{ display: 'inline-block', transform: `translateY(${(1 - e) * 105}%)`, opacity: Math.min(1, e * 2) }}>{w}</span>
            </span>
          )
        })}
      </div>
      <p className="lf-sub" style={{ ...sub }}>
        From need to fulfilment.
      </p>
      <div className="lf-logo" style={logo}>
        <Noordveld />
      </div>
    </>
  )
}
