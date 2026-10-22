import { useEffect, useState } from 'react'
import { CircleAlert } from 'lucide-react'
import type { StudioState } from '../../../api/studio'
import { getApplicationBlueprint, type ApplicationBlueprint } from '../../../api/studioFrontend'

/** The proposed application at a glance: what it contains, who does what, and what still needs a decision. Built from the saved
 *  specification, never from a template fit score. */
export function ApplicationStructure({
  definition,
  notSetUp = 0,
}: {
  definition: StudioState['definition']
  /** Features the application cannot run yet (rules or calculations nobody has set up). */
  notSetUp?: number
}) {
  const { id: projectId, revision } = definition
  const [blueprint, setBlueprint] = useState<ApplicationBlueprint | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void getApplicationBlueprint(projectId, controller.signal)
      .then((value) => {
        if (value.revision === revision) setBlueprint(value)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [projectId, revision])

  const business = definition.business
  const workflows = definition.workflow_definitions
  const doing = business.roles.map((role) => ({
    role,
    processes: workflows
      .filter((workflow) => workflow.states.some((state) => state.role_id === role.id))
      .map((workflow) => workflow.name),
    maintains: business.entities.filter((entity) => entity.owner_role_id === role.id),
  }))
  const working = doing.filter((item) => item.processes.length || item.maintains.length)
  const idle = doing.length - working.length
  const gaps = blueprint?.requirements.filter((item) => item.status === 'needs_design') ?? []
  const decisions = business.decisions.filter((item) => item.status === 'open').length
  const unconfirmed = business.rules.filter((rule) => rule.status !== 'confirmed').length
  const plural = (count: number, one: string, many = `${one}s`) =>
    `${count} ${count === 1 ? one : many}`
  const todo = [
    gaps.length ? `${plural(gaps.length, 'requirement')} still need a screen design` : '',
    decisions ? `${plural(decisions, 'open business decision')}` : '',
    unconfirmed ? `${plural(unconfirmed, 'rule')} not yet confirmed` : '',
    notSetUp
      ? `${plural(notSetUp, 'feature')} not set up, so the steps that need ${notSetUp === 1 ? 'it' : 'them'} stay switched off`
      : '',
  ].filter(Boolean)

  return (
    <section className="sw-card sw-proposal" aria-label="Proposed application">
      <div className="sw-card__head">
        <div>
          <h3>Proposed application</h3>
          <p className="sw-muted">
            Built from your approved requirements, knowledge and process. Explore it below as each
            role would use it, then ask the assistant to change anything.
          </p>
        </div>
      </div>
      <div className="sw-tiles" role="list" aria-label="What the application contains">
        {(
          [
            [workflows.length, 'processes'],
            [business.entities.length, 'record types'],
            [working.length, 'roles at work'],
            [blueprint?.surfaces.length ?? '…', 'screens'],
          ] as const
        ).map(([count, label]) => (
          <div role="listitem" key={label}>
            <strong>{count}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <details className="sw-proposal__who">
        <summary>
          Who does what · {working.length} roles{idle ? ` (${idle} without work yet)` : ''}
        </summary>
        <ul>
          {working.map(({ role, processes, maintains }) => (
            <li key={role.id}>
              <strong>{role.name}</strong>
              <span>
                {processes.length ? processes.join(' · ') : 'No process steps'}
                {maintains.length
                  ? ` — maintains ${maintains.map((item) => item.name).join(', ')}`
                  : ''}
              </span>
            </li>
          ))}
        </ul>
      </details>
      {todo.length ? (
        <div className="sw-proposal__todo" role="note">
          <CircleAlert size={16} aria-hidden="true" />
          <div>
            <strong>Before this is ready</strong>
            <ul>
              {todo.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  )
}
