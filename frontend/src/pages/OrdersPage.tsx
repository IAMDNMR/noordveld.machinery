import { Link, useSearchParams } from 'react-router-dom'
import { DIRECT_ORDER, getOrders, type OrderRow, type Queue } from '../api/orders'
import { Restricted } from '../components/orders/Restricted'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { useSession } from '../store/session'
import '../styles/wf.css'
import '../components/orders/orders.css'

const QUEUES: { id: Queue | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending_review', label: 'Pending review' },
  { id: 'needs_fulfilment', label: 'Needs fulfilment' },
  { id: 'ready_to_ship', label: 'Ready to ship' },
  { id: 'shipped', label: 'Shipped' },
  { id: 'completed', label: 'Completed' },
  { id: 'exceptions', label: 'Exceptions' },
]

const WARN = new Set(['CANCELLED', 'REJECTED', 'ALLOCATION_FAILED', 'ALLOCATION_RELEASED', 'SHIPMENT_EXCEPTION', 'DELIVERY_FAILED', 'SERVICE_CANCELLED'])
export const statusTone = (status: string): string =>
  status === 'DELIVERED' || status === 'COMPLETED' ? 'tag-good' : status === 'SHIPPED' || status === 'ALLOCATED' || status === 'READY_TO_SHIP' ? 'tag-info' : status === 'NEW' || WARN.has(status) ? 'tag-warn' : 'tag-plain'

const money = (amount: number | null, currency: string, direct = false) =>
  amount == null ? (direct ? 'Not available' : 'Not recorded') : new Intl.NumberFormat('en-NL', { style: 'currency', currency }).format(amount)

/** End User: my requests and orders. Order Processor: the work queue. Which one is shown follows the role the server returns. */
export default function OrdersPage() {
  const { user, ready } = useSession()
  const processor = user?.role === 'ORDER_PROCESSOR'
  usePageMeta({ title: processor ? 'Order processing' : 'My orders', description: 'Orders and their status.', path: '/orders' })
  const orders = useApi((s) => (user ? getOrders(s) : Promise.resolve(null)), `orders:${user?.id ?? 'none'}`)
  const [params, setParams] = useSearchParams()
  const queue = (params.get('queue') as Queue | null) ?? 'all'

  if (!ready) return <div className="wf ord-page" />
  return (
    <div className="wf ord-page">
      <div className="wf-container">
        <p className="eyebrow">{processor ? 'Order Processor' : 'End User'}</p>
        <h1>{processor ? 'Order processing' : 'My orders'}</h1>
        <p className="lede">
          {processor
            ? 'Customer orders to allocate, fulfil, ship and follow. Every step is recorded in the Noordveld graph; nothing here edits catalogue facts.'
            : 'Your orders, their status and how they are being fulfilled.'}
        </p>

        {!user ? (
          <Restricted reason="signed_out" />
        ) : orders.error ? (
          <Restricted reason={orders.error.status === 401 ? 'signed_out' : 'forbidden'} />
        ) : !orders.data ? (
          <p className="muted ord-loading">Loading orders…</p>
        ) : (
          <>
            {processor ? (
              <div className="chip-row ord-queues" role="group" aria-label="Queue">
                {QUEUES.map((q) => {
                  const n = q.id === 'all' ? orders.data!.length : orders.data!.filter((o) => o.queue === q.id).length
                  return (
                    <button key={q.id} type="button" className="chip" aria-pressed={queue === q.id} onClick={() => setParams(q.id === 'all' ? {} : { queue: q.id })}>
                      {q.label} <span className="muted">{n}</span>
                    </button>
                  )
                })}
              </div>
            ) : null}
            <OrderTable rows={orders.data.filter((o) => queue === 'all' || o.queue === queue)} processor={processor} />
          </>
        )}
      </div>
    </div>
  )
}

function OrderTable({ rows, processor }: { rows: OrderRow[]; processor: boolean }) {
  if (rows.length === 0) return <p className="pi-empty">{processor ? 'No orders in this queue.' : 'You have no orders yet. Add verified parts to your cart and place an order at checkout.'}</p>
  return (
    <div className="card ord-table">
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Order / request</th>
              {processor ? <th scope="col">Customer</th> : null}
              <th scope="col">Date</th>
              <th scope="col">Parts</th>
              <th scope="col">Fits</th>
              <th scope="col">Status</th>
              <th scope="col">Fulfilment</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.order_id}>
                <th scope="row">
                  <Link className="link-more" to={`/orders/${encodeURIComponent(o.order_id)}`}>
                    {o.order_id}
                  </Link>
                  {o.data_status === 'USER_PROVIDED' ? <small>Submitted in the app</small> : null}
                </th>
                {processor ? <td data-label="Customer">{o.customer}</td> : null}
                <td data-label="Date">{o.order_date ?? 'Not recorded'}</td>
                <td data-label="Parts">{o.parts.join(', ') || 'No lines'}</td>
                <td data-label="Fits">{o.fits.length ? o.fits.slice(0, 3).join(', ') + (o.fits.length > 3 ? ` +${o.fits.length - 3}` : '') : 'No fitment recorded'}</td>
                <td data-label="Status">
                  <span className={`tag ${statusTone(o.status)}`}>{o.status_label}</span>
                </td>
                <td data-label="Fulfilment">{o.fulfilment}</td>
                <td data-label="Total">{money(o.total, o.currency, o.channel === DIRECT_ORDER)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
