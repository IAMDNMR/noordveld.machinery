import { Check, ShoppingCart } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { PartSummary } from '../../api'
import { formatMoney } from '../../lib/format'
import { partPath } from '../../lib/storeQuery'
import { useCart } from '../../store/CartContext'
import { AvailabilityBadge, StatusFlag } from './Badges'
import { PartImage } from './PartImage'

interface PartCardProps {
  part: PartSummary
  /** `row` is the list layout of the catalogue */
  layout?: 'tile' | 'row'
}

export function PartCard({ part, layout = 'tile' }: PartCardProps) {
  const { add, justAdded } = useCart()
  const added = justAdded === part.part_id
  const shown = part.fitment.slice(0, 3)
  const stock = part.availability?.total_available
  return (
    <article className={`pcard pcard--${layout}`}>
      <PartImage partNumber={part.part_number} category={part.category} name={part.name} />
      <div className="pcard__body">
        <div className="pcard__flags">
          <AvailabilityBadge availability={part.availability} />
          <StatusFlag status={part.availability?.part_status} />
        </div>
        <h3 className="pcard__name">
          <Link to={partPath(part.part_number)} className="pcard__link">
            {part.name}
          </Link>
        </h3>
        <p className="pcard__meta">
          <span className="mono">{part.part_number}</span>
          {part.category ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{part.subcategory ?? part.category}</span>
            </>
          ) : null}
        </p>
        {stock !== null && stock !== undefined ? <p className="pcard__stock">{stock} in stock across the network</p> : null}
        {shown.length > 0 ? (
          <ul className="pcard__fits" aria-label="Fits">
            {shown.map((m) => (
              <li key={m.model_code}>{m.model_code}</li>
            ))}
            {part.fitment.length > shown.length ? <li className="more">+{part.fitment.length - shown.length}</li> : null}
          </ul>
        ) : null}
      </div>
      <div className="pcard__foot">
        <p className="pcard__price">
          {part.price ? (
            <>
              <strong>{formatMoney(part.price)}</strong>
              <span>ex VAT{part.price.data_status === 'SYNTHETIC_DEMO' ? ' · demo price' : ''}</span>
            </>
          ) : (
            <span>Price not available</span>
          )}
        </p>
        {part.availability?.orderable === true ? (
          <button type="button" className={`pcard__add ${added ? 'is-added' : ''}`} onClick={() => add(part.part_id)} aria-label={`Add ${part.name} to cart`}>
            {added ? <Check size={18} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={18} strokeWidth={1.8} aria-hidden="true" />}
            <span>{added ? 'Added' : 'Add'}</span>
          </button>
        ) : (
          <span className="pcard__na">{part.availability?.orderable === false ? 'Not orderable online' : 'Ordering not configured'}</span>
        )}
      </div>
    </article>
  )
}
