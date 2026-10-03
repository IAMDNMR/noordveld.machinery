import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { askQuestion, getSuggestions, type PartTab } from '../api'
import { ErrorNotice, ThinkingNotice } from '../components/intelligence/Notices'
import { PartWorkspace, TABS } from '../components/intelligence/PartWorkspace'
import { QuestionInput } from '../components/intelligence/QuestionInput'
import { ResultView } from '../components/intelligence/ResultView'
import { SuggestedQuestions } from '../components/intelligence/SuggestedQuestions'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import '../components/intelligence/intelligence.css'

export const INTELLIGENCE_ROUTE = '/parts-intelligence'
const STEP = 12
const MAX = 36

const parseTab = (value: string | null): PartTab => (TABS.find((t) => t.id === value)?.id ?? 'overview')

export default function PartsIntelligencePage() {
  usePageMeta({
    title: 'Parts Intelligence',
    description: 'Understand parts, machines, relationships and supply context through the Noordveld knowledge graph. Every answer is traced to graph evidence and labelled with where the data comes from.',
    path: INTELLIGENCE_ROUTE,
  })

  const [params, setParams] = useSearchParams()
  const question = params.get('q') ?? ''
  const part = params.get('part')
  const tab = parseTab(params.get('tab'))
  const suggestions = useApi((signal) => getSuggestions(signal), 'suggestions')

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

  return (
    <>
      <section className="pi container" aria-labelledby="pi-title">
        <header className="pi__head">
          <p className="pi__eyebrow">Knowledge graph</p>
          <h1 id="pi-title">Parts Intelligence</h1>
          <p className="pi__lead">Understand parts, machines, relationships and supply context through the Noordveld knowledge graph.</p>
        </header>

        <QuestionInput value={question} busy={false} onAsk={ask} onClear={() => setParams(new URLSearchParams())} />

        {question ? (
          <Answer key={question} question={question} suggestions={suggestions.data} onAsk={ask} onInvestigate={investigate} />
        ) : (
          <SuggestedQuestions suggestions={suggestions.data} failed={Boolean(suggestions.error)} onAsk={ask} />
        )}

        <p className="pi__note">Demonstration knowledge graph. Source-derived data comes from the supplied Noordveld catalogue; stock, supplier, dealer, assembly and compliance links are synthetic demo data and are labelled as such.</p>
      </section>

      {part ? <PartWorkspace key={part} partKey={part} tab={tab} onTab={(t) => update({ tab: t }, true)} onOpenPart={investigate} onClose={closePart} /> : null}
    </>
  )
}

interface AnswerProps {
  question: string
  suggestions: Parameters<typeof ResultView>[0]['suggestions']
  onAsk: (q: string) => void
  onInvestigate: (pn: string) => void
}

/** Asks one question. Remounted per question, so a chosen candidate or "show more" never leaks into the next one. */
function Answer({ question, suggestions, onAsk, onInvestigate }: AnswerProps) {
  const [selected, setSelected] = useState<{ kind: string; key: string }[]>([])
  const [limit, setLimit] = useState(STEP)
  const state = useApi((signal) => askQuestion(question, selected, limit, signal), `${question}|${JSON.stringify(selected)}|${limit}`)

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
        onSelect={(c) => setSelected((cur) => [...cur.filter((x) => x.kind !== c.kind), c])}
        onMore={() => setLimit((n) => Math.min(MAX, n + STEP))}
      />
      {state.error ? <ErrorNotice error={state.error} onRetry={state.reload} /> : null}
    </div>
  )
}
