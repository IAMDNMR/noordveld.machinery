import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api'
import { getOrder, updateStatus, type OrderDetail } from '../api/orders'
import { Restricted } from '../components/orders/Restricted'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { roleLabel, useSession } from '../store/session'
import { statusTone } from './OrdersPage'
import '../styles/wf.css'
import '../components/orders/orders.css'

const money = (amount: number | null | undefined, currency = 'EUR') =>
  amount == null ? 'Not recorded' : new Intl.NumberFormat('en-NL', { style: 'currency', currency }).format(amount)
const fitText = (s: string | null) => (s === 'CONFIRMED' ? 'Confirmed fit' : s === 'CONDITIONAL' ? 'Conditional fit · verification required' : 'Fitment not verified')
const DATA: Record<string, string> = { SYNTHETIC_DEMO: 'Synthetic demo', SOURCE_DERIVED: 'Source-derived', USER_PROVIDED: 'Recorded in the app', DERIVED: 'Derived' }

/** One order or request. Both roles see the same facts about their order; only the Order Processor gets the operational detail and actions. */
export default function OrderDetailPage() {
  const { orderId = '' } = useParams()
  const { user, ready } = useSession()
  usePageMeta({ title: orderId, description: 'Order or purchase request.', path: `/orders/${orderId}` })
  const state = useApi((s) => (user ? getOrder(orderId, s) : Promise.resolve(null)), `order:${orderId}:${user?.id ?? 'none'}`)
  const [order, setOrder] = useState<OrderDetail | null>(null)
  const shown = order && order.order_id === orderId ? order : state.data

  if (!ready) return <div className="wf ord-page" />
  return (
    <div className="wf ord-page">
      <div className="wf-container">
        <Link className="back-link" to="/orders">
          <ArrowLeft size={14} strokeWidth={2} aria-hidden="true" /> {user?.role === 'ORDER_PROCESSOR' ? 'Order processing' : 'My requests & orders'}
        </Link>
        {!user ? (
          <Restricted reason="signed_out" />
        ) : state.error ? (
          <Restricted reason={state.error.status === 401 ? 'signed_out' : state.error.status === 404 ? 'not_found' : 'forbidden'} />
        ) : !shown ? (
          <p className="muted">Loading order…</p>
        ) : (
          <Detail o={shown} processor={user.role === 'ORDER_PROCESSOR'} onChange={setOrder} />
        )}
      </div>
    </div>
  )
}

function Detail({ o, processor, onChange }: { o: OrderDetail; processor: boolean; onChange: (o: OrderDetail) => void }) {
  return (
    <>
      <header className="ord-head">
        <div>
          <p className="eyebrow">{o.channel === 'DEMO_APP_REQUEST' ? 'Purchase request' : 'Order'}</p>
          <h1>{o.order_id}</h1>
          <p className="muted">
            {o.order_date ? `Created ${o.order_date}` : 'Creation date not recorded'}
            {processor && o.customer ? ` · ${o.customer.name}${o.delivery_address?.city ? `, delivers to ${o.delivery_address.city}` : ''}` : ''}
          </p>
        </div>
        <span className={`tag ${statusTone(o.status)} ord-status`}>{o.status_label}</span>
      </header>

      {processor ? <Actions o={o} onChange={onChange} /> : null}

      <div className="ord-grid">
        <section className="card card-pad" aria-labelledby="ord-items">
          <h2 id="ord-items">Items</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Part</th>
                  <th scope="col">Qty</th>
                  <th scope="col">Unit price</th>
                  <th scope="col">Line total</th>
                </tr>
              </thead>
              <tbody>
                {o.lines.map((l) => (
                  <tr key={l.part_id}>
                    <th scope="row">
                      <Link className="link-more" to={`/parts-store/${encodeURIComponent(l.part_number)}`}>
                        {l.part_number}
                      </Link>
                      <small>{l.name}</small>
                    </th>
                    <td>{l.quantity}</td>
                    <td>{money(l.unit_price_eur)}</td>
                    <td>{money(l.line_total_eur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="kv-list ord-totals">
            <div className="kv-row">
              <dt>Subtotal, ex VAT</dt>
              <dd>{money(o.totals.subtotal_ex_vat, o.currency)}</dd>
            </div>
            {o.totals.vat_amount != null ? (
              <div className="kv-row">
                <dt>VAT</dt>
                <dd>{money(o.totals.vat_amount, o.currency)}</dd>
              </div>
            ) : null}
            {o.totals.total_incl_vat != null ? (
              <div className="kv-row">
                <dt>Total, incl. VAT</dt>
                <dd>{money(o.totals.total_incl_vat, o.currency)}</dd>
              </div>
            ) : null}
          </dl>
          {o.totals.note ? <p className="small muted">{o.totals.note}</p> : null}
          <p className="disclaimer">{o.payment}</p>
        </section>

        <section className="card card-pad" aria-labelledby="ord-fit">
          <h2 id="ord-fit">Fitment & availability</h2>
          {o.lines.map((l) => (
            <div key={l.part_id} className="ord-line">
              <p className="part-number">{l.part_number}</p>
              <div className="chip-row">
                {l.fitment.length ? (
                  l.fitment.map((f) => (
                    <span key={f.model_code} className={`tag ${f.status === 'CONFIRMED' ? 'tag-good' : 'tag-warn'}`}>
                      {f.model_code} · {fitText(f.status)}
                    </span>
                  ))
                ) : (
                  <span className="tag tag-warn">No fitment recorded · identification required</span>
                )}
              </div>
              <dl className="kv-list">
                <div className="kv-row">
                  <dt>Availability</dt>
                  <dd>{l.availability_state ? l.availability_state.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Not recorded'}</dd>
                </div>
                <div className="kv-row">
                  <dt>Fulfilment</dt>
                  <dd>{l.fulfilment}</dd>
                </div>
                {processor ? (
                  <>
                    <div className="kv-row">
                      <dt>Part status</dt>
                      <dd>{l.part_status ? `${l.part_status.replace(/_/g, ' ').toLowerCase()}${l.orderable ? ' · orderable' : ' · not orderable'}` : 'Not recorded'}</dd>
                    </div>
                    <div className="kv-row">
                      <dt>Recorded price</dt>
                      <dd>{l.price ? `${money(l.price.list_price_ex_vat, l.price.currency)} ex VAT` : 'Not recorded'}</dd>
                    </div>
                    <div className="kv-row">
                      <dt>Stock</dt>
                      <dd>
                        {(l.warehouses ?? []).length ? `${l.in_stock_units} units` : 'Not recorded'}
                        {(l.warehouses ?? []).map((w) => (
                          <small key={w.warehouse_id}>
                            {w.name} · {w.available ?? 'not recorded'}
                          </small>
                        ))}
                      </dd>
                    </div>
                    <div className="kv-row">
                      <dt>Supplier</dt>
                      <dd>
                        {(l.suppliers ?? []).length
                          ? (l.suppliers ?? []).map((s) => (
                              <small key={s.name}>
                                {s.name}
                                {s.primary ? ' · primary' : ''}
                                {s.lead_time_days != null ? ` · lead time ${s.lead_time_days} days` : ''}
                              </small>
                            ))
                          : 'No supplier relationship recorded'}
                      </dd>
                    </div>
                  </>
                ) : null}
              </dl>
            </div>
          ))}
        </section>

        <section className="card card-pad" aria-labelledby="ord-ship">
          <h2 id="ord-ship">Shipment & tracking</h2>
          {o.shipments.length === 0 ? (
            <p className="pi-empty">No shipment is recorded yet.</p>
          ) : (
            o.shipments.map((s) => (
              <div key={s.shipment_id} className="ord-line">
                <p className="spread">
                  <strong>{s.shipment_id}</strong>
                  <span className={`tag ${s.status === 'DELIVERED' ? 'tag-good' : 'tag-info'}`}>{s.status ? s.status.toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Status not recorded'}</span>
                </p>
                <p className="small muted">
                  {[s.carrier, s.dispatched_from ? `from ${s.dispatched_from}` : null, s.tracking_ref ? `tracking ${s.tracking_ref}` : 'tracking number not recorded'].filter(Boolean).join(' · ')}
                </p>
                <ol className="ord-timeline">
                  {s.events.map((e) => (
                    <li key={`${s.shipment_id}-${e.event_seq}`}>
                      <strong>{e.event_status ?? 'Event'}</strong>
                      <span className="small muted">{[e.event_date, e.event_location].filter(Boolean).join(' · ')}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))
          )}
        </section>

        <section className="card card-pad" aria-labelledby="ord-history">
          <h2 id="ord-history">Status history</h2>
          {o.history.length === 0 ? (
            <p className="pi-empty">No status events are recorded.</p>
          ) : (
            <ol className="ord-timeline">
              {o.history.map((e, n) => (
                <li key={`${e.sequence}-${n}`}>
                  <strong>{e.status_label}</strong>
                  <span className="small muted">
                    {[e.occurred_at ? e.occurred_at.replace('T', ' ').replace('+00:00', ' UTC') : null, e.by ? `by ${e.by}${e.role ? ` (${roleLabel(e.role as 'END_USER' | 'ORDER_PROCESSOR')})` : ''}` : null, e.recorded ? DATA[e.recorded] ?? e.recorded : null]
                      .filter(Boolean)
                      .join(' · ') || 'Recorded in the demo dataset'}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>

        {processor ? (
          <section className="card card-pad" aria-labelledby="ord-evidence">
            <h2 id="ord-evidence">Evidence</h2>
            <dl className="kv-list">
              <div className="kv-row">
                <dt>Order record</dt>
                <dd>{DATA[o.data_status ?? ''] ?? o.data_status ?? 'Not stated'}</dd>
              </div>
              {o.lines.map((l) => (
                <div key={l.part_id} className="kv-row">
                  <dt>{l.part_number}</dt>
                  <dd>
                    Fitment: {l.evidence?.fitment}
                    <small>Inventory: {DATA[l.evidence?.inventory ?? ''] ?? 'not stated'} · Price: {DATA[l.evidence?.price ?? ''] ?? 'not stated'}</small>
                  </dd>
                </div>
              ))}
            </dl>
            <Link className="link-more" to={`/parts-intelligence?part=${encodeURIComponent(o.lines[0]?.part_number ?? '')}`}>
              Investigate in Parts Intelligence →
            </Link>
          </section>
        ) : null}
      </div>
    </>
  )
}

/** The Order Processor's one next step. The server decides whether it is valid and whether the graph supports it. */
function Actions({ o, onChange }: { o: OrderDetail; onChange: (o: OrderDetail) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const next = o.next
  const go = async () => {
    if (!next) return
    setBusy(true)
    setError(null)
    try {
      onChange(await updateStatus(o.order_id, next.status, o.status))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The status could not be changed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card card-pad ord-actions" aria-labelledby="ord-actions">
      <h2 id="ord-actions">Next step</h2>
      {!next ? (
        <p className="muted">This order is complete. No further status applies.</p>
      ) : (
        <div className="spread">
          <div>
            <p>
              Move from <strong>{o.status_label}</strong> to <strong>{next.label}</strong>
            </p>
            {!next.allowed && next.reason ? <p className="small ord-blocked">{next.reason}</p> : <p className="small muted">The change is recorded in the status history with your name and the time.</p>}
          </div>
          <button type="button" className="btn btn-accent" disabled={!next.allowed || busy} onClick={go}>
            {busy ? 'Saving…' : `Mark as ${next.label.toLowerCase()}`}
          </button>
        </div>
      )}
      {error ? (
        <p className="pi-error ord-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}
