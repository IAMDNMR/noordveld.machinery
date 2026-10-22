import { ShoppingBag, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { CHECKOUT_ROUTE, STORE_ROUTE } from '../../lib/storeQuery'
import { useCart } from '../../store/CartContext'
import { CartContents } from './CartContents'

export function CartDrawer() {
  const { lines, count, open, setOpen, clear } = useCart()
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        return
      }
      if (e.key !== 'Tab') return
      const controls = [
        ...(panel.current?.querySelectorAll<HTMLElement>(
          'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]',
        ) ?? []),
      ].filter((node) => node.getClientRects().length > 0)
      const first = controls[0],
        last = controls[controls.length - 1]
      if (!first) {
        e.preventDefault()
        panel.current?.focus()
        return
      }
      if (
        e.shiftKey &&
        (document.activeElement === first || document.activeElement === panel.current)
      ) {
        e.preventDefault()
        last.focus()
      } else if (
        !e.shiftKey &&
        (document.activeElement === last || !panel.current?.contains(document.activeElement))
      ) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    panel.current?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      previous?.focus()
    }
  }, [open, setOpen])

  const close = () => setOpen(false)
  return (
    <div className={`cart ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <button
        type="button"
        className="cart__scrim"
        onClick={close}
        tabIndex={-1}
        aria-label="Close cart"
      />
      <div
        className="cart__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        tabIndex={-1}
        ref={panel}
        inert={!open}
      >
        <div className="cart__head">
          <h2 id="cart-title">
            Your cart{' '}
            <span>
              {count} {count === 1 ? 'item' : 'items'}
            </span>
          </h2>
          <button type="button" className="cart__close" onClick={close} aria-label="Close cart">
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>
        {lines.length === 0 ? (
          <div className="cart__empty">
            <ShoppingBag size={44} strokeWidth={1.1} aria-hidden="true" />
            <h3>Your cart is empty</h3>
            <p>Parts you add appear here.</p>
            <Link to={STORE_ROUTE} className="button button--primary" onClick={close}>
              Browse parts
            </Link>
          </div>
        ) : (
          <div className="cart__body">
            <CartContents onNavigate={close} />
            <div className="cart__actions">
              <Link
                to={CHECKOUT_ROUTE}
                className="button button--primary cart__order"
                onClick={close}
              >
                Review order
              </Link>
              <button type="button" className="cart__clear" onClick={clear}>
                Clear cart
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
