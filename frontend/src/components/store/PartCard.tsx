import { Check, ShoppingCart } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { PartSummary } from '../../api'
import { formatMoney } from '../../lib/format'
import { partPath } from '../../lib/storeQuery'
import { useCart } from '../../store/CartContext'
import { AvailabilityBadge, canOrder, StatusFlag } from './Badges'
import { PartImage } from './PartImage'

/** One catalogue part, as the wireframe's part card: picture, number, name, meta, price with availability, actions. */
export function PartCard({ part, machine = null }: { part: PartSummary; machine?: string | null }) {
  const { add, justAdded } = useCart()
  const added = justAdded === part.part_id
  const fits = part.fitment.slice(0, 3)
  return (
    <article className="part-card card">
      <Link to={partPath(part.part_number)} className="part-thumb" tabIndex={-1} aria-hidden="true">
        <PartImage partNumber={part.part_number} category={part.category} name={part.name} />
      </Link>
      <p className="part-number">{part.part_number}</p>
      <h3 className="part-name">
        <Link to={partPath(part.part_number)}>{part.name}</Link>
      </h3>
      <div className="part-meta">
        {part.category ? <span>{part.subcategory ? `${part.category} · ${part.subcategory}` : part.category}</span> : null}
        <span>{fits.length ? `Fits ${fits.map((f) => f.model_code).join(', ')}${part.fitment.length > fits.length ? ` +${part.fitment.length - fits.length}` : ''}` : 'No fitment recorded'}</span>
        <StatusFlag status={part.availability?.part_status} partNumber={part.part_number} />
      </div>
      <div className="part-foot">
        <span className="part-price">{part.price ? formatMoney(part.price) : <span className="muted small">Price not available</span>}</span>
        <AvailabilityBadge availability={part.availability} />
      </div>
      <div className="part-actions">
        <Link to={partPath(part.part_number)} className="btn btn-secondary btn-sm">
          View details
        </Link>
        {canOrder(part.availability?.part_status, part.availability?.orderable) ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => add(part.part_id, 1, machine)} aria-label={`Add ${part.name} to cart`}>
            {added ? <Check size={15} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={15} strokeWidth={1.8} aria-hidden="true" />}
            {added ? 'Added' : 'Add'}
          </button>
        ) : (
          <span className="part-na">{part.availability?.orderable === false ? 'Not orderable online' : 'Ordering not configured'}</span>
        )}
      </div>
    </article>
  )
}
