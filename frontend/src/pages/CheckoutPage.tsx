import { ShoppingBag } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, isAbort, lineKey, quoteCart } from '../api'
import {
  getCountries, getDealers, getDestinations, placeOrder, reviewCheckout,
  type CheckoutReview, type DealerRow, type DepotPlan, type Destination, type TransportOption,
} from '../api/orders'
import { CartContents } from '../components/store/CartContents'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { CHECKOUT_ROUTE, STORE_ROUTE } from '../lib/storeQuery'
import { useCart } from '../store/CartContext'
import { useSession } from '../store/session'
import '../components/store/checkout.css'

const STEPS = ['Cart', 'Customer details', 'Cart review', 'Delivery & dealer', 'Availability & fulfilment', 'Review & place order'] as const

const EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/
const PHONE = /^\+?[0-9][0-9 ()\-./]{5,29}$/
const DETAILS_KEY = 'noordveld-checkout-details'
const IDEM_KEY = 'noordveld-checkout-key'

const STATE_LABEL: Record<string, string> = { IN_STOCK: 'In stock', LOW_STOCK: 'Low stock', ON_ORDER: 'On order', OUT_OF_STOCK: 'Out of stock', UNKNOWN: 'Unknown' }
const days = (n: number | null) => (n == null ? 'not recorded' : `${n} ${n === 1 ? 'day' : 'days'}`)
const km = (n: number | null) => (n == null ? 'not recorded' : `${n.toLocaleString('en-NL', { maximumFractionDigits: 1 })} km`)
const modeLabel = (m: string | null) => (m ? m.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Not recorded')

interface Details {
  name: string
  email: string
  phone: string
  company: string
}

const readDraft = (): Partial<Details> => {
  try {
    return JSON.parse(sessionStorage.getItem(DETAILS_KEY) ?? '{}') as Partial<Details>
  } catch {
    return {}
  }
}

/** One key per checkout: a double click or a network retry places the order once. A new key starts after an order is placed. */
const checkoutKey = (): string => {
  try {
    const existing = sessionStorage.getItem(IDEM_KEY)
    if (existing) return existing
    const fresh = `co-${crypto.randomUUID()}`
    sessionStorage.setItem(IDEM_KEY, fresh)
    return fresh
  } catch {
    return `co-${Math.random().toString(36).slice(2)}-${Date.now()}`
  }
}

/**
 * Parts Store checkout: Cart → Customer details → Cart review → Delivery & dealer → Availability & fulfilment → Review & place order.
 * The browser only collects choices. Availability, depots, transport options and every rule come from the API (and Neo4j); the server re-checks all
 * of it when the order is placed. Customer details belong to the order: no customer record is created.
 */
export default function CheckoutPage() {
  usePageMeta({ title: 'Checkout', description: 'Check out your cart: customer details, delivery, dealer, availability and fulfilment, then place the order.', path: CHECKOUT_ROUTE })
  const { lines } = useCart()
  const { user, ready } = useSession()

  if (!ready) return <div className="wf-container co" />
  if (lines.length === 0)
    return (
      <div className="wf-container co">
        <h1>Checkout</h1>
        <div className="scat__empty">
          <ShoppingBag size={44} strokeWidth={1.1} aria-hidden="true" />
          <h3>Your cart is empty</h3>
          <Link to={STORE_ROUTE} className="btn btn-primary">
            Browse parts
          </Link>
        </div>
      </div>
    )
  return (
    <div className="wf-container co">
      <h1>Checkout</h1>
      {user?.role === 'END_USER' ? (
        <Flow />
      ) : user?.role === 'ORDER_PROCESSOR' ? (
        <p className="muted">Order Processors run the order queue; they do not place orders.</p>
      ) : (
        <div className="card card-pad">
          <CartContents />
          <p className="small muted">
            <Link className="link-more" to={`/sign-in?next=${encodeURIComponent(CHECKOUT_ROUTE)}`}>
              Sign in as an End User
            </Link>{' '}
            to check out.
          </p>
        </div>
      )}
    </div>
  )
}

function Flow() {
  const { lines, clear } = useCart()
  const { user } = useSession()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [details, setDetails] = useState<Details>(() => {
    const d = readDraft()
    // the signed-in account only offers defaults; whatever is entered here is what the order keeps
    return { name: d.name ?? user?.name.replace(/ \(demo\)$/, '') ?? '', email: d.email ?? user?.email ?? '', phone: d.phone ?? '', company: d.company ?? user?.customer ?? '' }
  })
  const [country, setCountry] = useState('')
  const [shipToId, setShipToId] = useState('')
  const [receiverName, setReceiverName] = useState('')
  const [receiverPhone, setReceiverPhone] = useState('')
  const [dealerId, setDealerId] = useState('')
  const [allDealers, setAllDealers] = useState(false)
  const [serviceRequired, setServiceRequired] = useState(false)
  const [depotId, setDepotId] = useState('')
  const [routeId, setRouteId] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; reasons: string[] } | null>(null)
  const idem = useRef(checkoutKey())

  const items = useMemo(() => lines.map((l) => ({ part_id: l.partId, quantity: l.qty, machine: l.machine ?? null })), [lines])
  const cartKey = lines.map((l) => `${lineKey(l)}:${l.qty}`).join(',')

  useEffect(() => {
    try {
      sessionStorage.setItem(DETAILS_KEY, JSON.stringify(details))
    } catch {
      /* storage unavailable: the details live for this visit */
    }
  }, [details])

  // reference data, all from the graph
  const countries = useApi((s) => getCountries(s), 'countries')
  const destinations = useApi((s) => (country ? getDestinations(country, s) : Promise.resolve([] as Destination[])), `dest:${country}`)
  const dealers = useApi((s) => getDealers(allDealers ? null : country || null, s), `dealers:${allDealers ? '*' : country}`)
  const quote = useApi((s) => quoteCart(lines, s), `quote:${cartKey}`)

  // availability, depots and transport for the chosen destination. It is read once per destination + cart: moving between steps keeps the choice made.
  const [review, setReview] = useState<CheckoutReview | null>(null)
  const [reviewError, setReviewError] = useState<ApiError | null>(null)
  const reviewFor = useRef('')
  const needsReview = step >= 5 && !!shipToId
  const reviewKey = `${shipToId}|${cartKey}`
  useEffect(() => {
    if (!needsReview || reviewFor.current === reviewKey) return
    const ctrl = new AbortController()
    setReview(null)
    setReviewError(null)
    reviewCheckout(items, shipToId, ctrl.signal).then(
      (r) => {
        reviewFor.current = reviewKey
        setReview(r)
        const rec = r.depots.find((d) => d.recommended)
        setDepotId(rec?.depot_id ?? '')
        setRouteId(rec?.recommended_route_id ?? '')
      },
      (e: unknown) => {
        if (!isAbort(e)) setReviewError(e instanceof ApiError ? e : new ApiError(0, 'unknown', 'Availability could not be checked.'))
      },
    )
    return () => ctrl.abort()
  }, [needsReview, reviewKey, items, shipToId])

  const destination = destinations.data?.find((d) => d.ship_to_id === shipToId) ?? null
  const dealer = dealers.data?.find((d) => d.dealer_id === dealerId) ?? null
  const depot = review?.depots.find((d) => d.depot_id === depotId) ?? null
  const option = depot?.options.find((o) => o.route_id === routeId) ?? null
  const blocked = (quote.data?.rejected.length ?? 0) > 0 || (quote.data?.unknown_part_ids.length ?? 0) > 0

  const detailsOk = details.name.trim().length >= 2 && EMAIL.test(details.email.trim()) && PHONE.test(details.phone.trim()) && details.company.trim().length >= 2
  const deliveryOk = !!destination && receiverName.trim().length >= 2 && PHONE.test(receiverPhone.trim()) && !!dealer
  const fulfilmentOk = !!depot?.selectable && !!option
  const set = (k: keyof Details) => (e: { target: { value: string } }) => setDetails((d) => ({ ...d, [k]: e.target.value }))

  const submit = async () => {
    if (!destination || !dealer || !option) return
    setBusy(true)
    setError(null)
    try {
      const order = await placeOrder({
        items,
        requester: { name: details.name.trim(), email: details.email.trim(), phone: details.phone.trim(), company: details.company.trim() },
        delivery: { ship_to_id: destination.ship_to_id, receiver_name: receiverName.trim(), receiver_phone: receiverPhone.trim() },
        dealer_id: dealer.dealer_id,
        dealer_service_required: serviceRequired,
        depot_id: depotId,
        route_id: routeId,
        confirmed,
        idempotency_key: idem.current,
      })
      try {
        sessionStorage.removeItem(IDEM_KEY)
      } catch {
        /* nothing to remove */
      }
      clear() // the ordered lines left the cart on the server; drop them here too so they cannot be saved back
      navigate(`/orders/${encodeURIComponent(order.order_id)}?placed=1`)
    } catch (e) {
      const reasons = e instanceof ApiError && e.details && typeof e.details === 'object' && 'reasons' in e.details ? ((e.details as { reasons: string[] }).reasons ?? []) : []
      setError({ message: e instanceof ApiError ? e.message : 'The order could not be placed.', reasons })
    } finally {
      setBusy(false)
    }
  }

  const nav = (back: number | null, next: number | null, ok: boolean) => (
    <div className="co__nav">
      {back ? (
        <button type="button" className="btn btn-secondary" onClick={() => setStep(back)}>
          Back
        </button>
      ) : null}
      {next ? (
        <button type="button" className="btn btn-primary" disabled={!ok} onClick={() => setStep(next)}>
          Continue
        </button>
      ) : null}
    </div>
  )

  return (
    <>
      <ol className="co__steps" aria-label="Checkout steps">
        {STEPS.map((label, i) => (
          <li key={label} className={i + 1 === step ? 'is-current' : i + 1 < step ? 'is-done' : ''} aria-current={i + 1 === step ? 'step' : undefined}>
            <span>{i + 1}</span> {label}
          </li>
        ))}
      </ol>

      {step === 1 ? (
        <section className="card card-pad co__panel" aria-labelledby="co-cart">
          <h2 id="co-cart">Cart</h2>
          <CartContents />
          {nav(null, 2, lines.length > 0)}
        </section>
      ) : null}

      {step === 2 ? (
        <section className="card card-pad co__panel" aria-labelledby="co-details">
          <h2 id="co-details">Customer details</h2>
          <p className="small muted">These details are saved with this order only. Your account name and email are offered as defaults; change them if the order is for someone else.</p>
          <div className="co__grid">
            <label>
              Name
              <input value={details.name} onChange={set('name')} autoComplete="name" required />
            </label>
            <label>
              Company
              <input value={details.company} onChange={set('company')} autoComplete="organization" required />
            </label>
            <label>
              Email
              <input type="email" value={details.email} onChange={set('email')} autoComplete="email" required />
              {details.email && !EMAIL.test(details.email.trim()) ? <small className="co__bad">Enter a valid email address.</small> : null}
            </label>
            <label>
              Phone
              <input type="tel" value={details.phone} onChange={set('phone')} autoComplete="tel" placeholder="+31 20 555 0100" required />
              {details.phone && !PHONE.test(details.phone.trim()) ? <small className="co__bad">Enter a valid phone number.</small> : null}
            </label>
          </div>
          {nav(1, 3, detailsOk)}
        </section>
      ) : null}

      {step === 3 ? (
        <section className="card card-pad co__panel" aria-labelledby="co-review-cart">
          <h2 id="co-review-cart">Cart review</h2>
          {!quote.data ? (
            <p className="muted" role="status">
              Checking your parts…
            </p>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Part</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Machine</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => {
                    const ok = quote.data!.lines.find((x) => x.part.part_id === l.partId)
                    const bad = quote.data!.rejected.find((x) => x.part.part_id === l.partId)
                    const part = (ok ?? bad)?.part
                    return (
                      <tr key={lineKey(l)}>
                        <th scope="row">
                          {part ? part.part_number : l.partId}
                          <small>{part?.name}</small>
                        </th>
                        <td>{l.qty}</td>
                        <td>{l.machine ?? 'Not specified'}</td>
                        <td>{ok ? <span className="tag tag-good">Verified, orderable</span> : bad ? <span className="tag tag-warn">{bad.status_label}: cannot be ordered</span> : <span className="tag tag-warn">Not in the catalogue</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="small muted">Part cost is not available: no pricing source is connected. The prices in the cart are synthetic demo list prices, not an order cost.</p>
              {blocked ? <p className="pi-error" role="alert">Remove the parts that cannot be ordered (go back to the cart) to continue. Unverified parts need machine or serial identification first.</p> : null}
            </>
          )}
          {nav(2, 4, !!quote.data && !blocked)}
        </section>
      ) : null}

      {step === 4 ? (
        <section className="card card-pad co__panel" aria-labelledby="co-delivery">
          <h2 id="co-delivery">Delivery &amp; dealer</h2>
          <p className="small muted">The delivery site, the person receiving, the dealer and the depot it ships from are four separate choices.</p>
          <fieldset className="co__fieldset">
            <legend>Delivery site (ship-to)</legend>
            <label>
              Country
              <select value={country} onChange={(e) => { setCountry(e.target.value); setShipToId('') ; setDealerId('') }} aria-label="Delivery country">
                <option value="">Choose a country</option>
                {(countries.data ?? []).map((c) => (
                  <option key={c.country_code} value={c.country_code}>
                    {c.country_code} · {c.destinations} {c.destinations === 1 ? 'site' : 'sites'}
                  </option>
                ))}
              </select>
            </label>
            {country ? (
              destinations.data ? (
                <ul className="co__choices" aria-label="Delivery sites">
                  {destinations.data.map((d) => (
                    <li key={d.ship_to_id}>
                      <label className={shipToId === d.ship_to_id ? 'is-on' : ''}>
                        <input type="radio" name="shipto" checked={shipToId === d.ship_to_id} onChange={() => setShipToId(d.ship_to_id)} />
                        <span>
                          <strong>
                            {d.street}, {d.postal_code} {d.city}
                          </strong>
                          <small>
                            {d.country_code} · site {d.ship_to_id}
                            {d.receiving_hours ? ` · receiving ${d.receiving_hours}` : ''}
                          </small>
                        </span>
                        <span className="badge badge-data">Synthetic demo</span>
                      </label>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted" role="status">Loading delivery sites…</p>
              )
            ) : null}
          </fieldset>
          <fieldset className="co__fieldset">
            <legend>Receiver</legend>
            <div className="co__grid">
              <label>
                Receiver name
                <input value={receiverName} onChange={(e) => setReceiverName(e.target.value)} required />
              </label>
              <label>
                Receiver phone
                <input type="tel" value={receiverPhone} onChange={(e) => setReceiverPhone(e.target.value)} placeholder="+49 40 555 0199" required />
              </label>
            </div>
          </fieldset>
          <fieldset className="co__fieldset">
            <legend>Dealer</legend>
            <label>
              Receiving / service dealer
              <select value={dealerId} onChange={(e) => setDealerId(e.target.value)} aria-label="Dealer">
                <option value="">Choose a dealer</option>
                {(dealers.data ?? []).map((d: DealerRow) => (
                  <option key={d.dealer_id} value={d.dealer_id}>
                    {d.name} · {d.city}, {d.country_code}
                  </option>
                ))}
              </select>
            </label>
            <label className="co__check">
              <input type="checkbox" checked={allDealers} onChange={(e) => setAllDealers(e.target.checked)} /> Show dealers in every country (not only {country || 'the delivery country'})
            </label>
            <label className="co__check">
              <input type="checkbox" checked={serviceRequired} onChange={(e) => setServiceRequired(e.target.checked)} /> The dealer should install the part after delivery
            </label>
          </fieldset>
          {nav(3, 5, deliveryOk)}
        </section>
      ) : null}

      {step === 5 ? (
        <section className="card card-pad co__panel" aria-labelledby="co-avail">
          <h2 id="co-avail">Availability &amp; fulfilment</h2>
          {reviewError ? (
            <p className="pi-error" role="alert">
              {reviewError.message}
            </p>
          ) : !review ? (
            <p className="muted" role="status">
              Checking depot stock and transport routes…
            </p>
          ) : (
            <>
              <p className="small muted">
                Availability is read from the depot inventory. <strong>Unknown</strong> stock is shown as unknown (never as zero) and cannot be used. A depot is offered only if it holds known stock for every line
                and has a recorded route to {review.destination.city}. Stock, routes and estimates are <span className="badge badge-data">synthetic demo data</span>.
              </p>
              <div className="co__depots" role="radiogroup" aria-label="Fulfilment depot">
                {review.depots.map((d: DepotPlan) => (
                  <label key={d.depot_id} className={`co__depot ${depotId === d.depot_id ? 'is-on' : ''} ${d.selectable ? '' : 'is-off'}`}>
                    <input
                      type="radio"
                      name="depot"
                      disabled={!d.selectable}
                      checked={depotId === d.depot_id}
                      onChange={() => {
                        setDepotId(d.depot_id)
                        setRouteId(d.recommended_route_id ?? '')
                      }}
                    />
                    <span>
                      <strong>
                        {d.name} · {d.city}, {d.country_code}
                      </strong>
                      {d.recommended ? <em className="tag tag-good">Recommended</em> : null}
                      <small>
                        {d.lines.map((l) => (
                          <span key={l.part_id} className={`co__stock co__stock--${l.state.toLowerCase()}`}>
                            {l.part_number}: {STATE_LABEL[l.state]}
                            {l.available != null ? ` · ${l.available} available` : ''}
                          </span>
                        ))}
                      </small>
                      {d.selectable ? <small>{d.options.length} transport {d.options.length === 1 ? 'option' : 'options'} to this destination</small> : <small className="co__bad">{d.reasons.join(' ')}</small>}
                    </span>
                  </label>
                ))}
              </div>

              {depot?.selectable ? (
                <fieldset className="co__fieldset">
                  <legend>Fulfilment option: {depot.name} → {review.destination.city}</legend>
                  <ul className="co__choices" aria-label="Transport options">
                    {depot.options.map((o: TransportOption) => (
                      <li key={o.route_id}>
                        <label className={routeId === o.route_id ? 'is-on' : ''}>
                          <input type="radio" name="route" checked={routeId === o.route_id} onChange={() => setRouteId(o.route_id)} />
                          <span>
                            <strong>{o.option_name ?? o.option_code}</strong>
                            <small>
                              {modeLabel(o.mode)} · {o.service_level?.toLowerCase()} · {km(o.distance_km)} · estimated {days(o.estimated_days)} ({o.estimate_basis.toLowerCase()})
                            </small>
                            {o.freight ? <small>Freight context: {o.freight.currency} {o.freight.amount.toFixed(2)} — {o.freight.label}</small> : <small>No freight estimate recorded</small>}
                          </span>
                          <span className="badge badge-data">Synthetic demo</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </fieldset>
              ) : null}
              {!review.can_order ? <p className="pi-error" role="alert">No depot can supply this order to this destination. Change the delivery site or the quantities.</p> : null}
            </>
          )}
          {nav(4, 6, fulfilmentOk)}
        </section>
      ) : null}

      {step === 6 && destination && dealer && depot && option ? (
        <section className="card card-pad co__panel" aria-labelledby="co-place">
          <h2 id="co-place">Review &amp; place order</h2>
          <div className="co__summary">
            <section aria-label="Requester">
              <h3>Requester</h3>
              <dl className="kv-list">
                <div className="kv-row"><dt>Name</dt><dd>{details.name}</dd></div>
                <div className="kv-row"><dt>Email</dt><dd>{details.email}</dd></div>
                <div className="kv-row"><dt>Phone</dt><dd>{details.phone}</dd></div>
                <div className="kv-row"><dt>Company</dt><dd>{details.company}</dd></div>
              </dl>
            </section>
            <section aria-label="Parts">
              <h3>Parts</h3>
              <dl className="kv-list">
                {(review?.lines ?? []).map((l) => (
                  <div className="kv-row" key={`${l.part_id}|${l.machine}`}>
                    <dt>
                      {l.part_number}
                      <small>{l.part_name}</small>
                    </dt>
                    <dd>
                      × {l.quantity}
                      <small>Machine: {l.machine ?? 'not specified'}</small>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
            <section aria-label="Delivery">
              <h3>Delivery</h3>
              <dl className="kv-list">
                <div className="kv-row"><dt>Ship-to</dt><dd>{destination.street}, {destination.postal_code} {destination.city}, {destination.country_code}</dd></div>
                <div className="kv-row"><dt>Receiver</dt><dd>{receiverName} · {receiverPhone}</dd></div>
                <div className="kv-row"><dt>Dealer</dt><dd>{dealer.name} · {dealer.city}, {dealer.country_code}{serviceRequired ? <small>Dealer installation requested</small> : <small>No dealer installation</small>}</dd></div>
              </dl>
            </section>
            <section aria-label="Fulfilment">
              <h3>Fulfilment</h3>
              <dl className="kv-list">
                <div className="kv-row"><dt>Depot</dt><dd>{depot.name} · {depot.city}, {depot.country_code}</dd></div>
                <div className="kv-row"><dt>Availability</dt><dd>{depot.lines.map((l) => `${l.part_number}: ${STATE_LABEL[l.state]}${l.available != null ? ` (${l.available})` : ''}`).join('; ')}<small>Stock is reserved for this order when it is placed (synthetic demo inventory).</small></dd></div>
              </dl>
            </section>
            <section aria-label="Transport">
              <h3>Transport</h3>
              <dl className="kv-list">
                <div className="kv-row"><dt>Option</dt><dd>{option.option_name ?? option.option_code}</dd></div>
                <div className="kv-row"><dt>Mode</dt><dd>{modeLabel(option.mode)} · {option.service_level?.toLowerCase()}</dd></div>
                <div className="kv-row"><dt>Distance</dt><dd>{km(option.distance_km)}</dd></div>
                <div className="kv-row"><dt>Estimated delivery</dt><dd>{days(option.estimated_days)} after dispatch<small>Estimated and synthetic; not a guaranteed date.</small></dd></div>
              </dl>
            </section>
            <section aria-label="Cost">
              <h3>Cost</h3>
              <dl className="kv-list">
                <div className="kv-row"><dt>Part cost</dt><dd>Not available</dd></div>
                <div className="kv-row"><dt>Transportation cost</dt><dd>Not available{option.freight ? <small>Freight context only: {option.freight.currency} {option.freight.amount.toFixed(2)}, {option.freight.label.toLowerCase()}</small> : null}</dd></div>
                <div className="kv-row"><dt>Total</dt><dd>Not available</dd></div>
              </dl>
              <p className="small muted">{review?.cost.note}</p>
            </section>
            <section aria-label="Provenance" className="co__prov">
              <h3>Data status</h3>
              <p className="small">
                Order details: recorded in this app. Stock, transport options, distances, estimates and tracking: <strong>SYNTHETIC DEMO DATA</strong>. Parts and fitment: source-derived catalogue.
              </p>
            </section>
          </div>
          <label className="co__check co__confirm">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I confirm the details above and want to place this order.
          </label>
          {error ? (
            <div className="pi-error" role="alert">
              <p>{error.message}</p>
              {error.reasons.length ? (
                <ul>
                  {error.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          <div className="co__nav">
            <button type="button" className="btn btn-secondary" onClick={() => setStep(5)} disabled={busy}>
              Back
            </button>
            <button type="button" className="btn btn-primary" onClick={submit} disabled={!confirmed || busy}>
              {busy ? 'Placing order…' : 'Place order'}
            </button>
          </div>
        </section>
      ) : null}
    </>
  )
}
