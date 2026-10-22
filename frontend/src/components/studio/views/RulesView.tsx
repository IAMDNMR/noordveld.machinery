import { Scale } from 'lucide-react'
import { useState } from 'react'
import { Empty } from '../bits'
import type { ViewProps } from './types'

const TYPE_LABEL = {
  validation: 'Validation',
  decision: 'Decision',
  calculation: 'Calculation',
  policy: 'Policy',
} as const

// Outcomes are stored as codes (RAISE_EXC_PACKING_QUANTITY_MISMATCH); people read them as words.
const outcomeText = (outcome: string) => {
  const words = outcome.replaceAll('_', ' ').toLowerCase().replace(/\bexc\b/g, 'exception')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Business rules and what follows from them: the condition, the outcomes it can produce, where it is applied, and what happens when something goes wrong. */
export function RulesView({ studio, recent, ask, go, act, busy, access }: ViewProps) {
  const [confirming, setConfirming] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const { definition } = studio
  const business = definition.business
  const steps = definition.workflow_definitions.flatMap((workflow) =>
    workflow.states.map((state) => ({ workflow, state })),
  )
  const appliedBy = (ruleId: string) =>
    steps.filter(
      ({ state, workflow }) =>
        (state.rule_ids ?? []).includes(ruleId) ||
        workflow.transitions.some(
          (edge) => edge.source === state.id && edge.condition.field === ruleId,
        ),
    )
  const handledBy = (id: string) =>
    steps.filter(({ state }) => (state.exception_ids ?? []).includes(id))
  const assumptions = business.rules.filter((rule) => rule.status === 'assumption').length

  if (!business.rules.length && !business.exceptions.length) {
    return (
      <Empty icon={<Scale size={28} />} title="No rules or exceptions yet">
        Rules appear as you describe how the business decides things, and exceptions as you say what
        can go wrong. Try “a shipment over 20 tonnes needs a heavy vehicle”.
      </Empty>
    )
  }
  return (
    <div className="sw-view">
      <section className="sw-card" aria-label="Business rules">
        <div className="sw-card__head">
          <h3>
            Business rules <span className="sw-count">{business.rules.length}</span>
          </h3>
          <button type="button" className="sw-button" onClick={() => ask('Add a rule: ')}>
            Add a rule
          </button>
        </div>
        {assumptions ? (
          <p className="sw-callout-inline">
            {assumptions} rules need review. Confirm only policies you have checked against a real source.
          </p>
        ) : null}
        <ul className="sw-rules">
          {business.rules.map((rule) => {
            const places = appliedBy(rule.id)
            return (
              <li key={rule.id} data-changed={recent.has(rule.id) || undefined}>
                <div className="sw-rules__head">
                  <span className="sw-tag">{TYPE_LABEL[rule.type ?? 'policy']}</span>
                  <span className={`sw-badge sw-badge--${rule.status}`}>
                    {rule.status === 'confirmed'
                      ? 'Confirmed'
                      : rule.origin
                        ? 'Blueprint default'
                        : 'Needs confirmation'}
                  </span>
                  {!rule.execution ? (
                    <span
                      className="sw-badge sw-badge--assumption"
                      title="The application cannot check this rule yet, so the steps that use it stay unavailable."
                    >
                      Not enforced yet
                    </span>
                  ) : null}
                </div>
                <p>{rule.description}</p>
                {rule.condition ? (
                  <p className="sw-muted">
                    <strong>When:</strong> {rule.condition}
                  </p>
                ) : null}
                {rule.outcomes?.length ? (
                  <p className="sw-outcomes">
                    <strong>Then:</strong>{' '}
                    {rule.outcomes.map((outcome) => (
                      <span key={outcome}>{outcomeText(outcome)}</span>
                    ))}
                  </p>
                ) : null}
                <details className="sw-muted">
                  <summary>Source and process usage</summary>
                  <small>
                    Source: {rule.source.reference}
                    {places.length
                      ? ` · applied at ${places
                          .map(({ state }) => state.label)
                          .slice(0, 3)
                          .join(', ')}${places.length > 3 ? ` and ${places.length - 3} more` : ''}`
                      : ' · not applied by any step yet'}
                  </small>
                </details>
                <div>
                  {rule.status === 'assumption' && access?.can.review ? (
                    <button
                      type="button"
                      className="sw-link-button"
                      disabled={busy}
                      onClick={() => {
                        setConfirming(rule.id)
                        setSource('')
                      }}
                    >
                      Confirm for this project
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="sw-link-button"
                    onClick={() =>
                      ask(
                        `Explain the rule “${rule.description.slice(0, 80)}” and where it applies.`,
                      )
                    }
                  >
                    Explain
                  </button>
                </div>
                {confirming === rule.id ? (
                  <form
                    className="sw-step__insert"
                    onSubmit={(event) => {
                      event.preventDefault()
                      act(
                        [
                          {
                            type: 'confirm_rule',
                            rule: rule.id,
                            source: { kind: 'business_owner', reference: source.trim() },
                          },
                        ],
                        'Review this rule confirmation before applying it.',
                      )
                      setConfirming(null)
                    }}
                  >
                    <label>
                      Who or what confirms this rule?
                      <input
                        required
                        maxLength={300}
                        value={source}
                        onChange={(event) => setSource(event.target.value)}
                        placeholder="Business owner and policy or document reference"
                      />
                    </label>
                    <p className="sw-muted">
                      This confirms the existing condition and outcomes. Its blueprint origin stays
                      in the audit trail.
                    </p>
                    <div className="sw-actions">
                      <button type="submit" className="sw-button" disabled={busy || !source.trim()}>
                        Review confirmation
                      </button>
                      <button
                        type="button"
                        className="sw-button sw-button--quiet"
                        onClick={() => setConfirming(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}
              </li>
            )
          })}
        </ul>
      </section>
      <section className="sw-card" aria-label="Exceptions">
        <div className="sw-card__head">
          <h3>
            When something goes wrong <span className="sw-count">{business.exceptions.length}</span>
          </h3>
          <button type="button" className="sw-button" onClick={() => ask('Add an exception: ')}>
            Add an exception
          </button>
        </div>
        {business.exceptions.length === 0 ? (
          <p className="sw-muted">No exceptions recorded.</p>
        ) : (
          <table className="sw-table sw-table--wide">
            <thead>
              <tr>
                <th>Exception</th>
                <th>Happens when</th>
                <th>Recovery</th>
                <th>Handled at</th>
              </tr>
            </thead>
            <tbody>
              {business.exceptions.map((item) => (
                <tr key={item.id} data-changed={recent.has(item.id) || undefined}>
                  <td>
                    <strong>{item.name}</strong>
                  </td>
                  <td>{item.trigger}</td>
                  <td>
                    {item.recovery}
                    {item.resolution ? (
                      <small> · {item.resolution}</small>
                    ) : (
                      <small className="sw-warn-text"> · no resolution set</small>
                    )}
                  </td>
                  <td>
                    {handledBy(item.id)
                      .map(({ state }) => state.label)
                      .join(', ') || <small className="sw-warn-text">no step handles it</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {business.decisions.some((item) => item.status === 'open') ? (
        <p className="sw-muted sw-aside">
          {business.decisions.filter((item) => item.status === 'open').length} open business
          decisions affect these rules.{' '}
          <button type="button" className="sw-link-button" onClick={() => go('knowledge')}>
            Decide them in Domain Knowledge
          </button>
        </p>
      ) : null}
    </div>
  )
}
