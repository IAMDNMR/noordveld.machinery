import { Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { quoteCart } from '../../api'
import { useApi } from '../../hooks/useApi'
import { formatMoney } from '../../lib/format'
import { partPath } from '../../lib/storeQuery'
import { useCart } from '../../store/CartContext'
import { PartImage } from './PartImage'
import { QtyStepper } from './QtyStepper'
import { ErrorView } from './StateViews'

/**
 * The cart's lines and totals. The browser holds part ids and quantities; this component asks the API to price them,
 * so a name or a price shown here is always the graph's current value. Used by the drawer and the checkout page.
 */
export function CartContents({ onNavigate }: { onNavigate?: () => void }) {
  const { lines, setQty, remove } = useCart()
  const key = lines.map((l) => `${l.partId}:${l.qty}`).join(',')
  const quote = useApi((signal) => quoteCart(lines, signal), key)

  if (quote.error && !quote.data) return <ErrorView error={quote.error} onRetry={quote.reload} what="Your cart" />
  if (!quote.data) return <p className="cart__loading" role="status">Loading your cart…</p>

  const { data } = quote
  return (
    <>
      <ul className="cart__lines" aria-busy={quote.loading}>
        {data.lines.map(({ part, quantity, line_total }) => (
          <li key={part.part_id} className="cline">
            <PartImage partNumber={part.part_number} name={part.name} variant="mini" />
            <div>
              <Link to={partPath(part.part_number)} className="cline__name" onClick={onNavigate}>
                {part.name}
              </Link>
              <p className="cline__no mono">{part.part_number}</p>
              <div className="cline__row">
                <QtyStepper value={quantity} onChange={(qty) => setQty(part.part_id, qty)} label={`Quantity of ${part.name}`} compact />
                <button type="button" className="cline__remove" onClick={() => remove(part.part_id)} aria-label={`Remove ${part.name}`}>
                  <Trash2 size={17} strokeWidth={1.7} aria-hidden="true" />
                </button>
              </div>
              {line_total === null ? <p className="cline__note">No price available for this part</p> : null}
            </div>
            <p className="cline__total">{line_total ? formatMoney(line_total) : '—'}</p>
          </li>
        ))}
        {data.rejected.map(({ part, status_label, reason }) => (
          <li key={part.part_id} className="cline cline--blocked">
            <PartImage partNumber={part.part_number} name={part.name} variant="mini" />
            <div>
              <Link to={partPath(part.part_number)} className="cline__name" onClick={onNavigate}>
                {part.name}
              </Link>
              <p className="cline__no mono">{part.part_number}</p>
              <p className="cline__note" role="note">
                <strong>Cannot be ordered: {status_label}.</strong> {reason}
              </p>
            </div>
            <button type="button" className="cline__remove" onClick={() => remove(part.part_id)} aria-label={`Remove ${part.name}`}>
              <Trash2 size={17} strokeWidth={1.7} aria-hidden="true" />
            </button>
          </li>
        ))}
        {data.unknown_part_ids.map((id) => (
          <li key={id} className="cline cline--unknown">
            <p className="cline__note">A part in your cart ({id}) is no longer in the catalogue.</p>
            <button type="button" className="cline__remove" onClick={() => remove(id)} aria-label={`Remove unknown part ${id}`}>
              <Trash2 size={17} strokeWidth={1.7} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <dl className="cart__totals">
        <div className="cart__grand">
          <dt>Subtotal</dt>
          <dd>{data.subtotal ? formatMoney(data.subtotal) : 'Not available'}</dd>
        </div>
        {data.rejected.length > 0 ? (
          <div>
            <dt>{data.rejected.length === 1 ? '1 part cannot be ordered and is not included.' : `${data.rejected.length} parts cannot be ordered and are not included.`}</dt>
          </div>
        ) : null}
        {data.subtotal === null && data.unpriced_part_ids.length > 0 ? <div><dt>Some parts have no price, so no subtotal is shown.</dt></div> : null}
      </dl>
      <p className="cart__fine">{data.note}</p>
    </>
  )
}
