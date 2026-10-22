import { useState } from 'react'
import { CircleAlert, Scale } from 'lucide-react'
import type { StudioState } from '../../api/studio'

/** Decisions only the business can make. Each shows what it holds back; recording one prepares a reviewed proposal with its impact,
 * and only a project or process owner can apply it. Nothing is decided by the assistant. */
export function DecisionList({
  studio,
  act,
  busy,
  recent,
}: {
  studio: StudioState
  act: (actions: Record<string, unknown>[], note?: string) => void
  busy: boolean
  recent: ReadonlySet<string>
}) {
  const business = studio.definition.business
  const decisions = business.decisions.filter((item) => item.status === 'open')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const steps = studio.definition.workflow_definitions.flatMap((workflow) => workflow.states)
  const preview = (id: string) => {
    const text = answers[id]?.trim()
    if (!text) return
    act(
      [{ type: 'answer_decision', decision_id: id, answer: text }],
      'Here is what this decision changes. Review it in the proposal; a project or process owner applies it.',
    )
  }
  if (!decisions.length) return <p className="sw-muted">No open decisions.</p>
  return (
    <ul className="sw-decisions">
      {decisions.map((item) => {
        const affects = item.affects ?? []
        const rules = business.rules.filter((rule) => affects.includes(rule.id))
        const held = steps.filter(
          (step) =>
            affects.includes(step.id) || (step.rule_ids ?? []).some((id) => affects.includes(id)),
        )
        const unbound = rules.filter((rule) => !rule.execution)
        return (
          <li key={item.id} data-changed={recent.has(item.id) || undefined}>
            <div className="sw-decisions__q">
              <Scale size={16} aria-hidden="true" />
              <label htmlFor={`d-${item.id}`}>{item.question}</label>
            </div>
            {held.length || rules.length ? (
              <dl className="sw-decisions__impact">
                {held.length ? (
                  <div>
                    <dt>Holds back</dt>
                    <dd>{held.map((step) => step.label).join(' · ')}</dd>
                  </div>
                ) : null}
                {rules.length ? (
                  <div>
                    <dt>Rules waiting on it</dt>
                    <dd>{rules.map((rule) => rule.description).join(' · ')}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
            {unbound.length ? (
              <p className="sw-decisions__note">
                <CircleAlert size={13} aria-hidden="true" /> After the answer,{' '}
                {unbound.length === 1 ? 'this rule still needs' : 'these rules still need'}{' '}
                executable logic before the generated application will run the step.
              </p>
            ) : null}
            <div className="sw-decisions__answer">
              <input
                id={`d-${item.id}`}
                value={answers[item.id] ?? ''}
                onChange={(event) =>
                  setAnswers((current) => ({ ...current, [item.id]: event.target.value }))
                }
                placeholder="The business's answer, in its own words"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') preview(item.id)
                }}
                maxLength={1000}
              />
              <button
                type="button"
                className="sw-button"
                disabled={busy || !answers[item.id]?.trim()}
                onClick={() => preview(item.id)}
              >
                Preview impact
              </button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
