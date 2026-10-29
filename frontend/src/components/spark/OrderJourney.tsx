import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleCheck,
  Clock,
  Minus,
  Plus,
  Truck,
  Wallet,
} from 'lucide-react'
import type {
  DeliveryDecision,
  FulfilmentOption,
  OrderAsk,
  OrderChoice,
  OrderResponse,
  OrderSlots,
  OrderSummary,
  OrderTurnBody,
} from '../../api/sparkOrder'
import { getProfile, saveProfile, type Profile } from '../../api/profile'
import { PartImage } from '../store/PartImage'
import { AnswerText } from './AnswerText'
import './spark-order.css'

const eur = (value: number | null | undefined) =>
  value === null || value === undefined
    ? 'Not recorded'
    : new Intl.NumberFormat('en', { style: 'currency', currency: 'EUR' }).format(value)
const day = (iso: string | null | undefined) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
      })
    : 'Not recorded'
const service = (o: { service_level?: string | null; mode?: string | null }) =>
  [o.service_level, o.mode]
    .filter(Boolean)
    .map((x) => x!.toLowerCase())
    .join(' ') || 'transport'
const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

const STEP_LABELS: Record<string, string> = {
  part: 'Part',
  quantity: 'Quantity',
  delivery: 'Delivery',
  fulfilment: 'Fulfilment',
  dealer: 'Dealer',
  details: 'Your details',
  review: 'Review',
  placed: 'Place order',
}
export const ACTIVE_ORDER_ID = 'spark-active-order'

/** One change to the order: a slot patch, a reopened step, or the confirmation. The server re-validates every one. */
export type OrderChange = (
  patch: OrderSlots,
  choice?: OrderChoice,
  revisit?: OrderTurnBody['revisit'],
) => void

type Props = {
  order: OrderResponse
  /** Only the open journey's latest step is interactive; earlier steps collapse to one line so nothing repeats. */
  active: boolean
  busy: boolean
  onPatch: OrderChange
}

export function OrderJourney({ order, active, busy, onPatch }: Props) {
  if (order.order) return <Placed order={order} />
  if (!active)
    return (
      <div className="so-record">
        {order.slots.auto === true ? null : (
          <span className="so-record__step">{STEP_LABELS[order.stage] ?? order.stage}</span>
        )}
        <AnswerText text={order.message} parts={order.part ? [order.part.part_number] : []} />
      </div>
    )
  const ask = order.ask
  // the message already says it: a note repeated below it is noise
  const said = (text: string) => order.message.includes(text)
  const warnings = [...new Set(order.warnings)].filter((warning) => !said(warning))
  const reasons = [...new Set(order.reasons)].filter((reason) => !said(reason))
  // Spark is filling the order for the user: the reply says everything; only a missing detail or the final yes needs a control
  const auto = order.slots.auto === true
  const place = order.ask?.choices.find((choice) => choice.confirm)
  return (
    <section className="so so--active" id={ACTIVE_ORDER_ID} aria-label="Your order">
      {auto ? null : <Progress order={order} busy={busy} onPatch={onPatch} />}
      <AnswerText text={order.message} parts={order.part ? [order.part.part_number] : []} />
      {order.prefilled.length ? (
        <p className="so-note">
          Filled from your saved profile: {order.prefilled.join(', ')}.{' '}
          <Link to="/profile">Manage profile</Link>
        </p>
      ) : null}
      {warnings.length ? (
        <ul className="so-warnings" aria-label="Notes">
          {warnings.map((warning) => (
            <li key={warning}>
              <AlertTriangle size={14} aria-hidden="true" /> {warning}
            </li>
          ))}
        </ul>
      ) : null}
      {order.part && !auto ? <OrderConfig order={order} busy={busy} onPatch={onPatch} /> : null}
      {reasons.length ? (
        // the record-level reasons behind the sentence above, one click away
        <details className="so-why">
          <summary>Why ({reasons.length})</summary>
          <ul className="so-reasons">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {order.options && order.decision ? (
        <DeliveryComparison
          options={order.options}
          decision={order.decision}
          hidden={order.hidden_options}
          busy={busy}
          onPatch={onPatch}
        />
      ) : null}
      {auto && order.stage === 'review' && order.summary && place ? (
        <AutoReview
          order={order}
          summary={order.summary}
          place={place}
          busy={busy}
          onPatch={onPatch}
        />
      ) : order.stage === 'review' && order.summary ? (
        <Review order={order} summary={order.summary} busy={busy} onPatch={onPatch} />
      ) : ask && !order.options && ask.kind !== 'number' && ask.kind !== 'confirm' ? (
        <AskView
          key={ask.question}
          ask={ask}
          busy={busy}
          onPatch={onPatch}
          said={said(ask.question)}
        />
      ) : null}
      {order.alternatives.length ? (
        <section aria-label="Related parts" className="so-panel">
          <h3 className="so-h">Related parts</h3>
          <ul className="so-related">
            {order.alternatives.map((alt) => (
              <li key={alt.part_id}>
                <Link to={`/spark/chat?order=${encodeURIComponent(alt.part_id)}`}>
                  {alt.part_number} · {alt.name}
                </Link>
                <small>{alt.note}</small>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  )
}

/** The eight steps. A completed step can be reopened; reopening keeps every other choice. */
function Progress({ order, busy, onPatch }: Omit<Props, 'active'>) {
  const reopen: Record<string, (() => void) | undefined> = {
    quantity: () => document.getElementById('so-qty')?.focus(),
    delivery: () =>
      onPatch({ ship_to_id: null, route_id: null }, {
        label: 'Change delivery site',
      } as OrderChoice),
    fulfilment: () => onPatch({}, { label: 'Change delivery option' } as OrderChoice, 'fulfilment'),
    dealer: () => onPatch({ dealer_id: null }, { label: 'Change dealer' } as OrderChoice),
    details: () => onPatch({}, { label: 'Edit my details' } as OrderChoice, 'details'),
  }
  return (
    <ol className="so-progress" aria-label="Order progress">
      {order.stages.map((stage, n) => {
        const open = stage.state === 'done' ? reopen[stage.id] : undefined
        const label = STEP_LABELS[stage.id] ?? stage.label
        return (
          <li
            key={stage.id}
            data-state={stage.state}
            aria-current={stage.state === 'current' ? 'step' : undefined}
          >
            {open ? (
              <button
                type="button"
                disabled={busy}
                onClick={open}
                aria-label={`Change ${label.toLowerCase()}`}
              >
                <Check size={12} aria-hidden="true" />
                {label}
              </button>
            ) : (
              <span>
                {stage.state === 'done' ? <Check size={12} aria-hidden="true" /> : <i>{n + 1}</i>}
                {label}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

/** The part being ordered and the choices that shape its price: one card, kept up to date, never repeated. */
function OrderConfig({ order, busy, onPatch }: Omit<Props, 'active'>) {
  const part = order.part!
  const s = order.slots
  const current = typeof s.quantity === 'number' ? s.quantity : null
  const [qty, setQty] = useState(current ?? 1)
  const valid = Number.isInteger(qty) && qty >= 1 && qty <= 99
  const asking = order.stage === 'quantity' && order.ask?.kind === 'number'
  const changed = current !== null && qty !== current
  const unit = part.price?.amount ?? null
  const stock = part.depot_stock_total
  const machine = typeof s.machine === 'string' ? s.machine : null
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (valid) onPatch({ quantity: qty }, { label: `Quantity ${qty}` } as OrderChoice)
  }
  return (
    <section className="so-config" aria-label="Selected part">
      <PartImage
        partNumber={part.part_number}
        category={part.category}
        name={part.name}
        variant="mini"
      />
      <div className="so-config__main">
        <p className="so-config__no">{part.part_number}</p>
        <h3 className="so-config__name">{part.name}</h3>
        <ul className="so-chips">
          {machine ? (
            <li className="is-good">Fits {machine}</li>
          ) : part.fits.length ? (
            <li>Fits {part.fits.length} machine model(s)</li>
          ) : (
            <li className="is-warn">Fitment not recorded</li>
          )}
          {part.part_status === 'VERIFIED' ? <li className="is-good">Verified</li> : null}
          {stock !== null ? (
            <li className={current && stock < current ? 'is-warn' : ''}>{stock} in depot stock</li>
          ) : (
            <li className="is-warn">Stock not recorded</li>
          )}
          {typeof s.needed_by === 'string' ? (
            <li>
              <Clock size={12} aria-hidden="true" /> Needed by {day(s.needed_by)}
            </li>
          ) : null}
          {typeof s.budget_eur === 'number' ? (
            <li>
              <Wallet size={12} aria-hidden="true" /> Budget {eur(s.budget_eur)}
            </li>
          ) : null}
        </ul>
        {part.supplier ? (
          <p className="so-config__meta">
            Supplier {part.supplier.name}
            {part.supplier.lead_time_days !== null
              ? ` · restock lead time ${part.supplier.lead_time_days} days`
              : ''}
          </p>
        ) : null}
      </div>
      <form className="so-config__buy" onSubmit={submit}>
        <p className="so-price">
          {unit !== null ? eur(unit) : 'Price not recorded'}
          <small>{unit !== null ? 'per unit, excl. VAT' : 'No total can be shown'}</small>
        </p>
        <div className="so-stepper" role="group" aria-label="Quantity">
          <button
            type="button"
            aria-label="One fewer"
            disabled={busy || qty <= 1}
            onClick={() => setQty((q) => Math.max(1, q - 1))}
          >
            <Minus size={15} aria-hidden="true" />
          </button>
          <input
            id="so-qty"
            type="number"
            inputMode="numeric"
            min={1}
            max={99}
            value={Number.isNaN(qty) ? '' : qty}
            aria-label="Quantity"
            aria-invalid={!valid}
            onChange={(event) => setQty(Number.parseInt(event.target.value, 10))}
          />
          <button
            type="button"
            aria-label="One more"
            disabled={busy || qty >= 99}
            onClick={() => setQty((q) => Math.min(99, q + 1))}
          >
            <Plus size={15} aria-hidden="true" />
          </button>
        </div>
        {!valid ? <small className="so-error">Enter a quantity from 1 to 99.</small> : null}
        {unit !== null && valid ? (
          <p className="so-subtotal">
            Subtotal <strong>{eur(Math.round(unit * qty * 100) / 100)}</strong>
          </p>
        ) : null}
        {asking ? (
          <button type="submit" className="so-btn so-btn--primary" disabled={busy || !valid}>
            Continue to delivery <ArrowRight size={15} aria-hidden="true" />
          </button>
        ) : changed ? (
          <button type="submit" className="so-btn" disabled={busy || !valid}>
            Update quantity
          </button>
        ) : null}
      </form>
    </section>
  )
}

/** Delivery options compared against the user's own limits: what meets them, what is closest if nothing does, and what each trade-off costs. */
function DeliveryComparison({
  options,
  decision,
  hidden,
  busy,
  onPatch,
}: {
  options: FulfilmentOption[]
  decision: DeliveryDecision
  hidden: number
  busy: boolean
  onPatch: OrderChange
}) {
  const select = (o: FulfilmentOption) =>
    onPatch({ route_id: o.route_id }, {
      label: `${cap(service(o))} from ${o.depot}`,
    } as OrderChoice)
  return (
    <section className="so-panel so-delivery" aria-label="Delivery options">
      <div className={`so-verdict so-verdict--${decision.status}`}>
        {decision.status === 'none' ? (
          <AlertTriangle size={17} aria-hidden="true" />
        ) : (
          <Truck size={17} aria-hidden="true" />
        )}
        <p>{decision.headline}</p>
      </div>
      {decision.alternatives.length ? (
        <div className="so-tradeoffs">
          {decision.alternatives.map((alt) => (
            <div key={alt.title} className="so-tradeoff">
              <p className="so-h">{alt.title}</p>
              <p className="so-tradeoff__what">{cap(alt.label)}</p>
              <p className="so-tradeoff__facts">
                Arrives {alt.arrives} · {eur(alt.total)}
              </p>
              <p className="so-tradeoff__gap">{alt.gap}</p>
              <button
                type="button"
                className="so-btn"
                disabled={busy}
                onClick={() =>
                  onPatch(alt.patch, { label: `${alt.title}: ${alt.label}` } as OrderChoice)
                }
              >
                Select this delivery
              </button>
            </div>
          ))}
        </div>
      ) : null}
      <table className="so-table">
        <caption className="sr-only">Recorded delivery options, best match first</caption>
        <thead>
          <tr>
            <th scope="col">Option</th>
            <th scope="col">Arrives (est.)</th>
            <th scope="col">Total</th>
            <th scope="col">
              <span className="sr-only">Select</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {options.map((o) => (
            <tr key={o.route_id} className={o.recommended ? 'is-best' : ''}>
              <td data-label="Option">
                <strong>{cap(service(o))}</strong>
                <span className="so-sub">
                  from {o.depot}
                  {o.depot.toLowerCase().includes(o.city.toLowerCase()) ? '' : `, ${o.city}`}
                </span>
                {o.recommended ? <span className="so-best">Best match</span> : null}
              </td>
              <td data-label="Arrives (est.)">
                {day(o.arrives_by)}
                <span className="so-sub">
                  {o.estimated_days !== null
                    ? `about ${o.estimated_days} day${o.estimated_days === 1 ? '' : 's'}`
                    : 'transit not recorded'}
                </span>
                {o.days_late ? (
                  <span className="so-miss">{o.days_late} day(s) late</span>
                ) : o.meets_date ? (
                  <span className="so-hit">On time</span>
                ) : null}
              </td>
              <td data-label="Total">
                {eur(o.total)}
                <span className="so-sub">{eur(o.cost.transport_cost)} delivery</span>
                {o.over_budget ? (
                  <span className="so-miss">{eur(o.over_budget)} over</span>
                ) : o.within_budget ? (
                  <span className="so-hit">In budget</span>
                ) : null}
              </td>
              <td>
                <button
                  type="button"
                  className={o.recommended ? 'so-btn so-btn--primary' : 'so-btn'}
                  disabled={busy}
                  onClick={() => select(o)}
                >
                  Select
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {decision.actions.length ? (
        <div className="so-actions" role="group" aria-label="Change what matters most">
          {decision.actions.map((action) => (
            <button
              key={action.label}
              type="button"
              className="so-btn so-btn--ghost"
              disabled={busy}
              onClick={() => onPatch(action.patch, action)}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
      <p className="so-foot">
        Estimates from recorded demo routes, not guaranteed dates. Totals exclude VAT.
        {hidden ? ` ${hidden} slower or dearer option(s) not shown.` : ''}
      </p>
    </section>
  )
}

/** Spark filled the order: the sentence above says it all, so only the yes is a button. The full summary, with its change options, is one click away. */
function AutoReview({
  order,
  summary,
  place,
  busy,
  onPatch,
}: {
  order: OrderResponse
  summary: OrderSummary
  place: NonNullable<OrderResponse['ask']>['choices'][number]
  busy: boolean
  onPatch: OrderChange
}) {
  const [open, setOpen] = useState(false)
  if (open) return <Review order={order} summary={summary} busy={busy} onPatch={onPatch} />
  return (
    <p className="so-inline-actions">
      <button
        type="button"
        className="btn btn-primary btn-sm"
        disabled={busy}
        onClick={() => onPatch({}, place)}
      >
        Place order
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={busy}
        onClick={() => setOpen(true)}
      >
        See details or change
      </button>
    </p>
  )
}

function Review({
  order,
  summary,
  busy,
  onPatch,
}: {
  order: OrderResponse
  summary: OrderSummary
  busy: boolean
  onPatch: OrderChange
}) {
  const place = order.ask?.choices.find((choice) => choice.confirm)
  const install = order.ask?.choices.find((choice) => choice.patch.service_required === true)
  const d = summary.destination
  const rows: [string, React.ReactNode][] = [
    [
      'Part',
      <>
        {summary.quantity} × {summary.part.part_number} · {summary.part.name}
        {summary.machine ? <span className="so-sub">for {summary.machine}</span> : null}
      </>,
    ],
    [
      'Deliver to',
      <>
        {d.street}, {d.postal_code} {d.city}, {d.country_code}
        {d.receiving_hours ? (
          <span className="so-sub">Receiving hours {d.receiving_hours}</span>
        ) : null}
      </>,
    ],
    [
      'Delivery',
      <>
        {cap(service(summary.transport))} from {summary.depot.name}
        <span className="so-sub">
          Arrives about {day(summary.transport.arrives_by)} (estimate)
          {summary.checks.needed_by
            ? ` · needed by ${day(summary.checks.needed_by)}`
            : ' · as soon as possible'}
        </span>
      </>,
    ],
    [
      'Dealer',
      <>
        {summary.dealer.name}, {summary.dealer.city}
        {summary.dealer_installation ? (
          <span className="so-sub">Installation requested</span>
        ) : null}
      </>,
    ],
    [
      'Contact',
      <>
        {summary.contact.name} · {summary.contact.email}
        <span className="so-sub">
          Receiver {summary.contact.receiver_name} · {summary.contact.receiver_phone}
        </span>
      </>,
    ],
  ]
  return (
    <section className="so-panel so-review" aria-label="Order summary">
      <h3 className="so-h">Review your order</h3>
      <dl className="so-rows">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <dl className="so-breakdown" aria-label="Price breakdown">
        <div>
          <dt>Parts subtotal</dt>
          <dd>{eur(summary.cost.part_cost)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd>{eur(summary.cost.transport_cost)}</dd>
        </div>
        <div>
          <dt>VAT</dt>
          <dd>Not included</dd>
        </div>
        <div className="so-breakdown__total">
          <dt>Total excl. VAT</dt>
          <dd>{eur(summary.total)}</dd>
        </div>
      </dl>
      <p className="so-foot">{summary.cost_note}</p>
      <div className="so-actions">
        {place ? (
          <button
            type="button"
            className="so-btn so-btn--primary so-btn--lg"
            disabled={busy}
            onClick={() => onPatch({}, place)}
          >
            Place order · {eur(summary.total)}
          </button>
        ) : null}
        <button
          type="button"
          className="so-btn so-btn--ghost"
          disabled={busy}
          onClick={() =>
            onPatch({}, { label: 'Change delivery option' } as OrderChoice, 'fulfilment')
          }
        >
          Change delivery
        </button>
        <button
          type="button"
          className="so-btn so-btn--ghost"
          disabled={busy}
          onClick={() => onPatch({}, { label: 'Edit my details' } as OrderChoice, 'details')}
        >
          Edit details
        </button>
        {install ? (
          <button
            type="button"
            className="so-btn so-btn--ghost"
            disabled={busy}
            onClick={() => onPatch(install.patch, install)}
          >
            Add dealer installation
          </button>
        ) : null}
      </div>
      <p className="so-foot">
        Nothing is ordered until you press Place order. No payment is taken in this demo.
      </p>
    </section>
  )
}

function Placed({ order }: { order: OrderResponse }) {
  const placed = order.order!
  const summary = order.summary
  return (
    <section className="so-placed" aria-label="Order placed">
      <CircleCheck size={28} aria-hidden="true" />
      <div>
        <h3>Order {placed.order_id} is placed</h3>
        <p>
          {placed.status_label ?? placed.status ?? 'Status recorded'}
          {summary
            ? ` · ${summary.quantity} × ${summary.part.part_number} · ${eur(placed.cost?.total ?? summary.total)} excl. VAT`
            : ''}
          {summary?.transport.arrives_by
            ? ` · arrives about ${day(summary.transport.arrives_by)}`
            : ''}
        </p>
        <div className="so-actions">
          <Link
            className="so-btn so-btn--primary"
            to={`/orders/${encodeURIComponent(placed.order_id)}`}
          >
            View order
          </Link>
          <Link className="so-btn so-btn--ghost" to="/orders">
            All my orders
          </Link>
        </div>
      </div>
      {order.profile_offer ? <SaveProfile offer={order.profile_offer} /> : null}
    </section>
  )
}

/** Questions that are not the quantity, delivery options or review: sites, machines, dealers, a date, contact details. */
function AskView({
  ask,
  busy,
  onPatch,
  said = false,
}: {
  ask: OrderAsk
  busy: boolean
  onPatch: OrderChange
  /** the message above already asks this question */
  said?: boolean
}) {
  const [date, setDate] = useState('')
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries((ask.fields ?? []).map((field) => [field.name, field.value])),
  )
  const many = ask.choices.length > 6
  return (
    <div className="so-panel so-ask">
      {said ? null : <p className="so-h">{ask.question}</p>}
      {ask.kind === 'date' ? (
        <form
          className="so-inline"
          onSubmit={(event) => {
            event.preventDefault()
            onPatch({ needed_by: date }, { label: `Needed by ${day(date)}` } as OrderChoice)
          }}
        >
          <label>
            Needed by
            <input
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <button type="submit" className="so-btn so-btn--primary" disabled={busy}>
            Use this date
          </button>
        </form>
      ) : null}
      {ask.kind === 'form' ? (
        <form
          className="so-form"
          onSubmit={(event) => {
            event.preventDefault()
            onPatch(form, { label: 'My details' } as OrderChoice)
          }}
        >
          {(ask.fields ?? []).map((field) => (
            <label key={field.name}>
              {field.label}
              <input
                type={field.type}
                required={field.required}
                autoComplete={
                  field.type === 'email' ? 'email' : field.type === 'tel' ? 'tel' : 'on'
                }
                value={form[field.name] ?? ''}
                onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
              />
            </label>
          ))}
          <button type="submit" className="so-btn so-btn--primary" disabled={busy}>
            Continue to review <ArrowRight size={15} aria-hidden="true" />
          </button>
        </form>
      ) : null}
      {ask.choices.length ? (
        <div className="so-choices" role="group" aria-label={ask.question}>
          {ask.choices.slice(0, many ? 5 : undefined).map((choice, n) => (
            <button
              type="button"
              key={choice.label}
              disabled={busy}
              className={choice.recommended ? 'is-recommended' : ''}
              onClick={() => onPatch(choice.patch, choice)}
            >
              <span>
                {n + 1}. {choice.label}
              </span>
              {choice.recommended ? <em>Suggested</em> : null}
              {choice.detail ? <small>{choice.detail}</small> : null}
            </button>
          ))}
        </div>
      ) : null}
      {many ? (
        <p className="so-note">
          {ask.choices.length - 5} more on record: type a name or number, or ask me for others.
        </p>
      ) : null}
    </div>
  )
}

/** The open order, pinned above the message box: what is chosen so far and a way back to it. */
export function OrderDraftBar({ order }: { order: OrderResponse }) {
  const s = order.slots
  const total = order.summary?.total
  return (
    <div className="so-draft" role="status" aria-label="Current order">
      <span className="so-draft__label">Order draft</span>
      <span className="so-draft__what">
        {order.part?.part_number}
        {typeof s.quantity === 'number' ? ` × ${s.quantity}` : ''}
        {typeof s.needed_by === 'string' ? ` · by ${day(s.needed_by)}` : ''}
        {total !== undefined && total !== null ? ` · ${eur(total)}` : ''}
      </span>
      <span className="so-draft__step">Next: {STEP_LABELS[order.stage] ?? order.stage}</span>
      <button
        type="button"
        onClick={() =>
          document
            .getElementById(ACTIVE_ORDER_ID)
            ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      >
        Go to order
      </button>
    </div>
  )
}

/** Offers to remember this order's details. Nothing is saved until the user presses the button, which is their consent. */
function SaveProfile({ offer }: { offer: Record<string, string> }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')
  const save = async () => {
    setState('saving')
    try {
      const current = await getProfile()
      await saveProfile({ ...(current.profile ?? {}), ...(offer as Partial<Profile>) }, true)
      setState('saved')
    } catch {
      setState('failed')
    }
  }
  return (
    <div className="so-save" aria-label="Save to profile">
      <p>
        Save the machine, delivery site, dealer and contact details to your profile so Spark won’t
        ask again? Stored only with your consent; erase them any time on{' '}
        <Link to="/profile">My profile</Link>.
      </p>
      {state === 'saved' ? (
        <p role="status">Saved to your profile.</p>
      ) : (
        <button
          type="button"
          className="so-btn"
          disabled={state === 'saving'}
          onClick={() => void save()}
        >
          Yes, save to my profile
        </button>
      )}
      {state === 'failed' ? (
        <p role="alert">Your profile could not be saved. Nothing was stored.</p>
      ) : null}
    </div>
  )
}
