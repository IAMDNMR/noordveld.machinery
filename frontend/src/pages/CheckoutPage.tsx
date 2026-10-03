import { ShoppingBag } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CartContents } from '../components/store/CartContents'
import { usePageMeta } from '../hooks/usePageMeta'
import { CHECKOUT_ROUTE, STORE_ROUTE } from '../lib/storeQuery'
import { useCart } from '../store/CartContext'

/**
 * A prepared order review. The catalogue API prices a cart but cannot place an order, so this page says so plainly and
 * offers no payment or confirmation step.
 */
export default function CheckoutPage() {
  usePageMeta({ title: 'Review order', description: 'Review the parts in your cart. Order placement is not connected in this demonstration store.', path: CHECKOUT_ROUTE })
  const { lines } = useCart()

  return (
    <div className="container pco">
      <h1>Review your order</h1>
      <p className="pco__notice" role="note">
        <strong>Demonstration only.</strong> Order placement is not connected, so no order is placed and nothing is charged. This page shows the cart as the parts service prices it.
      </p>
      {lines.length === 0 ? (
        <div className="scat__empty">
          <ShoppingBag size={44} strokeWidth={1.1} aria-hidden="true" />
          <h3>Your cart is empty</h3>
          <Link to={STORE_ROUTE} className="button button--primary">
            Browse parts
          </Link>
        </div>
      ) : (
        <div className="pco__panel">
          <CartContents />
          <button type="button" className="button button--primary" disabled>
            Place order (not available)
          </button>
          <Link to={STORE_ROUTE} className="pd__incart">
            Continue browsing
          </Link>
        </div>
      )}
    </div>
  )
}
