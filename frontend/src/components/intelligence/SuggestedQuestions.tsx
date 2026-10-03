import { useMemo, useState } from 'react'
import type { Suggestion } from '../../api'

/** Question groups shown in the interface. The questions inside are built by the API from the graph itself. */
const CATEGORIES = [
  'Part Discovery',
  'Machine & Fitment',
  'Part Relationships',
  'Supplier Intelligence',
  'Dealer Intelligence',
  'Assembly Intelligence',
  'Geographic Intelligence',
  'Compliance',
  'Inventory',
  'Network',
  'Provenance',
] as const

/** A short, varied starter set: one from each of the first categories that matter most. */
const FEATURED = ['Machine & Fitment', 'Part Relationships', 'Supplier Intelligence', 'Assembly Intelligence', 'Geographic Intelligence', 'Network', 'Provenance']

interface Props {
  suggestions: Suggestion[] | null
  failed: boolean
  onAsk: (question: string) => void
}

export function SuggestedQuestions({ suggestions, failed, onAsk }: Props) {
  const [category, setCategory] = useState<string>('')
  const featured = useMemo(() => (suggestions ?? []).filter((s, i, all) => FEATURED.includes(s.category) && all.findIndex((x) => x.category === s.category) === i), [suggestions])
  const available = useMemo(() => CATEGORIES.filter((c) => (suggestions ?? []).some((s) => s.category === c)), [suggestions])
  const shown = category ? (suggestions ?? []).filter((s) => s.category === category) : featured

  if (failed) return <p className="sq__note">Suggested questions are unavailable right now. You can still type a question above.</p>
  if (!suggestions) return null
  return (
    <section className="sq" aria-labelledby="sq-title">
      <h2 id="sq-title" className="sq__title">
        {category || 'Try asking'}
      </h2>
      <ul className="sq__cats" aria-label="Question categories">
        <li>
          <button type="button" aria-pressed={category === ''} onClick={() => setCategory('')}>
            Suggested
          </button>
        </li>
        {available.map((c) => (
          <li key={c}>
            <button type="button" aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          </li>
        ))}
      </ul>
      <ul className="sq__list">
        {shown.map((s) => (
          <li key={s.question}>
            <button type="button" onClick={() => onAsk(s.question)}>
              {s.question}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
