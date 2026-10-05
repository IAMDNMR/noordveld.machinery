import { useState } from 'react'
import { ApiError } from '../../api'
import { orderAction, type OrderDetail, type OrderStatus } from '../../api/orders'

const STAGE_LABEL: Record<string, string> = { done: 'done', current: 'in progress', pending: 'to do', exception: 'exception', skipped: 'not required' }
const when = (iso: string | null | undefined) => (iso ? iso.replace('T', ' ').replace('+00:00', ' UTC') : null)
const days = (n: number | null | undefined) => (n == null ? 'not recorded' : `${n} ${n === 1 ? 'day' : 'days'}`)
const mode = (m: string | null | undefined) => (m ? m.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Not recorded')
const label = (s: string | null | undefined) => (s ? s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Not recorded')
const DANGER = new Set(['cancel', 'reject', 'release_allocation', 'shipment_exception', 'delivery_failed', 'service_cancel'])

/**
 * A direct order (placed through the Parts Store checkout). Everything shown, including the lifecycle stage and which actions are valid next, is read
 * from the order as AuraDB holds it: reload the page and the same state comes back. The browser decides nothing about the order's stage.
 */
export function DirectDetail({ o, processor, placed, onChange }: { o: OrderDetail; processor: boolean; placed: boolean; onChange: (o: OrderDetail) => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const run = async (action: string) => {
    setBusy(action)
    setError(null)
    try {
      onChange(await orderAction(o.order_id, action, o.status as OrderStatus))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The action could not be completed.')
    } finally {
      setBusy(null)
    }
  }
  const allowed = (o.actions ?? []).filter((a) => a.allowed)
  const blockedActions = (o.actions ?? []).filter((a) => !a.allowed && processor)
  const svc = o.service
  const stockWarn = o.status === 'ALLOCATION_FAILED'

  return (
    <>
      <header className="ord-head">
        <div>
          <p className="eyebrow">Order</p>
          <h1>{o.order_id}</h1>
          <p className="muted">
            {o.order_date ? `Placed ${o.order_date}` : 'Date not recorded'}
            {o.requester?.name ? ` · ${o.requester.name}${o.requester.company ? `, ${o.requester.company}` : ''}` : ''}
          </p>
        </div>
        <span className={`tag ${o.status === 'COMPLETED' || o.status === 'DELIVERED' ? 'tag-good' : o.status === 'ALLOCATED' || o.status === 'SHIPPED' ? 'tag-info' : stockWarn || ['CANCELLED', 'REJECTED', 'DELIVERY_FAILED', 'SHIPMENT_EXCEPTION', 'ALLOCATION_RELEASED', 'SERVICE_CANCELLED'].includes(o.status) ? 'tag-warn' : 'tag-plain'} ord-status`}>
          {o.status_label}
        </span>
      </header>

      {placed ? (
        <section className="card card-pad ord-placed" role="status" aria-label="Order confirmation">
          <h2>Order placed</h2>
          <p>
            Your order <strong>{o.order_id}</strong> has been placed
            {o.status === 'ALLOCATED' ? ' and its stock has been allocated at the depot.' : stockWarn ? ', but the stock could not be allocated. The Order Processor will follow up.' : '.'}
          </p>
          <p className="small muted">No payment is taken in this demo. Stock, transport and tracking information are synthetic demo data.</p>
        </section>
      ) : null}

      <section className="card card-pad ord-stages-card" aria-label="Order progress">
        <ol className="ord-stages">
          {(o.stages ?? []).map((s) => (
            <li key={s.stage} className={`is-${s.state}`}>
              <span className="ord-stages__dot" aria-hidden="true" />
              <strong>{s.stage}</strong>
              <small>{STAGE_LABEL[s.state]}</small>
            </li>
          ))}
        </ol>
      </section>

      {allowed.length > 0 || blockedActions.length > 0 ? (
        <section className="card card-pad ord-actions" aria-labelledby="ord-actions">
          <h2 id="ord-actions">{processor ? 'Next steps' : 'Your options'}</h2>
          <div className="ord-actionrow">
            {allowed.map((a) => (
              <div key={a.action}>
                <button type="button" className={`btn ${DANGER.has(a.action) ? 'btn-secondary' : 'btn-accent'}`} disabled={busy !== null} onClick={() => run(a.action)}>
                  {busy === a.action ? 'Saving…' : a.label}
                </button>
                {a.note ? <p className="small muted">{a.note}</p> : null}
              </div>
            ))}
          </div>
          {blockedActions.length > 0 ? (
            <ul className="small ord-blocked">
              {blockedActions.map((a) => (
                <li key={a.action}>
                  {a.label}: {a.reason}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="small muted">Each step is recorded in the status history with the person and the time.</p>
          {error ? (
            <p className="pi-error ord-error" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      ) : null}

      <div className="ord-grid">
        <section className="card card-pad" aria-labelledby="ord-items">
          <h2 id="ord-items">Items</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Part</th>
                  <th scope="col">Qty</th>
                  <th scope="col">Machine</th>
                  <th scope="col">Allocation</th>
                </tr>
              </thead>
              <tbody>
                {o.lines.map((l) => (
                  <tr key={l.part_id + (l.machine ?? '')}>
                    <th scope="row">
                      {l.part_number}
                      <small>{l.name}</small>
                    </th>
                    <td>{l.quantity}</td>
                    <td>{l.machine ?? 'Not specified'}</td>
                    <td>
                      {label(l.allocation_status)}
                      {l.reserved_quantity ? <small>{l.reserved_quantity} reserved</small> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {processor
            ? o.lines.map((l) => (
                <p key={l.part_id + 'stock'} className="small muted">
                  Depot stock now, {l.part_number}:{' '}
                  {(l.warehouses ?? []).filter((w) => w.warehouse_id === o.fulfilment?.depot?.warehouse_id).map((w) => `${label(w.stock_status)}${w.available != null ? ` (${w.available} available)` : ' (quantity unknown)'}`).join('') || 'not recorded'}
                </p>
              ))
            : null}
        </section>

        <section className="card card-pad" aria-labelledby="ord-requester">
          <h2 id="ord-requester">Requester</h2>
          <dl className="kv-list">
            <div className="kv-row"><dt>Name</dt><dd>{o.requester?.name}</dd></div>
            <div className="kv-row"><dt>Company</dt><dd>{o.requester?.company}</dd></div>
            <div className="kv-row"><dt>Email</dt><dd>{o.requester?.email}</dd></div>
            <div className="kv-row"><dt>Phone</dt><dd>{o.requester?.phone}</dd></div>
          </dl>
          <p className="small muted">Entered at checkout and kept with this order. No customer record was created.</p>
        </section>

        <section className="card card-pad" aria-labelledby="ord-delivery">
          <h2 id="ord-delivery">Delivery &amp; dealer</h2>
          <dl className="kv-list">
            <div className="kv-row"><dt>Ship-to</dt><dd>{o.delivery?.street}, {o.delivery?.postal_code} {o.delivery?.city}, {o.delivery?.country_code}<small>Site {o.delivery?.ship_to_id}</small></dd></div>
            <div className="kv-row"><dt>Receiver</dt><dd>{o.receiver?.name}<small>{o.receiver?.phone}</small></dd></div>
            <div className="kv-row"><dt>Dealer</dt><dd>{o.dealer?.name}<small>{o.dealer?.city}, {o.dealer?.country_code} · {o.dealer_service_required ? 'installation requested' : 'no installation requested'}</small></dd></div>
          </dl>
        </section>

        <section className="card card-pad" aria-labelledby="ord-fulfil">
          <h2 id="ord-fulfil">Fulfilment &amp; transport</h2>
          <dl className="kv-list">
            <div className="kv-row"><dt>Fulfilment depot</dt><dd>{o.fulfilment?.depot?.name}<small>{o.fulfilment?.depot?.city}, {o.fulfilment?.depot?.country_code} · stock {label(o.fulfilment?.allocation_status).toLowerCase()}{o.fulfilment?.allocation_updated_at ? ` (${when(o.fulfilment.allocation_updated_at)})` : ''}</small></dd></div>
            <div className="kv-row"><dt>Transport</dt><dd>{o.transport?.option_code?.replace(/_/g, ' ')}<small>{mode(o.transport?.mode)} · {o.transport?.distance_km ?? '?'} km · estimated {days(o.transport?.estimated_days)} ({(o.transport?.estimate_basis ?? 'estimated').toLowerCase()})</small></dd></div>
            <div className="kv-row"><dt>Freight context</dt><dd>{o.transport?.freight_estimate ? `${o.transport.freight_estimate.currency} ${o.transport.freight_estimate.amount.toFixed(2)}` : 'Not recorded'}<small>{o.transport?.freight_estimate?.label ?? ''}</small></dd></div>
          </dl>
          <p className="small"><span className="badge badge-data">Synthetic demo data</span> Depot, route, estimate and tracking are demonstration data.</p>
        </section>

        <section className="card card-pad" aria-labelledby="ord-cost">
          <h2 id="ord-cost">Cost</h2>
          <dl className="kv-list">
            <div className="kv-row"><dt>Part cost</dt><dd>Not available</dd></div>
            <div className="kv-row"><dt>Transportation cost</dt><dd>Not available</dd></div>
            <div className="kv-row"><dt>Total</dt><dd>Not available</dd></div>
          </dl>
          <p className="small muted">{o.cost?.note}</p>
          <p className="disclaimer">{o.payment}</p>
        </section>

        <section className="card card-pad" aria-labelledby="ord-ship">
          <h2 id="ord-ship">Shipment &amp; tracking</h2>
          {o.shipments.length === 0 ? (
            <p className="pi-empty">No shipment has been created yet.</p>
          ) : (
            o.shipments.map((s) => (
              <div key={s.shipment_id} className="ord-line">
                <p className="spread">
                  <strong>{s.shipment_id}</strong>
                  <span className={`tag ${s.status === 'DELIVERED' ? 'tag-good' : s.status === 'CANCELLED' || s.status === 'EXCEPTION' || s.status === 'DELIVERY_FAILED' ? 'tag-warn' : 'tag-info'}`}>{label(s.status)}</span>
                </p>
                <p className="small muted">
                  From {s.dispatched_from} to {s.destination?.city}, {s.destination?.country_code} · {s.option} · tracking {s.tracking_ref}
                </p>
                <p className="small"><span className="badge badge-data">Synthetic demo tracking</span> No carrier is connected.</p>
                <ol className="ord-timeline">
                  {s.events.map((e) => (
                    <li key={`${s.shipment_id}-${e.event_seq}`}>
                      <strong>{label(e.event_status)}</strong>
                      <span className="small muted">{[e.event_date, e.event_location].filter(Boolean).join(' · ')}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))
          )}
        </section>

        {o.dealer_service_required ? (
          <section className="card card-pad" aria-labelledby="ord-service">
            <h2 id="ord-service">Dealer service</h2>
            {!svc ? (
              <p className="pi-empty">Dealer installation was requested. It starts when the order is delivered.</p>
            ) : (
              <>
                <p className="spread">
                  <strong>{svc.dealer}</strong>
                  <span className={`tag ${svc.service_status === 'COMPLETED' ? 'tag-good' : svc.service_status === 'CANCELLED' ? 'tag-warn' : 'tag-info'}`}>{label(svc.service_status)}</span>
                </p>
                <ol className="ord-timeline">
                  {([['Created', svc.created_at], ['Part received', svc.part_received_at], ['Started', svc.started_at], ['Installed', svc.installed_at], ['Completed', svc.completed_at], ['Cancelled', svc.cancelled_at]] as [string, string | null][])
                    .filter(([, t]) => t)
                    .map(([name, t]) => (
                      <li key={name}>
                        <strong>{name}</strong>
                        <span className="small muted">{when(t)}</span>
                      </li>
                    ))}
                </ol>
              </>
            )}
          </section>
        ) : null}

        <section className="card card-pad" aria-labelledby="ord-history">
          <h2 id="ord-history">Status history</h2>
          <ol className="ord-timeline">
            {o.history.map((e, n) => (
              <li key={`${e.sequence}-${n}`}>
                <strong>{e.status_label}</strong>
                <span className="small muted">{[when(e.occurred_at), e.by ? `by ${e.by}` : null, e.action ? e.action.replace(/_/g, ' ') : null].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  )
}
