import { useState } from 'react'
import { KnowledgeView } from './KnowledgeView'
import {
  ArrowRight,
  Boxes,
  CircleAlert,
  Database,
  GitBranch,
  MessageCircleQuestion,
  MessageSquareText,
  Pencil,
  Sparkles,
  Target,
  Users,
} from 'lucide-react'
import type { WorkflowDefinition } from '../../../api/applicationDefinition'
import { Empty } from '../bits'
import type { ViewProps } from './types'

const PRIORITY = [
  ['must', 'Must have'],
  ['should', 'Should have'],
  ['could', 'Could have'],
  ['wont', 'Not now'],
] as const

/** The main path through a process, start to end, preferring unconditional and non-exception transitions. Read-only: the diagram is in Business Process. */
export function mainPath(workflow: WorkflowDefinition, limit = 9) {
  const byId = new Map(workflow.states.map((state) => [state.id, state]))
  const path = []
  const seen = new Set<string>()
  let current = workflow.states.find((state) => state.kind === 'start')
  while (current && !seen.has(current.id) && path.length < limit) {
    path.push(current)
    seen.add(current.id)
    const edges = workflow.transitions.filter(
      (edge) => edge.source === current!.id && !seen.has(edge.target),
    )
    const next = edges
      .map((edge) => byId.get(edge.target))
      .filter((state) => state && state.kind !== 'exception')
    current = next.find((state) => state!.kind !== 'end') ?? next[0] ?? undefined
  }
  return path
}

function ProcessPreview({ workflow, go }: { workflow: WorkflowDefinition; go: ViewProps['go'] }) {
  const steps = mainPath(workflow)
  const exceptions = workflow.states.filter((state) => state.kind === 'exception').length
  const decisions = workflow.states.filter((state) => state.kind === 'branch').length
  return (
    <section className="sw-card sw-flowcard" aria-label="Application process preview">
      <div className="sw-card__head">
        <h3>
          Application process <span className="sw-muted">· {workflow.name}</span>
        </h3>
        <button type="button" className="sw-button" onClick={() => go('workflow')}>
          View details <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
      <ol className="sw-flow" aria-label={`Main path of ${workflow.name}`}>
        {steps.map((step) => (
          <li key={step.id} data-kind={step.kind}>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>
      <p className="sw-muted">
        {workflow.states.length} steps in total · {decisions} decision{decisions === 1 ? '' : 's'} ·{' '}
        {exceptions} exception path{exceptions === 1 ? '' : 's'}. The main path is shown; branches
        and recovery are in Business Process.
      </p>
    </section>
  )
}

/** What the assistant understood, in the order a reviewer reads it: the goal, who it is for, what it must do, and what is still unclear.
 * Clarifying is a conversation: each open question goes to the assistant; typing an answer here is the secondary route. */
export function RequirementsView(props: ViewProps) {
  const { studio, recent, ask, act, busy, go, answer } = props
  const { definition } = studio
  const business = definition.business
  const [showKnowledge, setShowKnowledge] = useState(false)
  const brief = business.brief
  const steps = definition.workflow_definitions.flatMap((workflow) => workflow.states)
  const coverage = (id: string) =>
    steps.filter((step) => (step.requirement_ids ?? []).includes(id)).length
  const answered = business.questions.filter((question) => question.status !== 'open')
  const open = studio.questions
  const [typing, setTyping] = useState<string | null>(null)
  const [text, setText] = useState('')
  const domain = studio.domain.domains.find((item) => item.id === brief.domain_id)
  const packs = studio.domain.packs.filter((pack) => pack.adopted)
  const savedUsers = [
    ...new Set([
      ...business.roles
        .filter((role) => !/platform|automat/i.test(role.name))
        .map((role) => role.name),
      ...brief.user_types,
    ]),
  ]
  const suggestedUsers = [
    ...new Set(studio.domain.packs.flatMap((pack) => pack.role_names ?? [])),
  ].filter((name) => !/platform|automat/i.test(name))
  const users = savedUsers.length ? savedUsers : suggestedUsers
  const modules = definition.workflow_definitions.length
    ? definition.workflow_definitions.map((workflow) => workflow.name)
    : business.requirements
        .filter((item) => item.priority === 'must' && item.kind === 'functional')
        .map((item) => item.statement)
  const save = (id: string) => {
    const value = text.trim()
    if (!value) return
    act([{ type: 'answer_question', question_id: id, answer: value }], 'Noted.')
    setText('')
    setTyping(null)
  }

  if (!brief.goal.trim() && !business.requirements.length) {
    return (
      <Empty icon={<MessageSquareText size={28} />} title="Nothing captured yet">
        Tell the assistant what you want to build. What it understands will appear here as you talk.
      </Empty>
    )
  }
  return (
    <div className="sw-view sw-req">
      <section className="sw-card sw-building" aria-label="What I'm building for you">
        <div className="sw-card__head">
          <div className="sw-building__title">
            <Sparkles size={20} aria-hidden="true" />
            <div>
              <h3>What I’m building for you</h3>
              <p className="sw-muted">
                Based on our conversation and the saved specification. It changes as we talk.
              </p>
            </div>
          </div>
          <button type="button" className="sw-button" onClick={() => ask('Change the goal: ')}>
            <Pencil size={14} aria-hidden="true" /> Edit with AI
          </button>
        </div>
        <div className="sw-grid sw-grid--4">
          <article className="sw-fact">
            <Target size={20} aria-hidden="true" />
            <h4>Business goal</h4>
            <p className="sw-clamp">{brief.goal || 'Not stated yet.'}</p>
          </article>
          <article className="sw-fact">
            <Boxes size={20} aria-hidden="true" />
            <h4>Key modules</h4>
            {modules.length ? (
              <ul>
                {modules.slice(0, 5).map((item) => (
                  <li key={item}>{item}</li>
                ))}
                {modules.length > 5 ? (
                  <li className="sw-muted">and {modules.length - 5} more</li>
                ) : null}
              </ul>
            ) : (
              <p className="sw-muted">Appear once the process is designed.</p>
            )}
          </article>
          <article className="sw-fact">
            <Users size={20} aria-hidden="true" />
            <h4>Main users</h4>
            {!savedUsers.length && users.length ? (
              <small className="sw-muted">
                Suggested by domain knowledge · review in Roles &amp; Permissions
              </small>
            ) : null}
            {users.length ? (
              <ul>
                {users.slice(0, 5).map((item) => (
                  <li key={item}>{item}</li>
                ))}
                {users.length > 5 ? (
                  <li className="sw-muted">and {users.length - 5} more</li>
                ) : null}
              </ul>
            ) : (
              <>
                <p className="sw-muted">Not stated yet.</p>
                <button
                  type="button"
                  className="sw-link-button"
                  onClick={() => ask('The people who will use it are ')}
                >
                  Tell me who uses it
                </button>
              </>
            )}
          </article>
          <article className="sw-fact">
            <Database size={20} aria-hidden="true" />
            <h4>Domain</h4>
            <p>{domain?.name ?? brief.domain_id ?? 'Not identified yet'}</p>
            {packs.map((pack) => (
              <span
                className="sw-pill"
                key={pack.id}
                title={pack.synthetic ? 'Synthetic demonstration knowledge' : undefined}
              >
                {pack.title}
              </span>
            ))}
            <button
              type="button"
              className="sw-link-button"
              aria-expanded={showKnowledge}
              aria-controls="requirements-knowledge"
              onClick={() => setShowKnowledge((value) => !value)}
            >
              {showKnowledge ? 'Hide domain knowledge' : 'View domain knowledge'}{' '}
              <ArrowRight size={12} aria-hidden="true" />
            </button>
          </article>
        </div>
        {brief.problem || brief.outcomes.length || brief.constraints.length ? (
          <dl className="sw-brief-more">
            {brief.problem ? (
              <div>
                <dt>Problem today</dt>
                <dd>{brief.problem}</dd>
              </div>
            ) : null}
            {brief.outcomes.length ? (
              <div>
                <dt>Success looks like</dt>
                <dd>{brief.outcomes.join(' · ')}</dd>
              </div>
            ) : null}
            {brief.constraints.length ? (
              <div>
                <dt>Constraints</dt>
                <dd>{brief.constraints.join(' · ')}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </section>

      {showKnowledge ? (
        <section
          id="requirements-knowledge"
          className="sw-card"
          aria-label="Domain knowledge reference"
        >
          <div className="sw-card__head">
            <h3>Domain knowledge reference</h3>
            <button type="button" className="sw-button" onClick={() => setShowKnowledge(false)}>
              Close reference
            </button>
          </div>
          <p className="sw-muted">
            Read-only reference. Continue the stage review to prepare and adopt the domain draft.
          </p>
          <KnowledgeView {...props} busy={true} act={() => undefined} />
        </section>
      ) : null}

      {definition.workflow_definitions[0] ? (
        <ProcessPreview workflow={definition.workflow_definitions[0]} go={go} />
      ) : (
        <section className="sw-card sw-flowcard" aria-label="Application process preview">
          <h3>
            <GitBranch size={16} aria-hidden="true" /> Application process
          </h3>
          <p className="sw-muted">
            Not designed yet. Once I know who does what, I will draw the process from the first
            request to the last outcome.
          </p>
        </section>
      )}

      <section className="sw-card" aria-label="Still to clarify" hidden={!!studio.flow}>
        <div className="sw-card__head">
          <h3>
            <MessageCircleQuestion size={16} aria-hidden="true" /> Still to clarify{' '}
            <span className="sw-count">{open.length}</span>
          </h3>
        </div>
        {open.length === 0 ? (
          <p className="sw-muted">
            Nothing open. Everything I would ask is already answered or covered.
          </p>
        ) : (
          <ul className="sw-ask-list">
            {open.map((question) => (
              <li key={question.id}>
                <p>{question.text}</p>
                {typing === question.id ? (
                  <div className="sw-ask-list__type">
                    <input
                      aria-label={`Answer: ${question.text}`}
                      value={text}
                      onChange={(event) => setText(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') save(question.id)
                        if (event.key === 'Escape') setTyping(null)
                      }}
                      placeholder="Type the answer"
                    />
                    <button
                      type="button"
                      className="sw-button sw-button--primary"
                      disabled={busy || !text.trim()}
                      onClick={() => save(question.id)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="sw-button sw-button--quiet"
                      onClick={() => setTyping(null)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="sw-ask-list__actions">
                    <button type="button" className="sw-button" onClick={() => answer(question.id)}>
                      <MessageSquareText size={14} aria-hidden="true" /> Answer
                    </button>
                    <button
                      type="button"
                      className="sw-link-button"
                      onClick={() => {
                        setTyping(question.id)
                        setText('')
                      }}
                    >
                      Type here
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {answered.length ? (
          <details className="sw-answered">
            <summary>Answered ({answered.length}) — review or correct</summary>
            <ul>
              {answered.map((question) => (
                <li key={question.id}>
                  <strong>{question.text}</strong>
                  <p>{question.answer || 'Marked not applicable.'}</p>
                  <button
                    type="button"
                    className="sw-link-button"
                    onClick={() => ask(`Correction: ${question.text} — `)}
                  >
                    Correct this
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <section className="sw-card" aria-label="Requirements">
        <div className="sw-card__head">
          <h3>
            What it must do <span className="sw-count">{business.requirements.length}</span>
          </h3>
          <button type="button" className="sw-button" onClick={() => ask('Add a requirement: ')}>
            Add a requirement
          </button>
        </div>
        {business.requirements.length === 0 ? (
          <p className="sw-muted">
            No requirements recorded yet. Describe what people must be able to do.
          </p>
        ) : (
          PRIORITY.map(([key, label]) => {
            const items = business.requirements.filter((item) => item.priority === key)
            return items.length ? (
              <div key={key} className="sw-group">
                <h4>{label}</h4>
                <ul className="sw-rows">
                  {items.map((item) => (
                    <li key={item.id} data-changed={recent.has(item.id) || undefined}>
                      <div>
                        <p>{item.statement}</p>
                        <small>
                          {item.kind === 'non_functional' ? `${item.category ?? 'quality'} · ` : ''}
                          {item.status}
                          {item.acceptance_criteria.length
                            ? ` · ${item.acceptance_criteria.length} acceptance ${item.acceptance_criteria.length === 1 ? 'criterion' : 'criteria'}`
                            : ' · no acceptance criteria yet'}
                          {steps.length ? (
                            coverage(item.id) ? (
                              ` · served by ${coverage(item.id)} process ${coverage(item.id) === 1 ? 'step' : 'steps'}`
                            ) : (
                              <span className="sw-warn-text">
                                {' '}
                                · <CircleAlert size={11} aria-hidden="true" /> not served by a step
                                yet
                              </span>
                            )
                          ) : (
                            ''
                          )}
                        </small>
                        {item.acceptance_criteria.length ? (
                          <details>
                            <summary>Acceptance criteria</summary>
                            <ul>
                              {item.acceptance_criteria.map((criterion) => (
                                <li key={criterion.id}>{criterion.statement}</li>
                              ))}
                            </ul>
                          </details>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className="sw-icon-button"
                        aria-label={`Change requirement: ${item.statement.slice(0, 40)}`}
                        onClick={() => ask(`Change the requirement “${item.statement}”: `)}
                      >
                        <Pencil size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null
          })
        )}
      </section>
    </div>
  )
}
