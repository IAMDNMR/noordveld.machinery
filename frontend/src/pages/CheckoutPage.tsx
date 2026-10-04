import { ShoppingBag } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api'
import { submitRequest } from '../api/orders'
import { CartContents } from '../components/store/CartContents'
import { usePageMeta } from '../hooks/usePageMeta'
import { CHECKOUT_ROUTE, STORE_ROUTE } from '../lib/storeQuery'
import { useCart } from '../store/CartContext'
import { useSession } from '../store/session'

/**
 * Order review. The catalogue API prices a cart but cannot place an order or take a payment, so this page says so plainly.
 * A signed-in End User can submit the cart as a purchase request for an Order Processor to review; nothing is paid or placed.
 */
export default function CheckoutPage() {
  usePageMeta({ title: 'Review order', description: 'Review the parts in your cart. Order placement is not connected in this demonstration store.', path: CHECKOUT_ROUTE })
  const { lines, clear } = useCart()
  const { user } = useSession()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // one key per visit and cart content: a double click or a retry never creates two requests, a later visit can request again
  const [visit] = useState(() => Math.random().toString(36).slice(2, 10))
  const key = `${visit}-${lines.map((l) => `${l.partId}x${l.qty}`).sort().join('-')}`.slice(0, 80)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const order = await submitRequest(lines.map((l) => ({ part_id: l.partId, quantity: l.qty })), key.padEnd(8, '0'))
      clear()
      navigate(`/orders/${encodeURIComponent(order.order_id)}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The request could not be submitted.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wf-container pco">
      <h1>Review your order</h1>
      <p className="pco__notice" role="note">
        <strong>Order placement is not connected in this demo.</strong> No order is placed and no payment is taken. This page shows the cart as the parts service prices it.
      </p>
      {lines.length === 0 ? (
        <div className="scat__empty">
          <ShoppingBag size={44} strokeWidth={1.1} aria-hidden="true" />
          <h3>Your cart is empty</h3>
          <Link to={STORE_ROUTE} className="btn btn-primary">
            Browse parts
          </Link>
        </div>
      ) : (
        <div className="pco__panel">
          <CartContents />
          {user?.role === 'END_USER' ? (
            <>
              <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
                {busy ? 'Submitting…' : 'Submit purchase request'}
              </button>
              <p className="small muted">The request goes to Noordveld order processing for review. It is not a paid order.</p>
            </>
          ) : user?.role === 'ORDER_PROCESSOR' ? (
            <p className="small muted">Order Processors review requests; they do not submit them.</p>
          ) : (
            <p className="small muted">
              <Link className="link-more" to={`/sign-in?next=${encodeURIComponent(CHECKOUT_ROUTE)}`}>
                Sign in as an End User
              </Link>{' '}
              to submit this cart as a purchase request.
            </p>
          )}
          {error ? (
            <p className="pi-error" role="alert">
              {error}
            </p>
          ) : null}
          <button type="button" className="btn btn-secondary" disabled>
            Place order (not available)
          </button>
          <Link to={STORE_ROUTE} className="link-more">
            Continue browsing
          </Link>
        </div>
      )}
    </div>
  )
}
