import { ShoppingBag } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { STORE_ROUTE } from '../../lib/storeQuery'
import { CartProvider, useCart } from '../../store/CartContext'
import { CartDrawer } from './CartDrawer'
import { StoreSearch } from './StoreSearch'
import '../../styles/wf.css'
import './store.css'

function StoreBar() {
  const { count, setOpen, justAdded } = useCart()
  const { pathname } = useLocation()
  const onIndex = pathname === STORE_ROUTE
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 420)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // The catalogue's own hero already carries a large search, so the compact one appears once it scrolls away.
  // Over the hero the bar is transparent; everywhere else it is a solid strip under the main nav.
  const over = onIndex && !scrolled

  return (
    <div className={`sbar ${over ? 'sbar--over' : ''}`}>
      <div className="wf-container sbar__inner">
        <Link to={STORE_ROUTE} className="sbar__title">
          Parts Store
        </Link>
        <div className="sbar__search" hidden={over}>
          <StoreSearch variant="bar" />
        </div>
        <button type="button" className={`sbar__cart ${justAdded ? 'is-bump' : ''}`} onClick={() => setOpen(true)} aria-label={`Open cart, ${count} ${count === 1 ? 'item' : 'items'}`}>
          <ShoppingBag size={20} strokeWidth={1.7} aria-hidden="true" />
          <span className="sbar__cart-label">Cart</span>
          {count > 0 ? <span className="sbar__count">{count}</span> : null}
        </button>
      </div>
    </div>
  )
}

/** Wraps every Parts Store page: shared cart, the sticky store bar and the cart drawer. */
export function StoreLayout() {
  return (
    <CartProvider>
      <div className="store wf">
        <StoreBar />
        <Outlet />
        <CartDrawer />
      </div>
    </CartProvider>
  )
}
