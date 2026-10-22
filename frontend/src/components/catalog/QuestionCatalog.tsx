import { useId, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import type { CatalogGroup } from '../../api/types'
import './catalog.css'

interface QuestionCatalogProps {
  groups: CatalogGroup[]
  /** runs the chosen question exactly as if it had been typed */
  onAsk: (question: string) => void
  title?: string
  align?: 'start' | 'center'
}

const ALL = 'All'

/** Example questions by category. Choosing one runs it at once through the page's own question flow. */
export function QuestionCatalog({
  groups,
  onAsk,
  title = 'Question catalog',
  align = 'start',
}: QuestionCatalogProps) {
  const [category, setCategory] = useState(ALL)
  const headingId = useId()
  const shown = category === ALL ? groups : groups.filter((g) => g.category === category)
  const total = groups.reduce((n, g) => n + g.questions.length, 0)
  return (
    <section className={`qc qc--${align}`} aria-labelledby={headingId}>
      <div className="qc__head">
        <h2 id={headingId} className="qc__title">
          {title}
        </h2>
        <span className="qc__count">{total} questions · choose one to run it</span>
      </div>
      <div className="qc__filters" role="group" aria-label="Question categories">
        {[ALL, ...groups.map((g) => g.category)].map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={category === c}
            className={category === c ? 'is-on' : ''}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>
      <div className="qc__groups">
        {shown.map((g) => (
          <div key={g.category} className="qc__group">
            <h3 className="qc__cat">{g.category}</h3>
            {g.note ? <p className="qc__note">{g.note}</p> : null}
            <ul className="qc__list" aria-label={`${g.category} questions`}>
              {g.questions.map((q) => (
                <li key={q}>
                  <button type="button" className="qc__q" onClick={() => onAsk(q)}>
                    <span>{q}</span>
                    <ArrowRight size={15} strokeWidth={2} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
