import { CircleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { IntelligenceAction, QueryResponse, Suggestion } from '../../api/index'
import type { Subject } from '../../api/intelligenceTypes'
import { GraphExplorer } from './GraphExplorer'
import { evidenceGraph } from './graphModel'
import { EvidencePanel } from './EvidencePanel'
import { ProvenanceBadge, ProvenanceLine } from './provenance'
import { ResultCard } from './ResultCard'
import { AvailabilityTable } from './AvailabilityTable'
import type { SparkChart, SparkPresentation, SparkTable } from '../../api/spark'
import { RecordChart, RecordTable } from '../spark/AnswerBlocks'
import { AnswerText } from '../spark/AnswerText'

interface ResultViewProps {
  response: QueryResponse
  suggestions: Suggestion[] | null
  limit: number
  maxLimit: number
  onInvestigate: (partNumber: string) => void
  onAsk: (question: string) => void
  onSelect: (candidate: { kind: string; key: string }) => void
  onMore: () => void
  /** starts over: clears the question */
  onClear?: () => void
  showGraph?: boolean
  conversational?: boolean
  /** Spark's checked presentation; without it the classic card layout is used */
  format?: NonNullable<SparkPresentation['intelligence']>
  table?: SparkTable | null
  chart?: SparkChart | null
}

function ActionButton({
  action,
  onInvestigate,
  onAsk,
}: {
  action: IntelligenceAction
  onInvestigate: (pn: string) => void
  onAsk: (q: string) => void
}) {
  if (action.kind === 'ask' && action.question) {
    const question = action.question
    return (
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onAsk(question)}>
        {action.label}
      </button>
    )
  }
  if (action.kind === 'investigate' && action.href) {
    const part = new URL(action.href, 'http://x').searchParams.get('part')
    return (
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => part && onInvestigate(part)}
      >
        {action.label}
      </button>
    )
  }
  if (action.href) {
    return (
      <Link className="btn btn-secondary btn-sm" to={action.href}>
        {action.label}
      </Link>
    )
  }
  return null
}

/** Which part, machine, supplier... the answer is about: its identity in a few facts, before the results that belong to it */
function SubjectLine({
  subject,
  onInvestigate,
}: {
  subject: Subject
  onInvestigate: (pn: string) => void
}) {
  const kind = subject.kind.charAt(0) + subject.kind.slice(1).toLowerCase()
  return (
    <div className="pr__subject" aria-label={`About ${kind.toLowerCase()} ${subject.label}`}>
      <p className="pr__subject-id">
        <span className="pr__subject-kind">{kind}</span>
        {subject.kind === 'PART' ? (
          <button
            type="button"
            className="pr__subject-label"
            onClick={() => onInvestigate(subject.label)}
          >
            {subject.label}
          </button>
        ) : (
          <strong className="pr__subject-label">{subject.label}</strong>
        )}
        {subject.name ? <span className="pr__subject-name">{subject.name}</span> : null}
        <ProvenanceBadge value={subject.data_class} />
      </p>
      {subject.facts.length > 0 ? (
        <dl className="pr__subject-facts">
          {subject.facts.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  )
}

export function ResultView({
  response,
  suggestions,
  limit,
  maxLimit,
  onInvestigate,
  onAsk,
  onSelect,
  onMore,
  onClear,
  showGraph = false,
  conversational = false,
  format,
  table = null,
  chart = null,
}: ResultViewProps) {
  const { clarification } = response
  const canShowMore = response.results.length < response.total && limit < maxLimit
  const unsupported = response.intent === 'UNSUPPORTED'
  const [showRecords, setShowRecords] = useState(!showGraph)

  return (
    <section className="pr" aria-label={`Answer to: ${response.question}`} aria-live="polite">
      {!conversational ? (
        <div className="pr__understood">
          <span className="pr__understood-k">Understood as</span>
          <span className="pr__chip">{response.intent_label}</span>
          {response.entities.map((e) => (
            <span key={`${e.kind}-${e.key}`} className="pr__chip">
              <span>{e.kind.charAt(0) + e.kind.slice(1).toLowerCase()}</span>{' '}
              <strong>{e.label}</strong>
            </span>
          ))}
          {onClear ? (
            <button type="button" className="pr__clear" onClick={onClear}>
              Clear
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="pr__answer">
        {!conversational ? (
          <h2 className="pr__title">
            {unsupported ? 'Outside Parts Intelligence' : response.intent_label}
          </h2>
        ) : null}
        {response.subject &&
        !clarification &&
        // a text answer that already names its subject needs no identity block above it
        !(format === 'text' && response.answer.summary.includes(response.subject.label)) ? (
          <SubjectLine subject={response.subject} onInvestigate={onInvestigate} />
        ) : null}
        {conversational ? (
          // in the chat a part named in the answer is a link that opens it
          <div className="pr__summary">
            <AnswerText
              text={response.answer.summary}
              parts={[
                ...response.results.flatMap((item) => (item.part_number ? [item.part_number] : [])),
                ...response.entities.filter((e) => e.kind === 'PART').map((e) => e.label),
                ...(response.subject?.kind === 'PART' ? [response.subject.label] : []),
              ]}
            />
          </div>
        ) : (
          <p className="pr__summary">{response.answer.summary}</p>
        )}
        {response.answer.demo ? (
          <p className="pr__demo" role="note">
            <strong>Demo data.</strong> This answer includes synthetic demonstration data, not live
            enterprise data.
          </p>
        ) : null}
        {!conversational && response.answer.source === 'llm' ? (
          <p className="pr__source">Worded by the language model from the evidence below.</p>
        ) : null}
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

      {showGraph && response.results.length > 0 ? (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          aria-expanded={showRecords}
          onClick={() => setShowRecords((value) => !value)}
        >
          {showRecords ? 'Hide answer records' : 'Show answer records'}
        </button>
      ) : null}
      {response.results.length > 0 && showRecords && (format === 'text' || format === 'chart') ? (
        // the sentence (or the chart) carries the answer; the records stay one click away
        <>
          {format === 'chart' && chart ? <RecordChart chart={chart} /> : null}
          <details className="spark-records">
            <summary>
              Show{' '}
              {response.results.length === 1
                ? 'the record'
                : `the ${response.results.length} records`}
            </summary>
            {table ? (
              <RecordTable table={table} onOpenPart={onInvestigate} label="Answer records" />
            ) : (
              <ul className="pr__results">
                {response.results.map((item, i) => (
                  <li key={`${i}-${item.kind}-${item.key}`}>
                    <ResultCard item={item} onInvestigate={onInvestigate} />
                  </li>
                ))}
              </ul>
            )}
          </details>
        </>
      ) : null}
      {response.results.length > 0 && showRecords && format === 'table' && table ? (
        <>
          <RecordTable table={table} onOpenPart={onInvestigate} label="Answer records" />
          {canShowMore ? (
            <button type="button" className="btn btn-secondary pr__more" onClick={onMore}>
              Show more
            </button>
          ) : null}
        </>
      ) : null}
      {response.results.length > 0 &&
      showRecords &&
      format !== 'text' &&
      format !== 'chart' &&
      !(format === 'table' && table) ? (
        <>
          {!conversational ? (
            <div className="pr__count">
              <h3>
                {response.total} {response.total === 1 ? 'result' : 'results'}
                {response.results.length < response.total ? (
                  <span> · showing {response.results.length}</span>
                ) : null}
              </h3>
              <ProvenanceLine items={response.provenance} />
            </div>
          ) : null}
          {conversational &&
          response.results.every((item) =>
            ['dealer', 'supplier', 'warehouse'].includes(item.kind),
          ) ? (
            <AvailabilityTable items={response.results} />
          ) : (
            <ul className="pr__results">
              {response.results.map((item, i) => (
                <li key={`${i}-${item.kind}-${item.key}`}>
                  <ResultCard item={item} onInvestigate={onInvestigate} />
                </li>
              ))}
            </ul>
          )}
          {canShowMore ? (
            <button type="button" className="btn btn-secondary pr__more" onClick={onMore}>
              Show more
            </button>
          ) : null}
        </>
      ) : null}

      {response.actions.length > 0 ? (
        <div className="pr__actions">
          {response.actions.map((a) => (
            <ActionButton
              key={`${a.kind}-${a.label}`}
              action={a}
              onInvestigate={onInvestigate}
              onAsk={onAsk}
            />
          ))}
        </div>
      ) : null}

      {!clarification && response.evidence.length > (format === 'text' ? 1 : 0) ? (
        <details className="gx-answer" open={showGraph || undefined}>
          <summary>
            View graph · {response.evidence.length}{' '}
            {response.evidence.length === 1 ? 'connection' : 'connections'}
          </summary>
          <GraphExplorer
            key={response.question}
            view={evidenceGraph(response.evidence)}
            onOpen={onInvestigate}
            label="Answer relationships"
          />
        </details>
      ) : null}
      {!clarification && !conversational ? <EvidencePanel response={response} /> : null}
    </section>
  )
}
