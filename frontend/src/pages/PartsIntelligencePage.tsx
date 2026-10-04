import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { askQuestion, getSuggestions, type PartTab } from '../api'
import { ErrorNotice, ThinkingNotice } from '../components/intelligence/Notices'
import { PartWorkspace, TABS } from '../components/intelligence/PartWorkspace'
import { PiHero } from '../components/intelligence/PiHero'
import { QuestionInput } from '../components/intelligence/QuestionInput'
import { ResultView } from '../components/intelligence/ResultView'
import { useApi } from '../hooks/useApi'
import { labelQuestion, rememberQuestion, useRecentQuestions } from '../store/recentQuestions'
import { usePageMeta } from '../hooks/usePageMeta'
import '../styles/wf.css'
import '../components/intelligence/intelligence.css'

export const INTELLIGENCE_ROUTE = '/parts-intelligence'
const STEP = 12
const MAX = 36

const parseTab = (value: string | null): PartTab => (TABS.find((t) => t.id === value)?.id ?? 'overview')

export default function PartsIntelligencePage() {
  usePageMeta({
    title: 'Parts Intelligence',
    description: 'Understand the relationship between machines, parts and supply through the Noordveld knowledge graph. Every answer is traced to graph evidence and labelled with where the data comes from.',
    path: INTELLIGENCE_ROUTE,
  })

  const [params, setParams] = useSearchParams()
  const question = params.get('q') ?? ''
  const part = params.get('part')
  const tab = parseTab(params.get('tab'))
  const suggestions = useApi((signal) => getSuggestions(signal), 'suggestions')
  const recent = useRecentQuestions()

  useEffect(() => {
    if (question) rememberQuestion(question)
  }, [question])

  const update = useCallback(
    (next: Record<string, string | null>, replace = false) => {
      const p = new URLSearchParams(params)
      for (const [k, v] of Object.entries(next)) {
        if (v === null) p.delete(k)
        else p.set(k, v)
      }
      setParams(p, { replace })
    },
    [params, setParams],
  )
  const ask = (q: string) => update({ q, part: null, tab: null })
  const investigate = (pn: string) => update({ part: pn, tab: 'overview' })
  const closePart = useCallback(() => update({ part: null, tab: null }), [update])

  // a part under investigation is its own document; the question it came from stays in the URL for the way back
  if (part)
    return (
      <div className="wf pi-page">
        <PartWorkspace key={part} partKey={part} tab={tab} backLabel={question ? 'Back to the investigation' : 'Parts Intelligence'} onTab={(t) => update({ tab: t }, true)} onOpenPart={investigate} onClose={closePart} />
      </div>
    )

  return (
    <div className="wf pi-page">
      <section className={`pih ${question ? 'pih--answering' : ''}`} aria-labelledby="pi-title">
        <PiHero>
          <QuestionInput value={question} busy={false} onAsk={ask} suggestions={suggestions.data} recent={recent} />
          {suggestions.error ? <p className="sq__note">Suggested questions are unavailable right now. You can still type a question above.</p> : null}
        </PiHero>

        <div className="wf-container">
          {question ? (
            <div className="pih__answer">
              <Answer key={question} question={question} suggestions={suggestions.data} onAsk={ask} onInvestigate={investigate} onClear={() => setParams(new URLSearchParams())} />
            </div>
          ) : null}

          <p className="pi__note">Demonstration knowledge graph. Source-derived data comes from the supplied Noordveld catalogue; stock, supplier, dealer, assembly and compliance links are synthetic demo data and are labelled as such.</p>
        </div>
      </section>
    </div>
  )
}

interface AnswerProps {
  question: string
  suggestions: Parameters<typeof ResultView>[0]['suggestions']
  onAsk: (q: string) => void
  onInvestigate: (pn: string) => void
  onClear: () => void
}

/** Asks one question. Remounted per question, so a chosen candidate or "show more" never leaks into the next one. */
function Answer({ question, suggestions, onAsk, onInvestigate, onClear }: AnswerProps) {
  const [selected, setSelected] = useState<{ kind: string; key: string }[]>([])
  const [limit, setLimit] = useState(STEP)
  const state = useApi((signal) => askQuestion(question, selected, limit, signal), `${question}|${JSON.stringify(selected)}|${limit}`)

  const intent = state.data?.intent
  const label = state.data?.intent_label
  useEffect(() => {
    if (intent && intent !== 'UNSUPPORTED' && label) labelQuestion(question, label)
  }, [question, intent, label])

  if (state.error && !state.data) return <ErrorNotice error={state.error} onRetry={state.reload} />
  if (!state.data) return <ThinkingNotice />
  return (
    <div aria-busy={state.loading}>
      <ResultView
        response={state.data}
        suggestions={suggestions}
        limit={limit}
        maxLimit={MAX}
        onInvestigate={onInvestigate}
        onAsk={onAsk}
        onClear={onClear}
        onSelect={(c) => setSelected((cur) => [...cur.filter((x) => x.kind !== c.kind), c])}
        onMore={() => setLimit((n) => Math.min(MAX, n + STEP))}
      />
      {state.error ? <ErrorNotice error={state.error} onRetry={state.reload} /> : null}
    </div>
  )
}
