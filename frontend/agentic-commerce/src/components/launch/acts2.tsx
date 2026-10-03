import { Boxes, Check, Cog, Droplets, Factory, History, MapPin, Package, Ruler, Store, Tractor, Warehouse, Zap } from 'lucide-react'
import { filmData as D } from './launchData'
import { box, easeInOut, enter, fall, lerp, lerpRect, rise, seg, type Rect } from './motion'
import { P } from './timeline'
import { Bubble, Draw, Surface } from './ui'

/* ───────── Acts 4–6: part intelligence, sourcing, fulfilment ───────── */

/** The dealer in the customer's own city that holds the part (pickup allowed), if the dataset has one */
export const PICKUP = D.stock.find((s) => s.id === D.pickupDealer)

export const arrival = (days: number): string => (days <= 1 ? 'Arrives tomorrow' : `Arrives in ${days} days`)

const LIST = D.siblings.slice(0, 3)
const listRect = (i: number): Rect => ({ x: P.listCard.x(i), y: P.listCard.y, w: P.listCard.w, h: P.listCard.h })

const CHAIN = [
  { icon: Tractor, label: 'Machine', value: D.machine.model },
  { icon: Cog, label: 'Compatible part', value: D.part.no },
  { icon: History, label: 'Legacy reference', value: D.part.legacyNo },
  { icon: Factory, label: 'Supplier', value: D.supplier.name },
  { icon: Store, label: 'Dealer', value: PICKUP?.name ?? 'Not configured' },
] as const

export function ActPart({ t }: { t: number }) {
  if (t < 12.5 || t > 18.8) return null
  const out = fall(t, 17.8, 18.3)
  const click = 14.9
  const grow = seg(t, click + 0.05, click + 1.05, easeInOut)
  const others = fall(t, click + 0.05, click + 0.6)
  const hover = rise(t, 14.0, 14.45) * (t < click + 0.1 ? 1 : 0)
  const press = seg(t, click - 0.05, click) * fall(t, click, click + 0.2)
  const detail = lerpRect(listRect(0), P.detail, grow)

  return (
    <div style={{ opacity: out, transform: `scale(${lerp(0.96, 1, out)})`, transformOrigin: '800px 450px' }}>
      {LIST.map((p, i) => {
        if (i > 0 && others < 0.01) return null
        const e = enter(t, 12.9 + i * 0.18, 0.8, 30)
        if (i === 0) {
          return (
            <Surface key={p.no} rect={detail} lift={hover * (1 - grow)} radius={lerp(16, 22, grow)} style={{ ...e, transform: `${e.transform} scale(${1 - 0.025 * press})` }}>
              <div style={{ opacity: fall(t, click + 0.05, click + 0.3) }}>
                <PartListBody no={p.no} name={p.name} />
              </div>
              {grow > 0.2 ? <PartDetail t={t} /> : null}
            </Surface>
          )
        }
        return (
          <Surface key={p.no} rect={listRect(i)} radius={16} style={{ ...e, opacity: (e.opacity as number) * others, transform: `${e.transform} translateX(${(1 - others) * 40}px)` }}>
            <PartListBody no={p.no} name={p.name} />
          </Surface>
        )
      })}

      {/* Relationship lines grow outward from the part, then the chain forms */}
      <svg className="lf-svg" viewBox="0 0 1600 900" aria-hidden="true">
        <Draw d={`M800 ${P.detail.y + P.detail.h} L800 ${P.chainY - 40}`} p={rise(t, 16.1, 16.7, easeInOut)} width={2} opacity={0.75} />
        {CHAIN.slice(0, -1).map((_, i) => (
          <Draw key={i} d={`M${P.chainX(i) + 46} ${P.chainY} L${P.chainX(i + 1) - 46} ${P.chainY}`} p={rise(t, 16.6 + i * 0.32, 17.1 + i * 0.32, easeInOut)} width={2.5} />
        ))}
      </svg>
      {CHAIN.map((n, i) => {
        const e = enter(t, 16.4 + i * 0.32, 0.7, 20)
        return (
          <div key={n.label} className="lf-node" style={{ left: P.chainX(i) - 140, top: P.chainY - 38, ...e }}>
            <Bubble icon={n.icon} size={76} on />
            <p className="lf-eyebrow">{n.label}</p>
            <p className="lf-node__value">{n.value}</p>
          </div>
        )
      })}
    </div>
  )
}

function PartListBody({ no, name }: { no: string; name: string }) {
  return (
    <div className="lf-pcard">
      <Bubble icon={Droplets} size={50} />
      <p className="lf-mono">{no}</p>
      <p className="lf-pcard__name">{name}</p>
      <p className="lf-pcard__fit">Fits {D.machine.model}</p>
    </div>
  )
}

function PartDetail({ t }: { t: number }) {
  const rows: [string, string][] = [
    ['Unified part number', D.part.no],
    ['Category', `${D.part.category} · ${D.part.subcategory}`],
    ['Fitment', D.part.fits.join(' · ')],
    ['Legacy code', `${D.part.legacyNo}${D.part.legacyBusiness ? ` (${D.part.legacyBusiness})` : ''}`],
  ]
  return (
    <div className="lf-detail" style={{ opacity: rise(t, 15.0, 15.35) }}>
      <div className="lf-pvis" style={{ ...enter(t, 15.0, 0.9, 16) }}>
        <Droplets size={120} strokeWidth={0.8} aria-hidden="true" />
        <span className="lf-mono">{D.part.no}</span>
      </div>
      <div className="lf-detail__main">
        <p className="lf-eyebrow">Part</p>
        <h3 className="lf-title lf-title--sm">{D.part.name}</h3>
        <dl>
          {rows.map(([k, v], i) => (
            <div key={k} style={enter(t, 15.45 + i * 0.16, 0.7, 14)}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <p className="lf-note" style={enter(t, 16.15, 0.7, 10)}>
          {D.part.specNote}
        </p>
      </div>
    </div>
  )
}


/* ───────── Sourcing + fulfilment on one map ───────── */

type Kind = 'supplier' | 'warehouse' | 'dealer' | 'customer'
interface Member {
  id: string
  kind: Kind
  name: string
  available?: number
}
interface Place {
  city: string
  x: number
  y: number
  at: number
  members: Member[]
}

const ICON: Record<Kind, typeof Warehouse> = { supplier: Factory, warehouse: Warehouse, dealer: Store, customer: MapPin }
const BUBBLE = 40
const STEP = 48

/**
 * Places, not pins: everything in one city sits in one row with one label, so nothing overlaps. Positions come from the
 * dataset's approximate city centres, fitted to the panel (a schematic map, not a geographic one).
 */
const PLACES: Place[] = (() => {
  const raw: (Member & { city: string; lat: number; lon: number; at: number })[] = [
    { id: D.supplier.id, kind: 'supplier', name: D.supplier.name, city: D.supplier.city, lat: D.supplier.lat, lon: D.supplier.lon, at: 18.7 },
    ...D.stock.filter((s) => s.kind === 'warehouse').map((s, i) => ({ id: s.id, kind: 'warehouse' as const, name: s.name, city: s.city, lat: s.lat, lon: s.lon, at: 19.2 + i * 0.14, available: s.available })),
    ...D.stock.filter((s) => s.kind === 'dealer').map((s, i) => ({ id: s.id, kind: 'dealer' as const, name: s.name, city: s.city, lat: s.lat, lon: s.lon, at: 19.85 + i * 0.14, available: s.available })),
    { id: D.customer.id, kind: 'customer', name: D.customer.name, city: D.customer.city, lat: D.customer.lat, lon: D.customer.lon, at: 20.5 },
  ]
  const lats = raw.map((r) => r.lat)
  const lons = raw.map((r) => r.lon)
  const [la0, la1, lo0, lo1] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)]
  const pad = { l: 60, r: 230, t: 70, b: 90 }
  const ky = (P.map.h - pad.t - pad.b) / ((la1 - la0) * 111)
  const kx = Math.min(ky * 1.7, (P.map.w - pad.l - pad.r) / ((lo1 - lo0) * 68))
  const groups = new Map<string, Place>()
  for (const r of raw) {
    const key = `${r.lat},${r.lon}`
    const place = groups.get(key) ?? { city: r.city, x: pad.l + (r.lon - lo0) * 68 * kx, y: pad.t + (la1 - r.lat) * 111 * ky, at: r.at, members: [] }
    place.members.push({ id: r.id, kind: r.kind, name: r.name, available: r.available })
    place.at = Math.min(place.at, r.at)
    groups.set(key, place)
  }
  // The customer always reads first in its place
  for (const p of groups.values()) p.members.sort((a, b) => Number(b.kind === 'customer') - Number(a.kind === 'customer'))
  return [...groups.values()]
})()

const placeOf = (id: string) => PLACES.find((p) => p.members.some((m) => m.id === id)) as Place
const pointOf = (id: string) => {
  const p = placeOf(id)
  return { x: p.x + p.members.findIndex((m) => m.id === id) * STEP, y: p.y }
}

const FROM_PLACE = placeOf(D.delivery.from)
const TO_PLACE = placeOf(D.customer.id)
const FROM = pointOf(D.delivery.from)
const TO = pointOf(D.customer.id)
const FROM_STOCK = D.stock.find((s) => s.id === D.delivery.from)
/** A gentle arc, bowed to the left of travel */
const CTRL = (() => {
  const dx = TO.x - FROM.x
  const dy = TO.y - FROM.y
  return { x: (FROM.x + TO.x) / 2 + dy * 0.28, y: (FROM.y + TO.y) / 2 - dx * 0.28 }
})()
const ROUTE = `M${FROM.x} ${FROM.y} Q${CTRL.x} ${CTRL.y} ${TO.x} ${TO.y}`
const onRoute = (u: number) => ({ x: (1 - u) ** 2 * FROM.x + 2 * (1 - u) * u * CTRL.x + u * u * TO.x, y: (1 - u) ** 2 * FROM.y + 2 * (1 - u) * u * CTRL.y + u * u * TO.y })
const MID = onRoute(0.5)

const warehouseTotal = D.stock.filter((s) => s.kind === 'warehouse').reduce((n, s) => n + s.available, 0)
const dealersWithStock = D.stock.filter((s) => s.kind === 'dealer' && s.available > 0)
const faster = D.delivery.standard.days - D.delivery.express.days

const FACTS = [
  { icon: Factory, label: 'Supplier', value: D.supplier.name, sub: `${D.supplier.city} · primary · ${D.supplier.leadDays} days lead time` },
  { icon: Store, label: 'Dealers', value: `${dealersWithStock.length} hold stock`, sub: PICKUP ? `${PICKUP.name}, ${PICKUP.city} · ${PICKUP.available}` : 'None in your city' },
  { icon: MapPin, label: 'Location', value: `${D.customer.city}, NL`, sub: `${D.customer.name} · from account` },
  { icon: Boxes, label: 'Availability', value: `${warehouseTotal} in warehouses`, sub: `${FROM_STOCK?.available ?? 0} at ${FROM_PLACE.city}, the nearest` },
  { icon: Ruler, label: 'Distance', value: `${D.delivery.km} km`, sub: `${FROM_PLACE.city} to ${D.customer.city}, road estimate` },
] as const

const OPTIONS = [
  { name: 'Express', price: `€${D.delivery.express.price.toFixed(2)}`, meta: `${D.delivery.express.days} days · from ${FROM_PLACE.city}` },
  { name: 'Standard', price: `€${D.delivery.standard.price.toFixed(2)}`, meta: `${D.delivery.standard.days} days · from ${FROM_PLACE.city}` },
  { name: 'Collect', price: 'Not configured', meta: PICKUP ? `${PICKUP.name} · ${PICKUP.available} in stock` : 'No dealer stock in your city' },
] as const

const TRACK = [
  { at: 26.35, text: 'Order confirmed', sub: `${D.part.no} × 1` },
  { at: 26.85, text: 'Preparing shipment', sub: `${FROM_PLACE.city} warehouse` },
  { at: 27.4, text: 'On the way', sub: `${D.delivery.km} km to ${D.customer.city}` },
  { at: 28.55, text: arrival(D.delivery.express.days), sub: `Express · ${D.customer.name}` },
] as const

const CLICK_EXPRESS = 25.7

export function ActSourcing({ t }: { t: number }) {
  if (t < 17.8 || t > 29.8) return null
  const panelIn = rise(t, 18.15, 18.85)
  const panelOut = fall(t, 28.95, 29.45)
  const toFulfil = seg(t, 24.2, 24.7, easeInOut)
  const tabX = lerp(P.tabs.sourcing.x, P.tabs.fulfilment.x, toFulfil)
  const tabW = lerp(P.tabs.sourcing.w, P.tabs.fulfilment.w, toFulfil)

  // The camera inside the map: settles on the route once Express is chosen
  const focus = seg(t, 25.9, 27.0, easeInOut)
  const zoom = lerp(1, 1.28, focus)
  const tx = focus * (P.map.w / 2 - zoom * MID.x)
  const ty = focus * (P.map.h / 2 - zoom * MID.y)

  const route = rise(t, 21.1, 22.3, easeInOut)
  const travel = seg(t, 27.4, 28.55, easeInOut)
  const pkg = onRoute(travel)
  const arrived = rise(t, 28.55, 29.0)

  const hover = rise(t, 25.0, 25.4) * (t < CLICK_EXPRESS ? 1 : 0)
  const press = seg(t, CLICK_EXPRESS - 0.05, CLICK_EXPRESS) * fall(t, CLICK_EXPRESS, CLICK_EXPRESS + 0.2)
  const chosen = rise(t, CLICK_EXPRESS, CLICK_EXPRESS + 0.35)
  const collapse = seg(t, 25.95, 26.45, easeInOut)
  const expand = Math.max(hover, chosen * (1 - collapse))

  return (
    <div style={{ opacity: panelIn * panelOut, transform: `scale(${0.97 + 0.03 * panelIn})`, transformOrigin: '800px 450px' }}>
      <Surface rect={P.panel} radius={26} />

      <div className="lf-tabs" style={{ left: P.tabs.sourcing.x, top: P.tabs.y, opacity: rise(t, 18.6, 19.1) }}>
        <i style={{ left: tabX - P.tabs.sourcing.x, width: tabW }} />
        <span className={toFulfil < 0.5 ? 'is-on' : ''} style={{ width: P.tabs.sourcing.w }}>
          Sourcing
        </span>
        <span className={toFulfil >= 0.5 ? 'is-on' : ''} style={{ width: P.tabs.fulfilment.w }}>
          Fulfilment
        </span>
      </div>

      {/* Sourcing: what the system found */}
      <div style={{ opacity: fall(t, 24.2, 24.55), transform: `translateX(${-24 * toFulfil}px)` }}>
        {FACTS.map((f, i) => (
          <div key={f.label} className="lf-fact" style={{ left: 130, top: 188 + i * 118, ...enter(t, 18.5 + i * 0.2, 0.7, 18) }}>
            <Bubble icon={f.icon} size={52} on />
            <div>
              <p className="lf-eyebrow">{f.label}</p>
              <p className="lf-fact__value">{f.value}</p>
              <p className="lf-fact__sub">{f.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Fulfilment: three ways to get it, then the shipment itself */}
      {t > 24.3 ? (
        <div>
          {OPTIONS.map((o, i) => {
            const e = enter(t, 24.45 + i * 0.14, 0.7, 16)
            const isExpress = i === 0
            const h = isExpress ? lerp(lerp(P.opt.h, 156, expand), 84, collapse) : P.opt.h
            const y = isExpress ? P.opt.y(0) : P.opt.y(i) + (156 - P.opt.h) * expand
            const gone = isExpress ? 1 : fall(t, 25.85, 26.15)
            const dim = isExpress ? 1 : lerp(1, 0.5, chosen)
            if (gone < 0.01) return null
            const on = isExpress && chosen > 0.5
            return (
              <Surface
                key={o.name}
                rect={{ x: P.opt.x, y, w: P.opt.w, h }}
                lift={isExpress ? hover : 0}
                radius={16}
                style={{ ...e, opacity: (e.opacity as number) * dim * gone, transform: `${e.transform} translateY(${(1 - gone) * -12}px) scale(${1 - 0.025 * (isExpress ? press : 0)})`, background: on ? 'var(--accent-soft)' : undefined, borderColor: on ? 'rgb(0 191 165 / 0.5)' : undefined }}
              >
                <div className="lf-opt">
                  <span className={`lf-radio ${on ? 'is-on' : ''}`}>{on ? <Check size={16} strokeWidth={3} aria-hidden="true" /> : null}</span>
                  <div className="lf-opt__main">
                    <p className="lf-opt__name">{o.name}</p>
                    <p className="lf-opt__sub" style={isExpress ? { opacity: 1 - collapse } : undefined}>
                      {o.meta}
                    </p>
                    {isExpress && faster > 0 ? (
                      <p className="lf-opt__gain" style={{ opacity: Math.max(0, expand - 2 * collapse), transform: `translateY(${(1 - expand) * 6}px)` }}>
                        <Zap size={15} strokeWidth={2} aria-hidden="true" />
                        {faster} {faster === 1 ? 'day' : 'days'} faster than Standard
                      </p>
                    ) : null}
                  </div>
                  <p className={`lf-opt__price ${o.price === 'Not configured' ? 'is-muted' : ''}`}>{o.price}</p>
                </div>
              </Surface>
            )
          })}

          <div className="lf-track-list" style={{ left: P.opt.x + 6, top: P.opt.y(0) + 120, opacity: rise(t, 26.3, 26.7) }}>
            <i className="lf-track-list__rail" />
            <i className="lf-track-list__fill" style={{ height: `${Math.min(1, Math.max(0, seg(t, 26.35, 28.55, (u) => u))) * 100}%` }} />
            {TRACK.map((s, i) => {
              const active = t >= s.at
              const done = i < TRACK.length - 1 ? t >= TRACK[i + 1].at : t >= s.at + 0.3
              const e = enter(t, 26.3 + i * 0.1, 0.6, 10)
              return (
                <div key={s.text} className={`lf-step ${active ? 'is-active' : ''} ${done ? 'is-done' : ''} ${i === TRACK.length - 1 ? 'is-last' : ''}`} style={e}>
                  <span className="lf-step__dot">{done ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : null}</span>
                  <div>
                    <p className="lf-step__text">{s.text}</p>
                    <p className="lf-step__sub">{s.sub}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {/* The map */}
      <div className="lf-map" style={box(P.map)}>
        <div className="lf-map__world" style={{ transform: `translate(${tx}px, ${ty}px) scale(${zoom})` }}>
          <svg viewBox={`0 0 ${P.map.w} ${P.map.h}`} width={P.map.w} height={P.map.h} aria-hidden="true">
            <defs>
              <pattern id="lf-grid" width="36" height="36" patternUnits="userSpaceOnUse">
                <circle cx="2" cy="2" r="1.2" fill="rgb(10 50 44 / 0.16)" />
              </pattern>
            </defs>
            <rect width={P.map.w} height={P.map.h} fill="url(#lf-grid)" opacity={rise(t, 18.5, 19.2)} />
            <path d={ROUTE} fill="none" stroke="var(--line-strong)" strokeWidth={2} strokeDasharray="2 9" strokeLinecap="round" opacity={route} />
            <Draw d={ROUTE} p={route * (1 - focus) + travel * focus} width={lerp(3, 4, focus)} />
          </svg>

          {PLACES.map((p) => {
            const e = rise(t, p.at, p.at + 0.6)
            if (e <= 0.001) return null
            const onRoutePlace = p === FROM_PLACE || p === TO_PLACE
            const dim = onRoutePlace ? 1 : lerp(1, 0.12, focus)
            return (
              <div key={p.city} className="lf-place" style={{ left: p.x - BUBBLE / 2, top: p.y - BUBBLE / 2, opacity: e * dim, transform: `scale(${(0.8 + 0.2 * e) / zoom ** 0.35})` }}>
                {p.members.map((m) => {
                  const me = rise(t, m.kind === 'customer' ? 20.5 : p.at, (m.kind === 'customer' ? 20.5 : p.at) + 0.5)
                  const lit = m.id === D.delivery.from ? rise(t, 21.5, 22.1) : m.kind === 'customer' ? Math.max(rise(t, 21.9, 22.4) * 0.6, arrived) : 0
                  const Icon = ICON[m.kind]
                  return (
                    <span key={m.id} className="lf-marker" style={{ opacity: me }}>
                      <Bubble icon={Icon} size={BUBBLE} on={m.kind === 'customer' || lit > 0.5} style={{ boxShadow: lit > 0.01 ? `0 0 0 ${7 * lit}px rgb(0 191 165 / ${0.18 * lit})` : undefined }} />
                      {m.available !== undefined ? <b>{m.available}</b> : null}
                    </span>
                  )
                })}
                <span className="lf-place__label">{p.city}</span>
              </div>
            )
          })}

          {travel > 0.001 && travel < 0.999 ? (
            <div className="lf-pkg" style={{ left: pkg.x, top: pkg.y, transform: `translate(-50%, -50%) scale(${1 / zoom ** 0.5})` }}>
              <Package size={24} strokeWidth={1.7} aria-hidden="true" />
            </div>
          ) : null}

          {arrived > 0.01 ? (
            <p className="lf-eta" style={{ left: TO.x, top: TO.y + 34, opacity: arrived, transform: `translate(-50%, ${(1 - arrived) * 8}px) scale(${1 / zoom})` }}>
              <Check size={18} strokeWidth={2.6} aria-hidden="true" />
              {arrival(D.delivery.express.days)}
            </p>
          ) : null}
        </div>

        {t > 21.9 && t < 26.0 ? (
          <p className="lf-dist" style={{ opacity: rise(t, 22.1, 22.6) * fall(t, 25.6, 25.95), left: MID.x - 160, top: MID.y - 20 }}>
            {D.delivery.km} km
          </p>
        ) : null}
        <p className="lf-map__note" style={{ opacity: rise(t, 19.0, 19.6) * (1 - focus) }}>
          Schematic · approximate city centres · demo data
        </p>
      </div>
    </div>
  )
}
