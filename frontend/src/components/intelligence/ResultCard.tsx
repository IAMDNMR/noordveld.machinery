import type { ResultItem } from '../../api'
import { humanize } from '../../lib/format'
import { NOT_AVAILABLE, ProvenanceBadge } from './provenance'

interface ResultCardProps {
  item: ResultItem
  onInvestigate: (partNumber: string) => void
}

/**
 * One result, laid out so it can be read in seconds: the key first and large, the name under it, then each fact on its own
 * labelled line, then where the data comes from. Never a single sentence of run-together values.
 */
export function ResultCard({ item, onInvestigate }: ResultCardProps) {
  const isPart = item.part_number !== null
  return (
    <article className={`rcard rcard--${item.kind}`}>
      <header className="rcard__head">
        {isPart ? (
          <h3 className="rcard__key mono">
            <button type="button" className="rcard__open" onClick={() => onInvestigate(item.part_number!)} aria-label={`Open ${item.title} in Part Intelligence`}>
              {item.title}
            </button>
          </h3>
        ) : (
          <h3 className="rcard__key">{item.title}</h3>
        )}
        {item.subtitle ? <p className="rcard__name">{item.subtitle}</p> : null}
        {item.relationship ? <p className="rcard__rel">{humanize(item.relationship)}</p> : null}
      </header>

      {item.facts.length > 0 ? (
        <dl className="rcard__facts">
          {item.facts.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd className={f.value ? undefined : 'is-missing'}>{f.value ?? NOT_AVAILABLE}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {item.groups.map((g) => (
        <div key={g.label} className="rcard__group">
          <h4>{g.label}</h4>
          <ul>
            {g.values.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </div>
      ))}

      <footer className="rcard__foot">
        <ProvenanceBadge value={item.data_class} />
        {isPart ? (
          <button type="button" className="rcard__action" onClick={() => onInvestigate(item.part_number!)}>
            View Part Intelligence
          </button>
        ) : null}
      </footer>
    </article>
  )
}
