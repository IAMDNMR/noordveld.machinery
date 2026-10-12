import { Boxes, Building2, Cog, PackageCheck, Ship, Store, Tractor, Wrench, type LucideIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { PartSummary } from '../../api'
import { apiGet } from '../../api/client'
import { getCountries, getDealers, getOrders } from '../../api/orders'
import { ButtonLink } from '../../components/ButtonLink'
import { Reveal } from '../../components/Reveal'
import { company } from '../../data/content'
import { useApi } from '../../hooks/useApi'
import { useInView } from '../../hooks/useInView'
import { editorialImageUrl } from '../../lib/assets'
import { STORE_ROUTE } from '../../lib/storeQuery'
import { useSession } from '../../store/session'
import { label, withImage } from './data'

const PI = (q: string) => `/parts-intelligence?${new URLSearchParams({ q })}`
/** A question for the one Agentic E-Commerce screen (parts, delivery, orders, shipments and warranty). */
const ASK = (q: string) => `/agentic-shopping?${new URLSearchParams({ q })}`
const signInTo = (hash: string) => `/sign-in?${new URLSearchParams({ next: `/parts-services${hash}` })}`

/* ───────── Parts Intelligence: the relationships the graph holds ───────── */

interface Kpis { parts: number; machines: number; fitments: number; suppliers: number; dealers: number; relationships: number; nodes: number; synthetic_nodes: number }

export function IntelligenceMap({ parts }: { parts: PartSummary[] | null }) {
  const kpis = useApi((s) => apiGet<Kpis>('/intelligence/kpis', {}, s), 'as-kpis')
  const example = withImage(parts ?? []).find((p) => p.fitment.length > 1) ?? (parts ?? [])[0]
  const no = example?.part_number
  // each node and the relationship that reaches it, with where it can be inspected; order, shipment and service records belong to signed-in users
  const nodes: { name: string; rel: string; icon: LucideIcon; to: string | null; note: string }[] = [
    { name: 'Machine', rel: 'FITS', icon: Tractor, to: no ? PI(`Which machines use ${no}?`) : null, note: 'fitment records' },
    { name: 'Part', rel: '', icon: Cog, to: no ? `/parts-intelligence?${new URLSearchParams({ q: no })}` : null, note: 'catalogue record' },
    { name: 'Supplier', rel: 'SUPPLIED_BY', icon: Building2, to: no ? PI(`Who supplies ${no}?`) : null, note: 'sourcing records' },
    { name: 'Dealer', rel: 'STOCKED_BY', icon: Store, to: no ? PI(`Which dealers stock ${no}?`) : null, note: 'dealer stock records' },
    { name: 'Depot', rel: 'AVAILABLE_AT', icon: Boxes, to: no ? PI(`Which warehouses have ${no}?`) : null, note: 'depot inventory' },
    { name: 'Order', rel: 'REFERENCES_PART', icon: PackageCheck, to: '/orders', note: 'your orders (sign-in)' },
    { name: 'Shipment', rel: 'HAS_SHIPMENT', icon: Ship, to: ASK('Where is my shipment and what parts are in it?'), note: 'shipment tracking (sign-in)' },
    { name: 'Service', rel: 'INSTALLED_PART', icon: Wrench, to: ASK('Is this failed part covered by warranty?'), note: 'installation and warranty records (sign-in)' },
  ]
  const questions = no
    ? [
        { q: `Which machines use ${no}?`, to: PI(`Which machines use ${no}?`) },
        { q: `Who supplies ${no}?`, to: PI(`Who supplies ${no}?`) },
        { q: `Which dealers stock ${no}?`, to: PI(`Which dealers stock ${no}?`) },
        { q: 'What recorded transport routes are available?', to: ASK('How long to ship a part to Lagos?') },
        { q: 'What is the status of an existing order?', to: '/orders' },
        { q: 'What warranty or service information is recorded?', to: ASK('Is this failed part covered by warranty?') },
      ]
    : []
  const ref = useRef<HTMLOListElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.3 })
  const k = kpis.data
  return (
    <section className="section on-dark as-intel" aria-labelledby="as-intel-title">
      <div className="as-intel__grid" aria-hidden="true" />
      <div className="container">
        <Reveal>
          <p className="label">Parts Intelligence</p>
          <h2 id="as-intel-title" className="h1">Make the connections visible.</h2>
          <p className="lead">Every part sits in a graph of recorded relationships. Select a node to inspect it with Parts Intelligence{example ? <>, starting from <span className="as-mono">{no}</span> ({example.name})</> : null}.</p>
        </Reveal>
        <ol ref={ref} className={`as-graph ${inView ? 'is-in' : ''}`} aria-label="Relationships recorded in the graph">
          {nodes.map((n, i) => (
            <li key={n.name} style={{ transitionDelay: `${i * 110}ms` }}>
              {n.rel ? <span className="as-graph__rel">{n.rel}</span> : null}
              {n.to ? (
                <Link to={n.to} className="as-graph__node"><n.icon size={22} strokeWidth={1.6} aria-hidden="true" /><strong>{n.name}</strong><small>{n.note}</small></Link>
              ) : (
                <span className="as-graph__node"><n.icon size={22} strokeWidth={1.6} aria-hidden="true" /><strong>{n.name}</strong><small>{n.note}</small></span>
              )}
            </li>
          ))}
        </ol>
        {k ? (
          <p className="as-intel__kpis">
            {k.parts} parts · {k.machines} machines · {k.fitments} fitment records · {k.suppliers} suppliers · {k.dealers} dealers · {k.relationships.toLocaleString('en-US')} relationships, of which {Math.round((k.synthetic_nodes / k.nodes) * 100)}% of the records are synthetic demonstration data.
          </p>
        ) : null}
        <div className="as-intel__bottom">
          <ul className="as-questions" aria-label="Example questions">
            {questions.map((x) => <li key={x.q}><Link to={x.to}>{x.q}</Link></li>)}
          </ul>
          <div className="as-legend">
            <p>Answers depend on the records that exist. Every answer is labelled:</p>
            <dl>
              <div><dt className="is-source">Source records</dt><dd>from the supplied catalogue (source-derived)</dd></div>
              <div><dt className="is-derived">Derived</dt><dd>computed from those records</dd></div>
              <div><dt className="is-demo">Synthetic demo</dt><dd>demonstration data, never real operations</dd></div>
              <div><dt className="is-unknown">Unknown</dt><dd>not recorded: shown as unknown, never as zero or “no”</dd></div>
            </dl>
            <ButtonLink to="/parts-intelligence">Explore Parts Intelligence</ButtonLink>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ───────── The ordering journey (the existing Parts Store checkout) ───────── */

const STEPS = ['Select part', 'Cart', 'Customer details', 'Delivery location', 'Dealer / receiver', 'Availability', 'Fulfilment', 'Transportation', 'Order confirmation']

export function OrderJourney() {
  const ref = useRef<HTMLOListElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.35 })
  return (
    <section className="section as-journey" aria-labelledby="as-journey-title">
      <div className="container">
        <Reveal>
          <p className="label">Parts Store · from selection to delivery</p>
          <h2 id="as-journey-title" className="h1">One checkout, every step recorded.</h2>
          <p className="lead">This is the Parts Store’s own checkout. Availability, delivery options and transport come from the recorded stock, routes and dealers; where nothing is recorded the checkout says so.</p>
        </Reveal>
        <ol ref={ref} className={`as-steps ${inView ? 'is-in' : ''}`}>
          {STEPS.map((s, i) => (
            <li key={s} style={{ transitionDelay: `${i * 120}ms` }}>
              <span className="as-steps__n">{i + 1}</span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
        <ButtonLink to={STORE_ROUTE}>Open Parts Store</ButtonLink>
      </div>
    </section>
  )
}

/* ───────── Dealer locator (the checkout's dealer records; signed-in only, as the API requires) ───────── */

export function DealerLocator() {
  const { user, ready } = useSession()
  const [country, setCountry] = useState('')
  const countries = useApi((s) => (user ? getCountries(s) : Promise.resolve([])), `as-countries:${user?.id ?? '-'}`)
  const dealers = useApi((s) => (user && country ? getDealers(country, s) : Promise.resolve(null)), `as-dealers:${user?.id ?? '-'}:${country}`)
  return (
    <section id="dealers" className="section on-mist as-dealers" aria-labelledby="as-dealers-title">
      <div className="container as-dealers__layout">
        <div>
          <Reveal>
            <p className="label">Dealer locator</p>
            <h2 id="as-dealers-title" className="h1">A dealer near the machine.</h2>
            <p className="lead">Find dealers in the recorded network by country. A listing shows who the dealer is and where; it does not mean the dealer holds stock, fulfils an order or receives the delivery.</p>
          </Reveal>
          {!ready ? null : user ? (
            <label className="as-select">
              <span>Country</span>
              <select value={country} onChange={(e) => setCountry(e.target.value)}>
                <option value="">{countries.loading ? 'Loading countries…' : 'Choose a country'}</option>
                {(countries.data ?? []).map((c) => <option key={c.country_code} value={c.country_code}>{c.country_code}</option>)}
              </select>
            </label>
          ) : (
            <p className="as-note">Dealer records are available to signed-in users. <Link to={signInTo('#dealers')}>Sign in to search dealers →</Link></p>
          )}
          {countries.error ? <p className="as-note as-note--bad">Countries could not be loaded.</p> : null}
        </div>
        <div className="as-dealers__list" aria-live="polite">
          {dealers.loading && country ? <p className="as-note">Reading the dealer records…</p> : null}
          {dealers.error ? <p className="as-note as-note--bad">Dealers could not be loaded.</p> : null}
          {dealers.data && dealers.data.length === 0 ? <p className="as-note">No dealer is recorded in {country}.</p> : null}
          {dealers.data && dealers.data.length > 0 ? (
            <ul>
              {dealers.data.slice(0, 8).map((d) => (
                <li key={d.dealer_id}>
                  <strong>{d.name}</strong>
                  <span>{[d.city, d.country_code].filter(Boolean).join(', ')}</span>
                  <small>{sentenceOr(d.dealer_type)}{d.data_status === 'SYNTHETIC_DEMO' ? ' · demo record' : ''}</small>
                </li>
              ))}
            </ul>
          ) : null}
          {dealers.data && dealers.data.length > 8 ? <p className="as-note">{dealers.data.length - 8} more dealers in {country} are recorded.</p> : null}
          {!country && user ? <div className="as-dealers__visual"><img src={editorialImageUrl('work-environment')} alt="" loading="lazy" /></div> : null}
          {!user ? <div className="as-dealers__visual"><img src={editorialImageUrl('work-environment')} alt="" loading="lazy" /></div> : null}
        </div>
      </div>
    </section>
  )
}

const sentenceOr = (code: string | null) => (code ? label(code).replace(/^./, (c) => c.toUpperCase()) : 'Dealer type not recorded')

/* ───────── Service & maintenance: what is supported, labelled honestly ───────── */

export function ServiceJourney() {
  const steps: { name: string; state: 'available' | 'partial' | 'unavailable'; text: string; to?: string; cta?: string }[] = [
    { name: 'Identify issue', state: 'available', text: 'Describe the problem in plain words; the agent identifies the machine and the part.', to: '/agentic-shopping', cta: 'Agentic E-Commerce' },
    { name: 'Find part', state: 'available', text: 'Verify the part and its recorded fitment.', to: STORE_ROUTE, cta: 'Parts Store' },
    { name: 'Order', state: 'available', text: 'Check out through the Parts Store (sign-in).', to: `${STORE_ROUTE}/checkout`, cta: 'Checkout' },
    { name: 'Receive', state: 'available', text: 'Follow the recorded order and shipment status.', to: '/orders', cta: 'My Orders' },
    { name: 'Install', state: 'partial', text: 'Installation records exist for demonstration machines and are shown with warranty answers; booking an installation is not available.', to: ASK('Is this failed part covered by warranty?'), cta: 'Agentic E-Commerce' },
    { name: 'Service completion', state: 'unavailable', text: 'Service booking and completion are not connected in this platform.' },
  ]
  const img = editorialImageUrl('service')
  return (
    <section id="service" className="section as-service" aria-labelledby="as-service-title">
      <div className="container as-service__layout">
        <Reveal className="as-service__media">{img ? <img src={img} alt="A service engineer working on a wheel loader" loading="lazy" /> : null}</Reveal>
        <div>
          <Reveal>
            <p className="label">Service &amp; maintenance</p>
            <h2 id="as-service-title" className="h1">Parts keep the machine working.</h2>
            <p className="lead">Maintenance, repair and component replacement all start with the right part. These are the steps the platform supports today, and what it does not.</p>
          </Reveal>
          <ol className="as-svc">
            {steps.map((s, i) => (
              <Reveal as="li" key={s.name} delay={i * 70} className={`as-svc__step is-${s.state}`}>
                <span className="as-svc__n">{i + 1}</span>
                <div>
                  <strong>{s.name}</strong> <em>{s.state === 'available' ? 'Available' : s.state === 'partial' ? 'Partly available' : 'Not available'}</em>
                  <p>{s.text}</p>
                  {s.to ? <Link to={s.to}>{s.cta} →</Link> : null}
                </div>
              </Reveal>
            ))}
          </ol>
          <a className="as-inline-link" href={`mailto:${company.serviceEmail}?subject=Service%20enquiry`}>Contact the service desk</a>
        </div>
      </div>
    </section>
  )
}

/* ───────── Order and delivery tracking ───────── */

const TRACK = ['Order', 'Allocation', 'Fulfilment', 'Shipment', 'Tracking', 'Dealer receipt', 'Service']

export function Tracking() {
  const { user, ready } = useSession()
  const orders = useApi((s) => (user ? getOrders(s) : Promise.resolve(null)), `as-orders:${user?.id ?? '-'}`)
  return (
    <section id="tracking" className="section on-dark as-track" aria-labelledby="as-track-title">
      <div className="container">
        <Reveal>
          <p className="label">Order &amp; delivery tracking</p>
          <h2 id="as-track-title" className="h1">Know where it is.</h2>
          <p className="lead">Every order moves through recorded steps. The status you see is the recorded status; planned routes and ETAs are plans, tracking events in this demo are synthetic, and no live carrier feed is connected.</p>
        </Reveal>
        <ol className="as-track__rail">
          {TRACK.map((s, i) => <Reveal as="li" key={s} delay={i * 80}><i />{s}</Reveal>)}
        </ol>
        <div className="as-track__body" aria-live="polite">
          {!ready ? null : !user ? (
            <p className="as-note as-note--dark">Your orders are visible only to you. <Link to={signInTo('#tracking')}>Sign in to see them →</Link></p>
          ) : orders.loading ? (
            <p className="as-note as-note--dark">Reading your orders…</p>
          ) : orders.error ? (
            <p className="as-note as-note--dark">Your orders could not be loaded.</p>
          ) : orders.data && orders.data.length === 0 ? (
            <p className="as-note as-note--dark">No order is recorded for your account yet.</p>
          ) : (
            <ul className="as-orders">
              {(orders.data ?? []).slice(0, 4).map((o) => (
                <li key={o.order_id}>
                  <Link to={`/orders/${encodeURIComponent(o.order_id)}`}>
                    <span className="as-mono">{o.order_id}</span>
                    <strong>{o.status_label}</strong>
                    <small>{o.order_date ?? 'date not recorded'} · {o.fulfilment}{o.data_status === 'SYNTHETIC_DEMO' ? ' · demo record' : ''}</small>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <ButtonLink to="/orders">Track an Order</ButtonLink>
      </div>
    </section>
  )
}

/* ───────── Trust and transparency ───────── */

export function Trust() {
  return (
    <section className="section as-trust" aria-labelledby="as-trust-title">
      <div className="container as-trust__layout">
        <Reveal>
          <p className="label">Trust &amp; transparency</p>
          <h2 id="as-trust-title" className="h2">What you see is what is recorded.</h2>
          <p className="lead">Parts discovery and service information come from the catalogue, its recorded compatibility relationships and recorded operational data. Synthetic demonstration data is always labelled, and nothing missing is filled in.</p>
        </Reveal>
        <ul className="as-trust__links">
          <li><a href={`mailto:${company.email}`}>Help &amp; contact</a></li>
          <li><a href="#dealers">Dealer locator</a></li>
          <li><Link to={STORE_ROUTE}>Product information</Link></li>
          <li><Link to="/parts-intelligence">How answers are built</Link></li>
          <li><Link to="/privacy">Privacy</Link></li>
          <li><Link to="/legal">Legal</Link></li>
        </ul>
      </div>
    </section>
  )
}
