import { CircleAlert } from 'lucide-react'
import type { Availability } from '../../api'
import { availabilityTone, humanize } from '../../lib/format'

export function AvailabilityBadge({ availability }: { availability: Availability | null }) {
  if (!availability?.state) return <span className="sbadge sbadge--none">Availability not configured</span>
  return (
    <span className={`sbadge sbadge--${availabilityTone(availability.state)}`}>
      <i aria-hidden="true" />
      {humanize(availability.state)}
    </span>
  )
}

/** Shown only when the catalogue marks the part as needing attention; the status text is the graph's own. */
export function StatusFlag({ status }: { status: string | null | undefined }) {
  if (!status || status === 'VERIFIED') return null
  return (
    <span className="sflag">
      <CircleAlert size={14} strokeWidth={1.8} aria-hidden="true" />
      {humanize(status)}
    </span>
  )
}

/** Marks values that come from the demonstration layer rather than a source document. */
export function DemoTag({ status }: { status: string | null | undefined }) {
  if (status !== 'SYNTHETIC_DEMO') return null
  return <span className="sflag sflag--demo">Demo data</span>
}
