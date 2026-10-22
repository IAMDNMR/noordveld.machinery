import { useMemo, useState } from 'react'
import { ArrowRight, GitBranch, Pencil, Plus, ShieldCheck, Sparkles, X } from 'lucide-react'
import type { WorkflowState } from '../../../api/applicationDefinition'
import { ProcessDiagram } from '../diagrams/ProcessDiagram'
import { stepIssues } from '../diagrams/processLayout'
import { Empty } from '../bits'
import type { ViewProps } from './types'
import { ProcessJourney } from './ProcessJourney'

const KIND: Record<string, string> = {
  start: 'Start',
  end: 'End',
  branch: 'Decision',
  exception: 'Exception',
  approval: 'Approval',
  form: 'Form',
  search: 'Search',
  review: 'Review',
  action: 'Action',
}
const NEW_KINDS = [
  ['form', 'Form'],
  ['review', 'Review'],
  ['action', 'Action'],
  ['search', 'Search'],
] as const

/** Choose entities for a step's inputs or outputs. Changes are sent as one typed action and come back for review. */
function DataPicker({
  label,
  chosen,
  entities,
  onChange,
}: {
  label: string
  chosen: string[]
  entities: { id: string; name: string }[]
  onChange: (ids: string[]) => void
}) {
  return (
    <fieldset className="sw-picker">
      <legend>{label}</legend>
      {entities.map((entity) => (
        <label key={entity.id}>
          <input
            type="checkbox"
            checked={chosen.includes(entity.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...chosen, entity.id]
                  : chosen.filter((id) => id !== entity.id),
              )
            }
          />
          {entity.name}
        </label>
      ))}
    </fieldset>
  )
}

function Inspector({
  step,
  studio,
  workflowId,
  busy,
  ask,
  act,
  onClose,
  issues,
}: {
  step: WorkflowState
  studio: ViewProps['studio']
  workflowId: string
  busy: boolean
  ask: ViewProps['ask']
  act: ViewProps['act']
  onClose: () => void
  issues: string[]
}) {
  const business = studio.definition.business
  const workflow = studio.definition.workflow_definitions.find((item) => item.id === workflowId)!
  const [editing, setEditing] = useState<'name' | 'data' | 'insert' | null>(null)
  const [name, setName] = useState(step.label)
  const [reads, setReads] = useState(step.reads_entity_ids ?? [])
  const [writes, setWrites] = useState(step.writes_entity_ids ?? [])
  const [insert, setInsert] = useState({ name: '', kind: 'form', role: step.role_id ?? '' })
  const [path, setPath] = useState('')
  const working = step.kind !== 'start' && step.kind !== 'end'
  const label = (id: string) => workflow.states.find((item) => item.id === id)?.label ?? id
  const names = (ids: string[] | undefined, pool: { id: string; name: string }[]) =>
    (ids ?? []).map((id) => pool.find((item) => item.id === id)?.name ?? id)
  const rules = (step.rule_ids ?? [])
    .map((id) => business.rules.find((item) => item.id === id))
    .filter((item) => item !== undefined)
  const exceptions = (step.exception_ids ?? [])
    .map((id) => business.exceptions.find((item) => item.id === id))
    .filter((item) => item !== undefined)
  const requirements = (step.requirement_ids ?? [])
    .map((id) => business.requirements.find((item) => item.id === id))
    .filter((item) => item !== undefined)
  const unlinked = business.requirements.filter(
    (item) => !(step.requirement_ids ?? []).includes(item.id),
  )
  const outgoing = workflow.transitions.filter((edge) => edge.source === step.id)
  const incoming = workflow.transitions.filter((edge) => edge.target === step.id)
  const when = (edge: (typeof outgoing)[number]) =>
    edge.condition.kind === 'always'
      ? ''
      : ` when ${business.rules.find((rule) => rule.id === edge.condition.field)?.description ?? edge.condition.field} ${edge.condition.kind === 'not_equals' ? 'is not' : 'is'} ${String(edge.condition.value).replaceAll('_', ' ').toLowerCase()}`
  const undecided = business.decisions.filter(
    (item) =>
      item.status !== 'decided' &&
      (item.affects ?? []).some((id) => id === step.id || (step.rule_ids ?? []).includes(id)),
  )

  return (
    <aside className="sw-card sw-step" aria-label="Step details">
      <header className="sw-step__head">
        <div>
          <p className="sw-eyebrow">{KIND[step.kind] ?? step.kind} step</p>
          {editing === 'name' ? (
            <form
              className="sw-inline-form"
              onSubmit={(event) => {
                event.preventDefault()
                if (name.trim() && name.trim() !== step.label)
                  act([{ type: 'rename_step', step: step.id, name: name.trim() }])
                setEditing(null)
              }}
            >
              <input
                aria-label="Step name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={120}
              />
              <button
                type="submit"
                className="sw-button sw-button--primary"
                disabled={busy || !name.trim()}
              >
                Save
              </button>
              <button
                type="button"
                className="sw-button sw-button--quiet"
                onClick={() => {
                  setName(step.label)
                  setEditing(null)
                }}
              >
                Cancel
              </button>
            </form>
          ) : (
            <h3>
              {step.label}{' '}
              <button
                type="button"
                className="sw-icon-button"
                aria-label="Rename step"
                onClick={() => setEditing('name')}
              >
                <Pencil size={13} />
              </button>
            </h3>
          )}
        </div>
        <button
          type="button"
          className="sw-icon-button"
          aria-label="Close step details"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>
      {issues.map((text) => (
        <p className="sw-issue" key={text}>
          {text}
        </p>
      ))}
      {undecided.map((item) => (
        <p className="sw-callout-inline" key={item.id}>
          Waiting on a business decision: {item.question}
        </p>
      ))}
      <dl className="sw-step__facts">
        {working ? (
          <div>
            <dt>Responsible</dt>
            <dd>
              <select
                aria-label="Responsible role"
                value={step.role_id ?? ''}
                disabled={busy}
                onChange={(event) => {
                  if (event.target.value)
                    act([{ type: 'assign_step_role', step: step.id, role: event.target.value }])
                }}
              >
                {!step.role_id ? <option value="">No role assigned</option> : null}
                {business.roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </dd>
          </div>
        ) : null}
        {step.permission ? (
          <div>
            <dt>Permission checked on the server</dt>
            <dd>
              <code>{step.permission}</code>
            </dd>
          </div>
        ) : null}
        {working ? (
          <div>
            <dt>Inputs and outputs</dt>
            <dd>
              {editing === 'data' ? (
                <div className="sw-step__data">
                  <DataPicker
                    label="Reads"
                    chosen={reads}
                    entities={business.entities}
                    onChange={setReads}
                  />
                  <DataPicker
                    label="Changes"
                    chosen={writes}
                    entities={business.entities}
                    onChange={setWrites}
                  />
                  <div className="sw-actions">
                    <button
                      type="button"
                      className="sw-button sw-button--primary"
                      disabled={busy}
                      onClick={() => {
                        act([
                          {
                            type: 'set_step_data',
                            step: step.id,
                            reads: reads.map((id) => names([id], business.entities)[0]),
                            writes: writes.map((id) => names([id], business.entities)[0]),
                          },
                        ])
                        setEditing(null)
                      }}
                    >
                      Propose change
                    </button>
                    <button
                      type="button"
                      className="sw-button sw-button--quiet"
                      onClick={() => {
                        setReads(step.reads_entity_ids ?? [])
                        setWrites(step.writes_entity_ids ?? [])
                        setEditing(null)
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <span>
                    Reads: {names(step.reads_entity_ids, business.entities).join(', ') || 'nothing'}
                  </span>
                  <span>
                    Changes:{' '}
                    {names(step.writes_entity_ids, business.entities).join(', ') || 'nothing'}
                  </span>
                  <button
                    type="button"
                    className="sw-link-button"
                    onClick={() => setEditing('data')}
                  >
                    Edit inputs and outputs
                  </button>
                </>
              )}
            </dd>
          </div>
        ) : null}
        {step.outputs.length ? (
          <div>
            <dt>Decides</dt>
            <dd>
              {step.outputs
                .map(
                  (output) =>
                    business.rules.find((rule) => rule.id === output)?.description ?? output,
                )
                .join(' · ')}
            </dd>
          </div>
        ) : null}
        {rules.length ? (
          <div>
            <dt>Rules</dt>
            <dd>
              {rules.map((item) => (
                <span key={item.id}>
                  {item.description}{' '}
                  <em
                    className={`sw-badge sw-badge--${item.status === 'confirmed' ? 'confirmed' : 'assumption'}`}
                  >
                    {item.status === 'confirmed' ? 'confirmed' : 'assumption'}
                  </em>
                </span>
              ))}
            </dd>
          </div>
        ) : null}
        {exceptions.length ? (
          <div>
            <dt>When it goes wrong</dt>
            <dd>
              {exceptions.map((item) => (
                <span key={item.id}>
                  <strong>{item.name}</strong>
                  {item.recovery ? ` — ${item.recovery}` : ''}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Transitions</dt>
          <dd>
            {incoming.length ? (
              <span>From: {incoming.map((edge) => label(edge.source)).join(', ')}</span>
            ) : null}
            {outgoing.length ? (
              outgoing.map((edge) => (
                <span key={edge.id}>
                  <ArrowRight size={12} aria-hidden="true" /> {label(edge.target)}
                  {when(edge)}
                </span>
              ))
            ) : (
              <span>
                {step.kind === 'end'
                  ? `Ends the process (${step.outcome ?? 'no outcome set'})`
                  : 'No next step'}
              </span>
            )}
          </dd>
        </div>
        {working ? (
          <div>
            <dt>Serves</dt>
            <dd>
              {requirements.map((item) => (
                <span key={item.id}>{item.statement}</span>
              ))}
              {unlinked.length ? (
                <select
                  aria-label="Link a requirement"
                  value=""
                  disabled={busy}
                  onChange={(event) => {
                    if (event.target.value)
                      act([
                        {
                          type: 'link_requirement',
                          requirement: event.target.value,
                          step: step.id,
                        },
                      ])
                  }}
                >
                  <option value="">
                    {requirements.length ? 'Link another requirement…' : 'Link a requirement…'}
                  </option>
                  {unlinked.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.statement.length > 80
                        ? `${item.statement.slice(0, 78)}…`
                        : item.statement}
                    </option>
                  ))}
                </select>
              ) : null}
            </dd>
          </div>
        ) : null}
        {step.outcome && step.kind === 'end' ? (
          <div>
            <dt>Outcome</dt>
            <dd>{step.outcome}</dd>
          </div>
        ) : null}
      </dl>
      {editing === 'insert' ? (
        <form
          className="sw-step__insert"
          onSubmit={(event) => {
            event.preventDefault()
            act([
              {
                type: 'insert_step',
                workflow: workflowId,
                after: step.id,
                transition_id: path || outgoing[0]?.id,
                step: {
                  name: insert.name.trim(),
                  kind: insert.kind,
                  role: insert.role
                    ? business.roles.find((role) => role.id === insert.role)?.name
                    : undefined,
                },
              },
            ])
            setEditing(null)
          }}
        >
          <strong>New step after “{step.label}”</strong>
          {outgoing.length > 1 ? (
            <label>
              Insert on path
              <select
                required
                aria-label="Path for the new step"
                value={path}
                onChange={(event) => setPath(event.target.value)}
              >
                <option value="">Choose a path…</option>
                {outgoing.map((edge) => (
                  <option key={edge.id} value={edge.id}>
                    {label(edge.target)}
                    {when(edge)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <input
            aria-label="New step name"
            placeholder="Name of the step"
            value={insert.name}
            onChange={(event) => setInsert({ ...insert, name: event.target.value })}
            maxLength={120}
          />
          <div className="sw-inline-form">
            <select
              aria-label="Kind of step"
              value={insert.kind}
              onChange={(event) => setInsert({ ...insert, kind: event.target.value })}
            >
              {NEW_KINDS.map(([key, text]) => (
                <option key={key} value={key}>
                  {text}
                </option>
              ))}
            </select>
            <select
              aria-label="Role for the new step"
              value={insert.role}
              onChange={(event) => setInsert({ ...insert, role: event.target.value })}
            >
              <option value="">No role yet</option>
              {business.roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
          </div>
          <div className="sw-actions">
            <button
              type="submit"
              className="sw-button sw-button--primary"
              disabled={busy || !insert.name.trim() || (outgoing.length > 1 && !path)}
            >
              Propose step
            </button>
            <button
              type="button"
              className="sw-button sw-button--quiet"
              onClick={() => setEditing(null)}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="sw-step__actions">
          {step.kind !== 'end' ? (
            <button
              type="button"
              className="sw-button"
              disabled={!outgoing.length || busy}
              onClick={() => setEditing('insert')}
            >
              <Plus size={14} aria-hidden="true" /> Step after
            </button>
          ) : null}
          {working ? (
            <button
              type="button"
              className="sw-button"
              disabled={busy}
              onClick={() => act([{ type: 'add_approval', before: step.id, workflow: workflowId }])}
            >
              <ShieldCheck size={14} aria-hidden="true" /> Approval before
            </button>
          ) : null}
          <button
            type="button"
            className="sw-button sw-button--quiet"
            onClick={() => ask(`Explain the step “${step.label}” and why it is there.`)}
          >
            <Sparkles size={14} aria-hidden="true" /> Explain
          </button>
          {working ? (
            <button
              type="button"
              className="sw-button sw-button--quiet"
              onClick={() => ask(`For the step “${step.label}”, add an exception path: `)}
            >
              Add exception path…
            </button>
          ) : null}
        </div>
      )}
      <p className="sw-muted sw-step__note">
        Changes are recorded as a new revision. Review mode proposes structural edits in the
        assistant; guided mode saves draft edits directly. Policy decisions always need review.
      </p>
    </aside>
  )
}

/** The business process as a working diagram: decisions, approvals and exception paths. Selecting a step opens an inspector that edits the same model the application is generated from. */
export function ProcessView({ studio, ask, act, select, selection, recent, busy }: ViewProps) {
  const { definition } = studio
  const business = definition.business
  const workflows = definition.workflow_definitions
  const [workflowId, setWorkflowId] = useState<string | null>(workflows[0]?.id ?? null)
  const workflow = workflows.find((item) => item.id === workflowId) ?? workflows[0]
  const [presentation, setPresentation] = useState<'journey' | 'diagram'>('diagram')
  const [stepId, setStepId] = useState<string | null>(null)
  // A step named by the assistant ("show me the shipment process") or elsewhere in the workspace brings its process forward.
  const [seenSelection, setSeenSelection] = useState<string | null>(null)
  if (selection !== seenSelection) {
    setSeenSelection(selection)
    const owner = selection
      ? workflows.find(
          (item) => item.id === selection || item.states.some((state) => state.id === selection),
        )
      : undefined
    if (owner) {
      setWorkflowId(owner.id)
      setStepId(owner.id === selection ? null : selection)
    }
  }
  const issues = useMemo(
    () => (workflow ? stepIssues(workflow, business.rules) : new Map<string, string[]>()),
    [workflow, business.rules],
  )
  if (!workflow)
    return (
      <Empty
        icon={<GitBranch size={28} />}
        title="The process has not been designed yet"
        action={
          <button
            type="button"
            className="sw-button sw-button--primary"
            onClick={() => ask('Design the main process from the requirements.')}
          >
            Ask the assistant to design it
          </button>
        }
      >
        Once the requirements are clear I will draw how work moves from the first request to the
        last outcome, including decisions and what happens when something goes wrong.
      </Empty>
    )
  const step = workflow.states.find((item) => item.id === stepId) ?? null
  const changed = workflow.states.filter((state) => recent.has(state.id))
  const problems = [...issues.values()].filter((list) => list.length).length

  return (
    <div className="sw-view sw-process">
      {workflows.length > 1 ? (
        <div className="sw-tabs" role="tablist" aria-label="Processes">
          {workflows.map((item) => (
            <button
              type="button"
              role="tab"
              key={item.id}
              aria-selected={item.id === workflow.id}
              onClick={() => {
                setWorkflowId(item.id)
                setStepId(null)
              }}
            >
              {item.name}
            </button>
          ))}
        </div>
      ) : null}
      <div className="sw-process__head">
        <div>
          {workflows.length > 1 ? null : <h2>{workflow.name}</h2>}
          <p className="sw-muted">
            {workflow.states.length} steps ·{' '}
            {workflow.states.filter((item) => item.kind === 'branch').length} decisions ·{' '}
            {workflow.states.filter((item) => item.kind === 'exception').length} exception paths
            {problems
              ? ` · ${problems} step${problems === 1 ? '' : 's'} with a structural problem`
              : ''}
          </p>
        </div>
        {changed.length ? (
          <span className="sw-pill">
            Just changed: {changed.map((item) => item.label).join(', ')}
          </span>
        ) : (
          <span className="sw-muted">Select a step to inspect or change it.</span>
        )}
      </div>
      <div className="sw-toolbar" role="group" aria-label="Process presentation">
        <button
          type="button"
          className="sw-button"
          aria-pressed={presentation === 'journey'}
          onClick={() => setPresentation('journey')}
        >
          Detailed process
        </button>
        <button
          type="button"
          className="sw-button"
          aria-pressed={presentation === 'diagram'}
          onClick={() => setPresentation('diagram')}
        >
          Flow diagram
        </button>
      </div>
      <div className="sw-process__body" data-inspecting={step ? true : undefined}>
        {presentation === 'journey' ? (
          <ProcessJourney
            workflow={workflow}
            definition={studio.definition}
            onSelect={(id) => {
              setStepId(id)
              select(id)
            }}
          />
        ) : (
          <ProcessDiagram
            workflow={workflow}
            business={business}
            selectedId={stepId}
            readOnly
            maxHeight={640}
            onSelect={(id) => {
              setStepId(id)
              select(id)
            }}
            onConnect={() => undefined}
          />
        )}
        {step ? (
          <Inspector
            key={`${step.id}:${studio.revision}`}
            step={step}
            studio={studio}
            workflowId={workflow.id}
            busy={busy}
            ask={ask}
            act={act}
            issues={issues.get(step.id) ?? []}
            onClose={() => {
              setStepId(null)
              select(null)
            }}
          />
        ) : null}
      </div>
    </div>
  )
}
