import { Check, ShoppingCart } from 'lucide-react'
import { Link } from 'react-router-dom'
import { eur, partPath, stockLine, type StorePart } from '../../data/store'
import { useCart } from '../../store/CartContext'
import { AvailabilityBadge, StatusFlag } from './Badges'
import { PartVisual } from './PartVisual'

interface PartCardProps {
  part: StorePart
  /** `row` is the list layout of the catalogue */
  layout?: 'tile' | 'row'
}

export function PartCard({ part, layout = 'tile' }: PartCardProps) {
  const { add, justAdded } = useCart()
  const added = justAdded === part.id
  const shown = part.fits.slice(0, 3)
  return (
    <article className={`pcard pcard--${layout}`}>
      <PartVisual part={part} />
      <div className="pcard__body">
        <div className="pcard__flags">
          <AvailabilityBadge part={part} />
          <StatusFlag part={part} />
        </div>
        <h3 className="pcard__name">
          <Link to={partPath(part)} className="pcard__link">
            {part.name}
          </Link>
        </h3>
        <p className="pcard__meta">
          <span className="mono">{part.no}</span>
          <span aria-hidden="true">·</span>
          <span>{part.subcategory || part.category}</span>
        </p>
        <p className="pcard__stock">{stockLine(part)}</p>
        <ul className="pcard__fits" aria-label="Fits">
          {shown.map((m) => (
            <li key={m}>{m}</li>
          ))}
          {part.fits.length > shown.length ? <li className="more">+{part.fits.length - shown.length}</li> : null}
        </ul>
      </div>
      <div className="pcard__foot">
        <p className="pcard__price">
          <strong>{eur(part.price)}</strong>
          <span>ex VAT</span>
        </p>
        {part.orderable ? (
          <button type="button" className={`pcard__add ${added ? 'is-added' : ''}`} onClick={() => add(part)} aria-label={`Add ${part.name} to cart`}>
            {added ? <Check size={18} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={18} strokeWidth={1.8} aria-hidden="true" />}
            <span>{added ? 'Added' : 'Add'}</span>
          </button>
        ) : (
          <span className="pcard__na">Confirm to order</span>
        )}
      </div>
    </article>
  )
}
