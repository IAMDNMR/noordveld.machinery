import { useId, useMemo, useState, type FormEvent } from 'react'
import type { Suggestion } from '../../api'
import type { RecentQuestion } from '../../store/recentQuestions'

/** Question groups, in the order the topic list shows them. The questions inside are built by the API from the graph itself. */
export const CATEGORIES = ['Part Discovery', 'Machine & Fitment', 'Part Relationships', 'Supplier Intelligence', 'Dealer Intelligence', 'Assembly Intelligence', 'Geographic Intelligence', 'Compliance', 'Inventory', 'Service', 'Orders', 'Network', 'Provenance'] as const

interface QuestionInputProps {
  /** The question currently being answered (from the URL); the box resets when it changes. */
  value: string
  busy: boolean
  onAsk: (question: string) => void
  /** starter questions from the API, grouped by topic under the field */
  suggestions?: Suggestion[] | null
  /** this visitor's recent questions */
  recent?: RecentQuestion[]
}

export function QuestionInput({ value, busy, onAsk, suggestions = null, recent = [] }: QuestionInputProps) {
  // Remount on a new submitted question so the box always shows what was asked (back button, suggestion click)
  return <Box key={value} initial={value} busy={busy} onAsk={onAsk} suggestions={suggestions} recent={recent} />
}

function Box({ initial, busy, onAsk, suggestions, recent }: { initial: string; busy: boolean; onAsk: (q: string) => void; suggestions: Suggestion[] | null; recent: RecentQuestion[] }) {
  const [text, setText] = useState(initial)
  const topics = useMemo(() => CATEGORIES.filter((c) => (suggestions ?? []).some((s) => s.category === c)), [suggestions])
  const [topic, setTopic] = useState('')
  const current = topic || topics[0] || ''
  const chips = (suggestions ?? []).filter((s) => s.category === current).slice(0, 4)
  const id = useId()
  const topicId = useId()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim().length >= 2) onAsk(text.trim())
  }
  return (
    <form className="pq" role="search" onSubmit={submit}>
      <div className="pq__row">
        <label className="sr-only" htmlFor={id}>
          Ask Parts Intelligence a question
        </label>
        <input
          id={id}
          className="pq__input"
          type="text"
          maxLength={300}
          value={text}
          autoComplete="off"
          placeholder={chips[0] ? `e.g. ${chips[0].question}` : 'Ask about a part, machine, fitment, supplier or relationship'}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="pq__ask" disabled={busy || text.trim().length < 2}>
          {busy ? 'Asking…' : 'Ask'}
        </button>
      </div>

      {topics.length > 0 ? (
        <div className="pq__topics">
          <label className="pq__k" htmlFor={topicId}>
            Topic
          </label>
          <select id={topicId} value={current} onChange={(e) => setTopic(e.target.value)}>
            {topics.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <ul className="pq__chips" aria-label={`${current} questions`}>
            {chips.map((s) => (
              <li key={s.question}>
                <button type="button" onClick={() => onAsk(s.question)}>
                  {s.question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {recent.length > 0 ? (
        <div className="pq__recent">
          <span className="pq__k">Recent</span>
          <ul>
            {recent.slice(0, 4).map((r) => (
              <li key={r.question}>
                <button type="button" onClick={() => onAsk(r.question)}>
                  {r.question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  )
}
