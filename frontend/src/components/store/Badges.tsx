import { CircleAlert } from 'lucide-react'
import type { Availability } from '../../api'
import { availabilityTone, humanize } from '../../lib/format'
import { statusLabel } from '../../lib/partStatus'
import { useIdentification } from '../../store/identification'

export function AvailabilityBadge({ availability }: { availability: Availability | null }) {
  if (!availability?.state) return <span className="tag tag-plain">Availability not configured</span>
  const tone = availabilityTone(availability.state)
  return (
    <span className={`tag ${tone === 'ok' ? 'tag-good' : tone === 'warn' ? 'tag-warn' : 'tag-bad'}`}>
      <i className="tag-dot" aria-hidden="true" />
      {humanize(availability.state)}
    </span>
  )
}

/**
 * Shown only when the catalogue marks the part as not verified. An unverified part the user has asked about reads
 * "Identification requested" here exactly as it does in Parts Intelligence.
 */
export function StatusFlag({ status, partNumber }: { status: string | null | undefined; partNumber: string }) {
  const { record } = useIdentification(partNumber)
  if (status === 'VERIFIED') return null
  const requested = status !== 'IDENTIFICATION_REQUIRED' && status !== 'AMBIGUOUS' && record?.requestedAt
  return (
    <span className="tag tag-warn">
      <CircleAlert size={13} strokeWidth={2} aria-hidden="true" />
      {requested ? 'Identification requested' : statusLabel(status)}
    </span>
  )
}

/** The one ordering rule, mirrored from the server: only a verified part marked orderable can go in the cart. */
export const canOrder = (status: string | null | undefined, orderable: boolean | null | undefined): boolean => status === 'VERIFIED' && orderable === true

/** Marks values that come from the demonstration layer rather than a source document. */
export function DemoTag({ status }: { status: string | null | undefined }) {
  if (status !== 'SYNTHETIC_DEMO') return null
  return <span className="badge badge-data">Demo data</span>
}
