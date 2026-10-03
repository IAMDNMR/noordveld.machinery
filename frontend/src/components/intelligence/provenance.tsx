import type { DataClass, ProvenanceSummary } from '../../api'

/** How each data class reads in the interface. The classes themselves come from the API. */
export const DATA_CLASS_LABEL: Record<DataClass, string> = {
  REAL: 'Real',
  SOURCE_DERIVED: 'Source-derived',
  DERIVED: 'Derived',
  SYNTHETIC_DEMO: 'Synthetic demo',
  USER_PROVIDED: 'User-provided',
  TEST_DATA: 'Test data',
  INTERNAL_REFERENCE_ONLY: 'Internal reference only',
  UNKNOWN: 'Unclassified',
  NOT_CONNECTED: 'Not connected',
}

export const DATA_CLASS_MEANING: Record<DataClass, string> = {
  REAL: 'Confirmed live enterprise data.',
  SOURCE_DERIVED: 'Taken from the supplied Noordveld catalogue.',
  DERIVED: 'Computed from source data.',
  SYNTHETIC_DEMO: 'Demonstration data created for this project. Not enterprise truth.',
  USER_PROVIDED: 'Supplied by a user.',
  TEST_DATA: 'Test data.',
  INTERNAL_REFERENCE_ONLY: 'For internal reference only.',
  UNKNOWN: 'The graph does not state where this came from.',
  NOT_CONNECTED: 'No such data is connected to the graph.',
}

/** A different mark per class, so status never depends on colour alone. */
const MARK: Record<DataClass, string> = {
  REAL: '●',
  SOURCE_DERIVED: '●',
  DERIVED: '◐',
  SYNTHETIC_DEMO: '◇',
  USER_PROVIDED: '▪',
  TEST_DATA: '◇',
  INTERNAL_REFERENCE_ONLY: '▫',
  UNKNOWN: '○',
  NOT_CONNECTED: '⊘',
}

export function ProvenanceBadge({ value }: { value: DataClass }) {
  return (
    <span className={`prov prov--${value.toLowerCase().replace(/_/g, '-')}`} title={DATA_CLASS_MEANING[value]}>
      <span aria-hidden="true">{MARK[value]}</span> {DATA_CLASS_LABEL[value]}
    </span>
  )
}

export function ProvenanceLine({ items }: { items: ProvenanceSummary[] }) {
  if (items.length === 0) return null
  return (
    <p className="prov-line">
      <span className="prov-line__label">Data</span>
      {items.map((p) => (
        <span key={p.data_class} className="prov-line__item">
          <ProvenanceBadge value={p.data_class} /> <span className="prov-line__n">{p.count}</span>
        </span>
      ))}
    </p>
  )
}

export const NOT_AVAILABLE = 'Not available'
