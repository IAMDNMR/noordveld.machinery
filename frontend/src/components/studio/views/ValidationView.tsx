import { useEffect, useRef, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import type { Finding } from '../../../api/applicationDefinition'
import type { StageKey } from '../../../api/studio'
import { Callout, StatusChip } from '../bits'
import type { ViewProps } from './types'
import { findingText, findingGroup } from '../findingPresentation'

const TAB_STAGE: Record<string, StageKey> = {
  brief: 'brief',
  knowledge: 'knowledge',
  workflow: 'workflow',
  data: 'data',
  rules: 'rules',
  roles: 'roles',
  screen: 'screen',
  approval: 'checks',
  checks: 'checks',
}
const GROUPS = [
  ['defect', 'Fix before generating', 'These issues block approval.'],
  [
    'business_decision',
    'Needs a decision',
    'Review the choices that need your business knowledge.',
  ],
  [
    'assumption',
    'Rules to confirm',
    'Check that these suggested rules match your business policy.',
  ],
  [
    'information',
    'Warnings and notes',
    'These do not block approval. Review them before approving.',
  ],
] as const
// Findings the Studio settles by itself (backend design_studio/auto_resolve.py): recorded facts only; rules, roles and authority stay with a person.
const OPTIONAL_QUESTIONS = new Set([
  'q_security',
  'q_accessibility',
  'q_performance',
  'q_constraints',
])

function Approval({
  scope,
  title,
  studio,
  blocked,
  reason,
  approve,
  busy,
  may,
  mayNot,
}: {
  scope: 'process' | 'design'
  title: string
  studio: ViewProps['studio']
  blocked: boolean
  reason: string
  approve: ViewProps['approve']
  busy: boolean
  may: boolean
  mayNot?: string
}) {
  const state = studio.approval[scope]
  const warnings = studio.analysis[scope].findings.filter((item) => item.severity === 'warning')
  const [acknowledged, setAcknowledged] = useState(false)
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  const submit = async () => {
    setWorking(true)
    setError(null)
    const failure = await approve(
      scope,
      warnings.map((item) => item.id),
      comment,
    )
    setWorking(false)
    if (failure) setError(failure)
  }
  return (
    <section className="sw-card sw-approval" aria-label={title} data-state={state.state}>
      <div className="sw-card__head">
        <h3>{title}</h3>
        <StatusChip
          status={
            state.state === 'valid'
              ? 'completed'
              : state.state === 'stale'
                ? 'needs_input'
                : blocked
                  ? 'blocked'
                  : 'ready_for_review'
          }
        />
      </div>
      {state.state === 'valid' && state.record ? (
        <p className="sw-muted">
          Approved at revision {state.record.revision} by {state.record.approved_by} on{' '}
          {state.record.approved_at.slice(0, 10)}
          {state.record.comment ? ` — “${state.record.comment}”` : ''}.
        </p>
      ) : state.state === 'stale' ? (
        <p className="sw-warn-text">
          This was approved before the content changed, so it no longer counts. It needs approving
          again.
        </p>
      ) : (
        <p className="sw-muted">
          {blocked ? reason : 'Ready for approval. Your workspace’s approval permissions apply.'}
        </p>
      )}
      {state.state !== 'valid' && !may ? (
        <p className="sw-callout-inline" role="note">
          {mayNot ?? 'Approving is not part of your access.'}
        </p>
      ) : null}
      {state.state !== 'valid' && may ? (
        <>
          {warnings.length ? (
            <label className="sw-check">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />{' '}
              I have reviewed and acknowledge {warnings.length} warning
              {warnings.length === 1 ? '' : 's'} (assumed rules, drafts, open questions)
            </label>
          ) : null}
          <label className="sw-field">
            <span>Comment (optional)</span>
            <input
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              maxLength={1000}
            />
          </label>
          <button
            type="button"
            className="sw-button sw-button--primary"
            disabled={busy || working || blocked || (warnings.length > 0 && !acknowledged)}
            onClick={() => void submit()}
          >
            {working ? 'Approving…' : `Approve ${scope}`}
          </button>
          {error ? (
            <Callout tone="danger" role="alert">
              {error}
            </Callout>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

/** Every finding the checks produce, sorted by what the person has to do about it, with the two approvals that gate generation. */
export function ValidationView({
  studio,
  access,
  busy,
  say,
  go,
  act,
  approve,
  resolve,
}: ViewProps) {
  const { design, process } = studio.analysis
  const { questions, requirements } = studio.definition.business
  const servedIds = new Set(
    studio.definition.workflow_definitions.flatMap((workflow) =>
      workflow.states.flatMap((state) => state.requirement_ids ?? []),
    ),
  )
  const resolvable =
    design.findings.some(
      (item) => item.code === 'REFERENCE_NO_OWNER' || item.code === 'STEP_REPEATED',
    ) ||
    requirements.some((item) => item.status === 'draft' && servedIds.has(item.id)) ||
    questions.some((item) => item.status === 'open' && OPTIONAL_QUESTIONS.has(item.id))
  const canResolve = !!resolve && !!access?.can.edit
  // A drafted process that a verified one already covers: [duplicate, verified], merged as a reviewed change.
  const overlaps = design.findings.filter(
    (item) => item.code === 'PROCESS_OVERLAP' && item.artefacts.length === 2,
  )
  const mergeAction = (item: Finding) => ({
    type: 'merge_process',
    duplicate: item.artefacts[0],
    keep: item.artefacts[1],
  })
  // Settle what the Studio can settle as soon as the checks show it, once per revision; the person is left only real decisions.
  const tried = useRef<number | null>(null)
  useEffect(() => {
    if (!canResolve || !resolvable || busy || tried.current === studio.definition.revision) return
    tried.current = studio.definition.revision
    void resolve?.()
  }, [canResolve, resolvable, busy, resolve, studio.definition.revision])
  const generated = !!studio.definition.generated_frontend
  const findings: Finding[] = design.findings.filter(
    (item) => item.code !== 'PROCESS_NOT_APPROVED' && (generated || item.code !== 'STEP_NO_SCREEN'),
  )
  const blocking = findings.filter((item) => item.severity === 'error')
  const business = studio.definition.business
  const steps = studio.definition.workflow_definitions.flatMap((workflow) =>
    workflow.states.filter((state) => state.kind !== 'start' && state.kind !== 'end'),
  )
  const served = business.requirements.filter((requirement) =>
    steps.some((step) => (step.requirement_ids ?? []).includes(requirement.id)),
  )
  const rulesOk = business.rules.filter((rule) => rule.status === 'confirmed')
  const defects = findings.filter((item) => findingGroup(item) === 'defect')
  const repairRequest = `Propose fixes for all blocking design issues together. Update existing items; do not add duplicates, invent business policies or confirm rules. Show the changes for review before saving:\n${defects.map((item) => `${item.code}: ${item.message} ${item.remediation}`).join('\n')}`
  const processOk = studio.approval.process.state === 'valid'
  const reasonFor = (scope: 'process' | 'design') =>
    scope === 'process'
      ? `${process.counts.error} blocking finding${process.counts.error === 1 ? '' : 's'} to resolve first.`
      : !processOk
        ? 'The process must be approved first.'
        : `${findings.filter((item) => item.severity === 'error').length} blocking finding${blocking.length === 1 ? '' : 's'} to resolve first.`

  if (!business.requirements.length && !studio.definition.workflow_definitions.length) {
    return (
      <div className="sw-empty">
        <div className="sw-empty__icon">
          <ShieldCheck size={28} />
        </div>
        <h3>Nothing to check yet</h3>
        <p>
          The checks run as soon as the design has requirements and a process. They never stop
          running: every change is checked again.
        </p>
      </div>
    )
  }
  return (
    <div className="sw-view">
      <div className="sw-tiles" role="list" aria-label="Summary">
        <div
          role="listitem"
          data-tone={
            blocking.filter((item) => item.category !== 'business_decision').length
              ? 'danger'
              : 'ok'
          }
        >
          <strong>{blocking.filter((item) => item.category !== 'business_decision').length}</strong>
          <span>to fix</span>
        </div>
        <div
          role="listitem"
          data-tone={
            findings.some(
              (item) => item.category === 'business_decision' && item.severity === 'error',
            )
              ? 'warn'
              : 'ok'
          }
        >
          <strong>{findings.filter((item) => item.category === 'business_decision').length}</strong>
          <span>decisions needed</span>
        </div>
        <div role="listitem">
          <strong>{findings.filter((item) => item.severity === 'warning').length}</strong>
          <span>warnings</span>
        </div>
        <div role="listitem">
          <strong>
            {served.length}/{business.requirements.length}
          </strong>
          <span>requirements linked to steps</span>
        </div>
        <div role="listitem">
          <strong>
            {rulesOk.length}/{business.rules.length}
          </strong>
          <span>rules confirmed</span>
        </div>
      </div>
      {studio.execution_gaps?.length ? (
        <section className="sw-card" aria-label="Application readiness">
          <h3>{studio.execution_gaps.length} capabilities need setup</h3>
          <p className="sw-muted">
            Design approval does not make these features work. Review the missing logic, data
            sources and connections before using the application.
          </p>
          <details>
            <summary>See what is unavailable</summary>
            <ul className="sw-findings">
              {studio.execution_gaps.map((item) => (
                <li key={`${item.category}:${item.item}`}>
                  <div>
                    <strong>{item.detail}</strong>
                    <p>{findingText(item.text, studio.definition)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </details>
        </section>
      ) : null}
      {canResolve && resolvable ? (
        <section className="sw-card" aria-label="Resolve automatically">
          <div className="sw-card__head">
            <div>
              <h3>{busy ? 'Resolving issues…' : 'Issues the Studio can resolve'}</h3>
              <p className="sw-muted">
                Agrees requirements a process step already implements, records optional details as
                not specified, and merges steps repeated back to back, and gives records others
                depend on (items, warehouses) a maintaining role. Rules and roles are never changed
                or removed for you.
              </p>
            </div>
            <button
              type="button"
              className="sw-button sw-button--primary"
              disabled={busy}
              onClick={() => void resolve?.()}
            >
              Resolve all
            </button>
          </div>
        </section>
      ) : null}
      {overlaps.length && access?.can.edit ? (
        <section className="sw-card" aria-label="Duplicate processes">
          <div className="sw-card__head">
            <div>
              <h3>
                {overlaps.length} drafted process{overlaps.length === 1 ? '' : 'es'} repeat a
                verified one
              </h3>
              <p className="sw-muted">
                The verified process already covers the same business activity. Merging moves the
                requirements, rules and exceptions across and shows you the result before anything
                is saved.
              </p>
            </div>
            <button
              type="button"
              className="sw-button sw-button--primary"
              disabled={busy}
              onClick={() =>
                act(overlaps.map(mergeAction), 'Review these process merges before applying them.')
              }
            >
              Review merges
            </button>
          </div>
        </section>
      ) : null}
      {defects.length ? (
        <section className="sw-card" aria-label="Repair design gaps">
          <div className="sw-card__head">
            <div>
              <h3>{busy ? 'Preparing fixes…' : 'Fix the blocking issues'}</h3>
              <p className="sw-muted">
                Review the suggested changes before saving. Opening this page never changes your
                design.
              </p>
            </div>
            <button
              type="button"
              className="sw-button sw-button--primary"
              disabled={busy || !access?.can.edit}
              onClick={() => say(repairRequest)}
            >
              Suggest fixes
            </button>
          </div>
        </section>
      ) : null}
      <div className="sw-grid sw-grid--2">
        <Approval
          scope="process"
          title="Process approval"
          studio={studio}
          blocked={process.blocking}
          reason={reasonFor('process')}
          approve={approve}
          busy={busy}
          may={!access || access.can.approve}
          mayNot={access?.denied.approve}
        />
        <Approval
          scope="design"
          title="Design approval"
          studio={studio}
          blocked={design.blocking || !processOk}
          reason={reasonFor('design')}
          approve={approve}
          busy={busy}
          may={!access || access.can.approve}
          mayNot={access?.denied.approve}
        />
      </div>
      {findings.length === 0 ? (
        <Callout tone="ok">
          No findings. The design is complete as far as the checks can tell.
        </Callout>
      ) : (
        GROUPS.map(([category, title, hint]) => {
          const items = findings.filter((item) => findingGroup(item) === category)
          return items.length ? (
            <details
              className="sw-card sw-disclosure"
              key={category}
              aria-label={title}
              open={category !== 'information'}
            >
              <summary>
                {title} <span className="sw-count">{items.length}</span>
              </summary>
              <p className="sw-muted">{hint}</p>
              <ul className="sw-findings">
                {items.map((item) => (
                  <li key={item.id} data-severity={item.severity}>
                    <div>
                      <span className={`sw-sev sw-sev--${item.severity}`}>{item.severity}</span>
                      <p>{findingText(item.message, studio.definition)}</p>
                      <small>{findingText(item.remediation, studio.definition)}</small>
                    </div>
                    <div className="sw-findings__actions">
                      {category === 'defect' ? (
                        <button
                          type="button"
                          className="sw-button"
                          onClick={() => say(`Fix this: ${item.message}`)}
                          disabled={busy || !access?.can.edit}
                        >
                          Fix with assistant
                        </button>
                      ) : item.code === 'PROCESS_OVERLAP' && access?.can.edit ? (
                        <button
                          type="button"
                          className="sw-button"
                          onClick={() =>
                            act(
                              [mergeAction(item)],
                              'Review this process merge before applying it.',
                            )
                          }
                          disabled={busy}
                        >
                          Merge
                        </button>
                      ) : category === 'assumption' ? (
                        <button
                          type="button"
                          className="sw-button"
                          onClick={() => go('rules')}
                          disabled={busy}
                        >
                          Review rule
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="sw-link-button"
                        onClick={() => say(`Explain why this is a problem: ${item.message}`)}
                      >
                        Explain
                      </button>
                      {TAB_STAGE[item.tab] && TAB_STAGE[item.tab] !== 'checks' ? (
                        <button
                          type="button"
                          className="sw-link-button"
                          onClick={() => go(TAB_STAGE[item.tab])}
                        >
                          Open
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ) : null
        })
      )}
    </div>
  )
}
