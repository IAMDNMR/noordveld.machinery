import {
  ArrowRight,
  BookOpen,
  Bot,
  CircleCheck,
  CircleDashed,
  Mic,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react'
import {
  STAGES,
  type StageKey,
  type StudioAccess,
  type StudioState,
  type VoiceStatus,
} from '../../api/studio'
import { projectPhase } from './StudioChrome'

const ACTION_LABEL: Record<keyof StudioAccess['can'], string> = {
  edit: 'Edit and ask the assistant',
  generate: 'Generate the application',
  review: 'Review',
  approve: 'Approve',
  launch: 'Launch for review',
  manage_access: 'Manage project access',
}
const stageName = (key: StageKey) => STAGES.find(([stage]) => stage === key)?.[1] ?? key

/** What the assistant works from: the saved project, its reference knowledge and which services are really connected. */
export function ContextPanel({
  studio,
  access,
  voiceStatus,
  onNavigate,
}: {
  studio: StudioState
  access: StudioAccess | null
  voiceStatus: VoiceStatus | null
  onNavigate: (stage: StageKey) => void
}) {
  const brief = studio.definition.business.brief
  const domain = studio.domain.domains.find((item) => item.id === brief.domain_id)
  const packs = studio.domain.packs.filter((pack) => pack.adopted)
  const decisions = studio.definition.business.decisions.filter((item) => item.status === 'open')
  const assistant = voiceStatus?.assistant ?? studio.assistant
  const speech = voiceStatus?.speech
  const phase = projectPhase(studio)
  return (
    <div
      className="sw-side-panel"
      role="tabpanel"
      id="sw-tabpanel-context"
      aria-labelledby="sw-tab-context"
    >
      <section>
        <h3>Next step</h3>
        <p>{studio.next.text}</p>
        <button type="button" className="sw-button" onClick={() => onNavigate(studio.next.stage)}>
          Go to {studio.next.label} <ArrowRight size={14} aria-hidden="true" />
        </button>
      </section>
      {access ? (
        <section aria-label="Your access">
          <h3>Your access</h3>
          <dl className="sw-kv">
            <div>
              <dt>Studio role</dt>
              <dd>{access.studio_role_labels.join(' · ') || 'None'}</dd>
            </div>
            <div>
              <dt>In this project</dt>
              <dd>
                {access.project_capabilities.length
                  ? access.project_capabilities.join(', ')
                  : 'No access'}
              </dd>
            </div>
          </dl>
          <ul className="sw-plain">
            {(Object.keys(access.can) as (keyof StudioAccess['can'])[]).map((action) => (
              <li key={action} data-on={access.can[action]}>
                {access.can[action] ? (
                  <CircleCheck size={14} aria-hidden="true" />
                ) : (
                  <CircleDashed size={14} aria-hidden="true" />
                )}
                <span>
                  <strong>{ACTION_LABEL[action]}</strong>
                  <small>
                    {access.can[action] ? 'Allowed' : (access.denied[action] ?? 'Not allowed')}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <h3>Project</h3>
        <dl className="sw-kv">
          <div>
            <dt>Phase</dt>
            <dd>{phase.label}</dd>
          </div>
          <div>
            <dt>Revision</dt>
            <dd>{studio.revision}</dd>
          </div>
          <div>
            <dt>Domain</dt>
            <dd>{domain?.name ?? 'Not identified yet'}</dd>
          </div>
          <div>
            <dt>Goal</dt>
            <dd>{brief.goal || 'Not stated yet'}</dd>
          </div>
        </dl>
      </section>
      <section>
        <h3>Reference knowledge</h3>
        {packs.length ? (
          <ul className="sw-plain">
            {packs.map((pack) => (
              <li key={pack.id}>
                <BookOpen size={14} aria-hidden="true" />
                <span>
                  <strong>{pack.title}</strong>
                  <small>
                    version {pack.version}
                    {pack.synthetic ? ' · synthetic demonstration data' : ''}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="sw-muted">None adopted. The design is built from the conversation only.</p>
        )}
        {decisions.length ? (
          <button type="button" className="sw-link-button" onClick={() => onNavigate('knowledge')}>
            {decisions.length} business decision{decisions.length === 1 ? '' : 's'} still open
          </button>
        ) : null}
      </section>
      <section>
        <h3>Connected services</h3>
        <ul className="sw-plain">
          <li data-on={assistant.enabled}>
            <Bot size={14} aria-hidden="true" />
            <span>
              <strong>
                {assistant.enabled ? `Language model · ${assistant.provider}` : 'No language model'}
              </strong>
              <small>{assistant.reason}</small>
            </span>
          </li>
          {speech ? (
            <li data-on={speech.enabled}>
              <Mic size={14} aria-hidden="true" />
              <span>
                <strong>
                  {speech.enabled ? `Voice · ${speech.provider}` : 'Voice unavailable'}
                </strong>
                <small>{speech.reason}</small>
              </span>
            </li>
          ) : null}
        </ul>
      </section>
    </div>
  )
}

/** The checks, summarised where the conversation happens: what blocks approval, and a way to fix it by asking. */
export function ChecksPanel({
  studio,
  onNavigate,
  onFix,
  busy,
}: {
  studio: StudioState
  onNavigate: (stage: StageKey) => void
  onFix: (text: string) => void
  busy: boolean
}) {
  const findings = studio.analysis.design.findings
  const errors = findings.filter((item) => item.severity === 'error')
  const warnings = findings.filter((item) => item.severity === 'warning')
  const approvals = [
    ['Process', studio.approval.process.state],
    ['Design', studio.approval.design.state],
  ] as const
  const blocked = (Object.keys(studio.stages) as StageKey[]).filter(
    (key) => studio.stages[key].status === 'blocked' || studio.stages[key].status === 'needs_input',
  )
  return (
    <div
      className="sw-side-panel"
      role="tabpanel"
      id="sw-tabpanel-checks"
      aria-labelledby="sw-tab-checks"
    >
      <div className="sw-mini-tiles">
        <div data-tone={errors.length ? 'danger' : 'ok'}>
          <strong>{errors.length}</strong>
          <span>blocking</span>
        </div>
        <div data-tone={warnings.length ? 'warn' : 'ok'}>
          <strong>{warnings.length}</strong>
          <span>warnings</span>
        </div>
      </div>
      <section>
        <h3>Approvals</h3>
        <ul className="sw-plain">
          {approvals.map(([name, state]) => (
            <li key={name} data-on={state === 'valid'}>
              {state === 'valid' ? (
                <CircleCheck size={14} aria-hidden="true" />
              ) : state === 'stale' ? (
                <TriangleAlert size={14} aria-hidden="true" />
              ) : (
                <CircleDashed size={14} aria-hidden="true" />
              )}
              <span>
                <strong>{name}</strong>
                <small>
                  {state === 'valid'
                    ? 'Approved for the current content'
                    : state === 'stale'
                      ? 'Approved earlier; the content changed since'
                      : 'Not approved yet'}
                </small>
              </span>
            </li>
          ))}
        </ul>
      </section>
      {blocked.length ? (
        <section>
          <h3>Stages waiting on you</h3>
          <ul className="sw-plain">
            {blocked.map((key) => (
              <li key={key}>
                <ShieldAlert size={14} aria-hidden="true" />
                <span>
                  <button type="button" className="sw-link-button" onClick={() => onNavigate(key)}>
                    {stageName(key)}
                  </button>
                  <small>{studio.stages[key].reason}</small>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <h3>To resolve first</h3>
        {errors.length === 0 ? (
          <p className="sw-muted">Nothing blocks approval.</p>
        ) : (
          <ul className="sw-plain sw-plain--findings">
            {errors.slice(0, 5).map((item) => (
              <li key={item.id}>
                <span>
                  <span>{item.message}</span>
                  <button
                    type="button"
                    className="sw-link-button"
                    disabled={busy}
                    onClick={() => onFix(`Fix this: ${item.message}`)}
                  >
                    Fix with assistant
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="sw-button" onClick={() => onNavigate('checks')}>
          Open Validation <ArrowRight size={14} aria-hidden="true" />
        </button>
      </section>
    </div>
  )
}
