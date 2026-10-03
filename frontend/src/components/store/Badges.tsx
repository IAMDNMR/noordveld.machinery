import { CircleAlert, ScanSearch } from 'lucide-react'
import { availabilityMeta, statusMeta, type StorePart } from '../../data/store'

export function AvailabilityBadge({ part }: { part: StorePart }) {
  const meta = availabilityMeta[part.availability]
  return (
    <span className={`sbadge sbadge--${meta.tone}`}>
      <i aria-hidden="true" />
      {meta.label}
    </span>
  )
}

/** Only shown when the catalogue entry needs the customer's attention; verified parts stay quiet. */
export function StatusFlag({ part }: { part: StorePart }) {
  if (part.status === 'VERIFIED') return null
  const Icon = part.status === 'IDENTIFICATION_REQUIRED' ? ScanSearch : CircleAlert
  return (
    <span className="sflag">
      <Icon size={14} strokeWidth={1.8} aria-hidden="true" />
      {statusMeta[part.status].short}
    </span>
  )
}
