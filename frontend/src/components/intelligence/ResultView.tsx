import { CircleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { IntelligenceAction, QueryResponse, Suggestion } from '../../api'
import { EvidencePanel } from './EvidencePanel'
import { ProvenanceLine } from './provenance'
import { ResultCard } from './ResultCard'

interface ResultViewProps {
  response: QueryResponse
  suggestions: Suggestion[] | null
  limit: number
  maxLimit: number
  onInvestigate: (partNumber: string) => void
  onAsk: (question: string) => void
  onSelect: (candidate: { kind: string; key: string }) => void
  onMore: () => void
}

function ActionButton({ action, onInvestigate, onAsk }: { action: IntelligenceAction; onInvestigate: (pn: string) => void; onAsk: (q: string) => void }) {
  if (action.kind === 'ask' && action.question) {
    const question = action.question
    return (
      <button type="button" className="button button--secondary" onClick={() => onAsk(question)}>
        {action.label}
      </button>
    )
  }
  if (action.kind === 'investigate' && action.href) {
    const part = new URL(action.href, 'http://x').searchParams.get('part')
    return (
      <button type="button" className="button button--secondary" onClick={() => part && onInvestigate(part)}>
        {action.label}
      </button>
    )
  }
  if (action.href) {
    return (
      <Link className="button button--secondary" to={action.href}>
        {action.label}
      </Link>
    )
  }
  return null
}

export function ResultView({ response, suggestions, limit, maxLimit, onInvestigate, onAsk, onSelect, onMore }: ResultViewProps) {
  const { clarification } = response
  const canShowMore = response.results.length < response.total && limit < maxLimit
  const unsupported = response.intent === 'UNSUPPORTED'

  return (
    <section className="pr" aria-labelledby="pr-question" aria-live="polite">
      <p className="pr__label">Question</p>
      <h2 id="pr-question" className="pr__question">
        {response.question}
      </h2>
      <p className="pr__understood">
        <span>{response.intent_label}</span>
        {response.entities.map((e) => (
          <span key={`${e.kind}-${e.key}`}>
            {e.kind.charAt(0) + e.kind.slice(1).toLowerCase()}: <strong>{e.label}</strong>
          </span>
        ))}
      </p>

      <div className="pr__answer">
        <p className="pr__label">Answer</p>
        <p className="pr__summary">{response.answer.summary}</p>
        {response.answer.source === 'gemini' ? <p className="pr__source">Worded by the language model from the evidence below.</p> : null}
      </div>

      {response.warnings.map((w) => (
        <p key={w} className="pr__warning" role="note">
          <CircleAlert size={18} strokeWidth={1.7} aria-hidden="true" />
          {w}
        </p>
      ))}

      {clarification ? (
        <div className="pr__clarify">
          {clarification.candidates.length > 0 ? (
            <ul className="pr__candidates" aria-label="Choose one">
              {clarification.candidates.map((c) => (
                <li key={`${c.kind}-${c.key}`}>
                  <button type="button" onClick={() => onSelect({ kind: c.kind, key: c.key })}>
                    <strong>{c.label}</strong>
                    {c.detail ? <span>{c.detail}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {unsupported && suggestions ? (
            <ul className="pr__try" aria-label="Questions you can ask">
              {suggestions.slice(0, 5).map((s) => (
                <li key={s.question}>
                  <button type="button" onClick={() => onAsk(s.question)}>
                    {s.question}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {response.results.length > 0 ? (
        <>
          <div className="pr__count">
            <h3>
              {response.total === 1 ? '1 result' : `${response.total} results`}
              {response.results.length < response.total ? <span> · showing {response.results.length}</span> : null}
            </h3>
            <ProvenanceLine items={response.provenance} />
          </div>
          <ul className="pr__results">
            {response.results.map((item, i) => (
              <li key={`${i}-${item.kind}-${item.key}`}>
                <ResultCard item={item} onInvestigate={onInvestigate} />
              </li>
            ))}
          </ul>
          {canShowMore ? (
            <button type="button" className="button button--secondary pr__more" onClick={onMore}>
              Show more
            </button>
          ) : null}
        </>
      ) : null}

      {response.actions.length > 0 ? (
        <div className="pr__actions">
          {response.actions.map((a) => (
            <ActionButton key={`${a.kind}-${a.label}`} action={a} onInvestigate={onInvestigate} onAsk={onAsk} />
          ))}
        </div>
      ) : null}

      {!clarification ? <EvidencePanel response={response} /> : null}
    </section>
  )
}
