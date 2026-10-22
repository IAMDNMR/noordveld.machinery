import type { Provenance } from '../../api/domainKnowledge'

const LABELS: Record<Provenance['kind'], string> = {
  verified_source: 'Verified source',
  derived: 'Derived, needs review',
  synthetic: 'Synthetic demo',
  user_provided: 'From the brief',
  assumption: 'Assumption',
}

export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  return (
    <span
      className={`dk-badge dk-badge--${provenance.kind}`}
      title={`${provenance.reference} · ${provenance.verification}`}
    >
      {LABELS[provenance.kind]}
    </span>
  )
}
