import { ArrowLeft, BadgeCheck, CalendarClock, Check, ChevronRight, CircleAlert, Copy, Factory, Mail, RotateCcw, ScanSearch, ShieldCheck, ShoppingCart, Truck, Warehouse, Weight } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AvailabilityBadge } from '../components/store/Badges'
import { PartCard } from '../components/store/PartCard'
import { PartVisual } from '../components/store/PartVisual'
import { QtyStepper } from '../components/store/QtyStepper'
import { company } from '../data/content'
import { machines } from '../data/machines'
import {
  bandLabel,
  cheapestStandard,
  eur,
  partById,
  partBySlug,
  ratesByBand,
  statusMeta,
  stockLine,
  storeCompliance,
  storeCountries,
  storeShippingRates,
  storeWarehouses,
  STORE_DISCLAIMER,
  STORE_ROUTE,
  totalStock,
  type StorePart,
} from '../data/store'
import { usePageMeta } from '../hooks/usePageMeta'
import { useCart } from '../store/CartContext'

type Tab = 'specs' | 'fit' | 'stock' | 'compliance'
const TABS: readonly { id: Tab; label: string }[] = [
  { id: 'specs', label: 'Specifications' },
  { id: 'fit', label: 'Fits machines' },
  { id: 'stock', label: 'Stock & delivery' },
  { id: 'compliance', label: 'Compliance' },
]

const CERT_LABEL: Record<string, string> = { VALID_DEMO: 'Valid', RENEWAL_PENDING_DEMO: 'Renewal pending' }
const NL_VAT = storeCountries.find((c) => c.code === 'NL')?.vat ?? 0.21
const expressFrom = Math.min(...storeShippingRates.filter((r) => r.method === 'EXPRESS').map((r) => r.price))

export default function PartDetailPage() {
  const { partNo = '' } = useParams()
  const part = partBySlug(partNo)
  return part ? <PartDetail key={part.id} part={part} /> : <MissingPart partNo={partNo} />
}

function MissingPart({ partNo }: { partNo: string }) {
  usePageMeta({ title: 'Part not found', description: 'This part is not in the Noordveld Parts Store.', path: `${STORE_ROUTE}/${partNo}` })
  return (
    <section className="pd-missing container">
      <h1 className="h2">We can’t find that part</h1>
      <p className="lead">No part with the number “{partNo}” is in the catalogue.</p>
      <Link to={STORE_ROUTE} className="button button--primary">
        Browse all parts
      </Link>
    </section>
  )
}

function PartDetail({ part }: { part: StorePart }) {
  usePageMeta({
    title: `${part.name} (${part.no})`,
    description: `${part.name}, part ${part.no}. ${part.category}${part.fits.length ? `, fits ${part.fits.join(', ')}` : ''}. ${eur(part.price)} excluding VAT. Demonstration store.`,
    path: `${STORE_ROUTE}/${part.slug}`,
  })

  const { add, setOpen, justAdded, items } = useCart()
  const [qty, setQty] = useState(1)
  const [tab, setTab] = useState<Tab>('specs')
  const [copied, setCopied] = useState(false)
  const inCart = items.find((i) => i.part.id === part.id)?.qty ?? 0
  const added = justAdded === part.id

  const copy = () => {
    void navigator.clipboard?.writeText(part.no).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    })
  }

  const together = part.related.filter((r) => r.kind === 'together').flatMap((r) => partById(r.id) ?? [])
  const family = part.related.filter((r) => r.kind === 'family').flatMap((r) => partById(r.id) ?? [])

  const onTabKey = (e: KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length]
    setTab(next.id)
    document.getElementById(`tab-${next.id}`)?.focus()
  }

  const notice =
    part.status !== 'VERIFIED' || !part.orderable
      ? {
          title: part.orderable ? statusMeta[part.status].label : 'Not orderable online yet',
          text: part.statusReason || 'Please confirm this part with the Noordveld parts team before ordering.',
        }
      : null

  return (
    <>
      <section className="pd container" aria-labelledby="pd-title">
        <nav className="pd__crumbs" aria-label="Breadcrumb">
          <Link to={STORE_ROUTE}>
            <ArrowLeft size={15} strokeWidth={2} aria-hidden="true" />
            Parts Store
          </Link>
          <ChevronRight size={14} aria-hidden="true" />
          <Link to={`${STORE_ROUTE}?cat=${encodeURIComponent(part.category)}`}>{part.category}</Link>
          {part.subcategory ? (
            <>
              <ChevronRight size={14} aria-hidden="true" />
              <span>{part.subcategory}</span>
            </>
          ) : null}
        </nav>

        <div className="pd__grid">
          <div className="pd__media">
            <PartVisual part={part} variant="large" />
            <dl className="pd__facts">
              <div>
                <Weight size={19} strokeWidth={1.4} aria-hidden="true" />
                <dt>Weight</dt>
                <dd>{part.weightKg} kg</dd>
              </div>
              <div>
                <ShieldCheck size={19} strokeWidth={1.4} aria-hidden="true" />
                <dt>Warranty</dt>
                <dd>{part.warrantyMonths} months</dd>
              </div>
              <div>
                <RotateCcw size={19} strokeWidth={1.4} aria-hidden="true" />
                <dt>Returns</dt>
                <dd>{part.returnDays} days</dd>
              </div>
              <div>
                <Factory size={19} strokeWidth={1.4} aria-hidden="true" />
                <dt>Made at</dt>
                <dd>{part.plant || 'Noordveld plant'}</dd>
              </div>
            </dl>
          </div>

          <div className="pd__buy">
            <p className="label">{part.category}</p>
            <h1 id="pd-title" className="pd__title">
              {part.name}
            </h1>
            <div className="pd__ids">
              <button type="button" className="pd__no" onClick={copy} aria-label={`Copy part number ${part.no}`}>
                <span className="mono">{part.no}</span>
                {copied ? <Check size={15} strokeWidth={2.2} aria-hidden="true" /> : <Copy size={15} strokeWidth={1.6} aria-hidden="true" />}
              </button>
              {part.legacyNo ? (
                <span className="pd__legacy">
                  Previously <span className="mono">{part.legacyNo}</span>
                  {part.legacyBusiness && part.legacyBusiness !== 'Noordveld' ? ` (${part.legacyBusiness})` : ''}
                </span>
              ) : null}
            </div>
            <p className="pd__desc">{part.desc}</p>

            <div className="pd__price">
              <strong>{eur(part.price)}</strong>
              <span>excl. VAT</span>
              <small>{eur(part.price * (1 + NL_VAT))} incl. {Math.round(NL_VAT * 100)}% VAT (NL)</small>
            </div>

            <div className="pd__stock">
              <AvailabilityBadge part={part} />
              <span>{stockLine(part)}</span>
            </div>

            {notice ? (
              <div className="pd__notice" role="note">
                <CircleAlert size={20} strokeWidth={1.6} aria-hidden="true" />
                <div>
                  <h2>{notice.title}</h2>
                  <p>{notice.text}</p>
                  {part.ident.map((r) => (
                    <p key={r.model} className="pd__ident">
                      <ScanSearch size={15} strokeWidth={1.7} aria-hidden="true" /> <strong>{r.model}</strong>: check your machine’s serial number.{' '}
                      {r.variants.map((v) => `${v.name} (${v.from} to ${v.to})`).join(' or ')}.
                    </p>
                  ))}
                </div>
              </div>
            ) : null}

            {part.orderable ? (
              <div className="pd__order">
                <QtyStepper value={qty} onChange={setQty} label="Quantity" />
                <button type="button" className={`button button--primary pd__add ${added ? 'is-added' : ''}`} onClick={() => add(part, qty)}>
                  {added ? <Check size={20} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={20} strokeWidth={1.8} aria-hidden="true" />}
                  {added ? 'Added to cart' : part.availability === 'BACKORDER' ? 'Order on backorder' : 'Add to cart'}
                </button>
              </div>
            ) : (
              <a className="button button--primary pd__confirm" href={`mailto:${company.serviceEmail}?subject=${encodeURIComponent(`Parts enquiry ${part.no}`)}`}>
                <Mail size={20} strokeWidth={1.8} aria-hidden="true" />
                Ask the parts team to confirm
              </a>
            )}
            {inCart > 0 ? (
              <button type="button" className="pd__incart" onClick={() => setOpen(true)}>
                {inCart} in your cart · View cart
              </button>
            ) : null}

            <ul className="pd__promises">
              <li>
                <Truck size={18} strokeWidth={1.5} aria-hidden="true" />
                Standard delivery from {eur(cheapestStandard)}, express from {eur(expressFrom)}
              </li>
              <li>
                <Warehouse size={18} strokeWidth={1.5} aria-hidden="true" />
                {part.dealers > 0 ? `${part.dealers} dealers also hold stock` : 'Ships from Noordveld warehouses'}
              </li>
              <li>
                <BadgeCheck size={18} strokeWidth={1.5} aria-hidden="true" />
                {part.fits.length ? `Fits ${part.fits.join(', ')}` : 'Fitment on request'}
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="pdt container" aria-label="Part information">
        <div className="pdt__tabs" role="tablist" aria-label="Part information">
          {TABS.map((t, i) => (
            <button key={t.id} id={`tab-${t.id}`} type="button" role="tab" aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} tabIndex={tab === t.id ? 0 : -1} onClick={() => setTab(t.id)} onKeyDown={(e) => onTabKey(e, i)}>
              {t.label}
            </button>
          ))}
        </div>

        <div id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="pdt__panel" key={tab}>
          {tab === 'specs' ? <SpecsPanel part={part} /> : null}
          {tab === 'fit' ? <FitPanel part={part} /> : null}
          {tab === 'stock' ? <StockPanel part={part} /> : null}
          {tab === 'compliance' ? <CompliancePanel part={part} /> : null}
        </div>
      </section>

      {together.length > 0 ? (
        <section className="prel container" aria-labelledby="together-title">
          <div className="prel__head">
            <h2 id="together-title" className="h3">
              Often ordered together
            </h2>
            <p>A demo purchase signal. These are suggestions, not substitutes.</p>
          </div>
          <ul className="prel__grid">
            {together.slice(0, 4).map((p) => (
              <li key={p.id}>
                <PartCard part={p} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {family.length > 0 ? (
        <section className="prel container" aria-labelledby="family-title">
          <div className="prel__head">
            <h2 id="family-title" className="h3">
              More in {part.subcategory || part.category}
            </h2>
            <p>Parts that share a name group. Check the specifications before choosing.</p>
          </div>
          <ul className="prel__grid">
            {family.slice(0, 4).map((p) => (
              <li key={p.id}>
                <PartCard part={p} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="pd__note container">{STORE_DISCLAIMER}</p>
    </>
  )
}

function SpecsPanel({ part }: { part: StorePart }) {
  const groups = Array.from(new Set(part.specs.map((s) => s.group)))
  const details: [string, string][] = [
    ['Part number', part.no],
    ['Previous number', part.legacyNo ? `${part.legacyNo}${part.legacyBusiness && part.legacyBusiness !== 'Noordveld' ? ` (${part.legacyBusiness})` : ''}` : ''],
    ['Type', part.type],
    ['Category', part.category],
    ['Subcategory', part.subcategory],
    ['Brand', part.brand],
    ['Made at', part.plant],
  ]
  return (
    <div className="pdt__cols">
      <section>
        <h3>Part details</h3>
        <dl className="spec">
          {details
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
      </section>
      <section>
        <h3>Specifications</h3>
        {groups.length ? (
          groups.map((g) => (
            <dl key={g} className="spec">
              <p className="spec__group">{g}</p>
              {part.specs
                .filter((s) => s.group === g)
                .map((s) => (
                  <div key={`${s.name}-${s.value}`}>
                    <dt>{s.name}</dt>
                    <dd>
                      {s.value}
                      {s.unit ? ` ${s.unit}` : ''}
                    </dd>
                  </div>
                ))}
            </dl>
          ))
        ) : (
          <p className="pdt__muted">No measured values are listed for this part.</p>
        )}
        {part.specNote ? (
          <p className="spec__note">
            <span>Catalogue note</span>
            {part.specNote}
          </p>
        ) : null}
      </section>
    </div>
  )
}

function FitPanel({ part }: { part: StorePart }) {
  if (!part.fits.length) return <p className="pdt__muted">The catalogue does not state which machines this part fits.</p>
  return (
    <div>
      <p className="pdt__lead">Fitment is stated in the Noordveld catalogue. Nothing is inferred from names or categories.</p>
      <ul className="fit">
        {part.fits.map((model) => {
          const m = machines.find((x) => x.model === model)
          const ident = part.ident.find((r) => r.model === model)
          return (
            <li key={model}>
              <div>
                <p className="fit__model mono">{model}</p>
                <p className="fit__name">{m ? m.name : 'Machine'}</p>
                {m ? <p className="fit__meta">Built at {m.plant}</p> : null}
                {ident ? <p className="fit__ident">Check serial range before ordering</p> : null}
              </div>
              {m ? (
                <Link to={`/machines/${m.slug}`} className="text-link">
                  View machine
                </Link>
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function StockPanel({ part }: { part: StorePart }) {
  const max = Math.max(1, ...Object.values(part.stock))
  return (
    <div className="pdt__cols">
      <section>
        <h3>Stock by warehouse</h3>
        <ul className="wh">
          {storeWarehouses.map((w) => {
            const n = part.stock[w.id] ?? 0
            return (
              <li key={w.id}>
                <div className="wh__row">
                  <span className="wh__name">
                    {w.name}
                    <small>
                      {w.city}, {w.country}
                    </small>
                  </span>
                  <strong className={n === 0 ? 'is-zero' : undefined}>{n === 0 ? 'None' : `${n} available`}</strong>
                </div>
                <div className="wh__bar" aria-hidden="true">
                  <span style={{ width: `${(n / max) * 100}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
        <p className="pdt__muted">
          {totalStock(part)} units in total. {part.dealers > 0 ? `${part.dealers} dealers in the network also hold this part.` : 'No dealer stock is listed.'}
        </p>
        {part.backorder ? (
          <p className="wh__backorder">
            <CalendarClock size={18} strokeWidth={1.5} aria-hidden="true" />
            {part.backorder.qty} units are on order from the supplier, with restock expected in about {part.backorder.days} days.
          </p>
        ) : null}
      </section>
      <section>
        <h3>Delivery rates</h3>
        <table className="rates">
          <thead>
            <tr>
              <th scope="col">Distance</th>
              <th scope="col">Standard</th>
              <th scope="col">Express</th>
            </tr>
          </thead>
          <tbody>
            {ratesByBand.map((r) => (
              <tr key={r.band}>
                <th scope="row">{bandLabel[r.band]}</th>
                <td>
                  {eur(r.standard?.price ?? 0)}
                  <small>{r.standard?.days} {r.standard?.days === 1 ? 'day' : 'days'}</small>
                </td>
                <td>
                  {eur(r.express?.price ?? 0)}
                  <small>{r.express?.days} {r.express?.days === 1 ? 'day' : 'days'}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="pdt__muted">Demo rates per shipment, excluding VAT, by road distance from the dispatching warehouse. Transit days exclude one handling day.</p>
      </section>
    </div>
  )
}

function CompliancePanel({ part }: { part: StorePart }) {
  const records = part.compliance.flatMap((id) => (storeCompliance[id] ? [{ id, ...storeCompliance[id] }] : []))
  if (!records.length) return <p className="pdt__muted">No compliance record is listed for this part.</p>
  return (
    <ul className="comp">
      {records.map((c) => (
        <li key={c.id}>
          <div className="comp__top">
            <h3>{c.requirement}</h3>
            <span className={`comp__status ${c.status === 'VALID_DEMO' ? 'is-ok' : 'is-warn'}`}>{CERT_LABEL[c.status] ?? c.status}</span>
          </div>
          <dl>
            <div>
              <dt>Standard</dt>
              <dd>{c.standard}</dd>
            </div>
            <div>
              <dt>Document</dt>
              <dd>{c.certification}</dd>
            </div>
            <div>
              <dt>Valid until</dt>
              <dd>{c.validUntil}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  )
}
