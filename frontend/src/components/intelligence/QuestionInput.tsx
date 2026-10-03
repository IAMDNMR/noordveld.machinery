import { ArrowRight, X } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'

interface QuestionInputProps {
  /** The question currently being answered (from the URL); the box resets when it changes. */
  value: string
  busy: boolean
  onAsk: (question: string) => void
  onClear: () => void
}

export function QuestionInput({ value, busy, onAsk, onClear }: QuestionInputProps) {
  // Remount on a new submitted question so the box always shows what was asked (back button, suggestion click)
  return <Box key={value} initial={value} busy={busy} onAsk={onAsk} onClear={onClear} />
}

function Box({ initial, busy, onAsk, onClear }: { initial: string; busy: boolean; onAsk: (q: string) => void; onClear: () => void }) {
  const [text, setText] = useState(initial)
  const id = useId()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim().length >= 2) onAsk(text.trim())
  }
  return (
    <form className="pq" role="search" onSubmit={submit}>
      <label className="sr-only" htmlFor={id}>
        Ask Parts Intelligence a question
      </label>
      <textarea
        id={id}
        className="pq__input"
        rows={2}
        maxLength={300}
        value={text}
        placeholder="Ask about a part, machine, fitment, supplier or relationship..."
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            e.currentTarget.form?.requestSubmit()
          }
        }}
      />
      <div className="pq__bar">
        {text || initial ? (
          <button
            type="button"
            className="pq__clear"
            onClick={() => {
              setText('')
              if (initial) onClear()
            }}
          >
            <X size={16} strokeWidth={2} aria-hidden="true" /> Clear
          </button>
        ) : (
          <span className="pq__hint">Press Enter to ask</span>
        )}
        <button type="submit" className="button button--primary pq__ask" disabled={busy || text.trim().length < 2}>
          {busy ? 'Asking…' : 'Ask'}
          <ArrowRight size={18} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </form>
  )
}
