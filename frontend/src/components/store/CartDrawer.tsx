import { Check, PackageCheck, ShoppingCart, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { eur, partPath, regionalRate, storeCountries, STORE_ROUTE, type ShipMethod } from '../../data/store'
import { useCart } from '../../store/CartContext'
import { PartVisual } from './PartVisual'
import { QtyStepper } from './QtyStepper'

const round2 = (n: number): number => Math.round(n * 100) / 100

export function CartDrawer() {
  const { items, count, subtotal, open, setOpen, setQty, remove, clear } = useCart()
  const [country, setCountry] = useState('NL')
  const [method, setMethod] = useState<ShipMethod>('STANDARD')
  const [placed, setPlaced] = useState<{ ref: string; total: number } | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, setOpen])

  useEffect(() => {
    if (!open) setPlaced(null)
  }, [open])

  const vat = storeCountries.find((c) => c.code === country)?.vat ?? 0.21
  const rates = { STANDARD: regionalRate('STANDARD'), EXPRESS: regionalRate('EXPRESS') }
  const shipping = items.length ? (rates[method]?.price ?? 0) : 0
  const vatAmount = round2((subtotal + shipping) * vat)
  const total = round2(subtotal + shipping + vatAmount)

  const placeOrder = () => {
    setPlaced({ ref: `ND-${Date.now().toString().slice(-6)}`, total })
    clear()
  }

  return (
    <div className={`cart ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <div className="cart__scrim" onClick={() => setOpen(false)} />
      <aside className="cart__panel" role="dialog" aria-modal="true" aria-label="Your cart" inert={!open}>
        <header className="cart__head">
          <h2>
            Your cart <span>{count ? `${count} ${count === 1 ? 'item' : 'items'}` : ''}</span>
          </h2>
          <button ref={closeRef} type="button" className="cart__close" onClick={() => setOpen(false)} aria-label="Close cart">
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </header>

        {placed ? (
          <div className="cart__done">
            <span className="cart__done-mark">
              <Check size={30} strokeWidth={2} aria-hidden="true" />
            </span>
            <h3>Demo order {placed.ref}</h3>
            <p>
              Total {eur(placed.total)} including VAT. This is a demonstration: no order has been placed and no payment was taken.
            </p>
            <button type="button" className="button button--primary" onClick={() => setOpen(false)}>
              Continue browsing
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="cart__empty">
            <ShoppingCart size={40} strokeWidth={1.1} aria-hidden="true" />
            <h3>Your cart is empty</h3>
            <p>Find a part by name, number or machine and add it here.</p>
            <Link to={STORE_ROUTE} className="button button--primary" onClick={() => setOpen(false)}>
              Browse parts
            </Link>
          </div>
        ) : (
          <>
            <ul className="cart__lines">
              {items.map(({ part, qty, total: line }) => (
                <li key={part.id} className="cline">
                  <PartVisual part={part} variant="mini" />
                  <div className="cline__main">
                    <Link to={partPath(part)} className="cline__name" onClick={() => setOpen(false)}>
                      {part.name}
                    </Link>
                    <p className="cline__no mono">{part.no}</p>
                    <div className="cline__row">
                      <QtyStepper value={qty} onChange={(n) => setQty(part.id, n)} label={`Quantity of ${part.name}`} compact />
                      <strong>{eur(line)}</strong>
                    </div>
                    {part.availability === 'BACKORDER' ? <p className="cline__note">On backorder{part.backorder ? `, restock in about ${part.backorder.days} days` : ''}</p> : null}
                  </div>
                  <button type="button" className="cline__remove" onClick={() => remove(part.id)} aria-label={`Remove ${part.name}`}>
                    <Trash2 size={17} strokeWidth={1.6} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>

            <div className="cart__summary">
              <div className="cart__field">
                <label htmlFor="cart-country">Deliver to</label>
                <select id="cart-country" value={country} onChange={(e) => setCountry(e.target.value)}>
                  {storeCountries.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name} · VAT {Math.round(c.vat * 100)}%
                    </option>
                  ))}
                </select>
              </div>

              <fieldset className="cart__ship">
                <legend>Delivery</legend>
                {(['STANDARD', 'EXPRESS'] as const).map((m) => (
                  <label key={m} className={method === m ? 'is-on' : undefined}>
                    <input type="radio" name="ship" checked={method === m} onChange={() => setMethod(m)} />
                    <span className="cart__ship-name">{m === 'STANDARD' ? 'Standard' : 'Express'}</span>
                    <span className="cart__ship-days">{rates[m]?.days === 1 ? '1 day transit' : `${rates[m]?.days} days transit`}</span>
                    <span className="cart__ship-price">{eur(rates[m]?.price ?? 0)}</span>
                  </label>
                ))}
              </fieldset>

              <dl className="cart__totals">
                <div>
                  <dt>Subtotal</dt>
                  <dd>{eur(subtotal)}</dd>
                </div>
                <div>
                  <dt>Delivery (regional demo rate)</dt>
                  <dd>{eur(shipping)}</dd>
                </div>
                <div>
                  <dt>VAT {Math.round(vat * 100)}%</dt>
                  <dd>{eur(vatAmount)}</dd>
                </div>
                <div className="cart__grand">
                  <dt>Total</dt>
                  <dd>{eur(total)}</dd>
                </div>
              </dl>

              <button type="button" className="button button--primary cart__order" onClick={placeOrder}>
                <PackageCheck size={20} strokeWidth={1.8} aria-hidden="true" />
                Place demo order
              </button>
              <p className="cart__fine">Demonstration only. Prices and delivery are synthetic; nothing is charged or shipped.</p>
            </div>
          </>
        )}
      </aside>
    </div>
  )
}
