import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Bot,
  Check,
  ShieldCheck,
  ChevronRight,
  CloudCheck,
  Eye,
  History,
  LayoutGrid,
  LifeBuoy,
  LoaderCircle,
  PanelLeftOpen,
  Rocket,
  Square,
  Truck,
  Users,
} from 'lucide-react'
import {
  STAGES,
  STATUS_LABEL,
  type StageKey,
  type StudioAccess,
  type StudioState,
} from '../../api/studio'
import type { Busy } from './useStudio'
import { ACTIVITY_TEXT, type Activity } from './bits'

/** A recognisable mark for the project, chosen from its domain. Purely decorative. */
function DomainIcon({ studio }: { studio: StudioState }) {
  const brief = studio.definition.business.brief
  const domain = studio.domain.domains.find((item) => item.id === brief.domain_id)
  const text =
    `${brief.domain_id ?? ''} ${domain?.name ?? ''} ${studio.definition.metadata.name}`.toLowerCase()
  const Icon = /transport|logistic|shipment|freight|fleet|delivery/.test(text)
    ? Truck
    : /leave|employee|people|hr\b/.test(text)
      ? Users
      : /support|ticket|helpdesk/.test(text)
        ? LifeBuoy
        : LayoutGrid
  return (
    <span className="sw-mark" aria-hidden="true">
      <Icon size={20} />
    </span>
  )
}

/** What the project is, judged only from its approvals and the generator's own result. */
export function projectPhase(studio: StudioState): {
  label: string
  tone: 'draft' | 'review' | 'done'
} {
  if (studio.compile?.status === 'generated') return { label: 'Generated', tone: 'done' }
  if (studio.approval.design.state === 'valid') return { label: 'Design approved', tone: 'done' }
  if (studio.approval.process.state === 'valid')
    return { label: 'Process approved', tone: 'review' }
  return { label: 'Draft', tone: 'draft' }
}

type TopBarProps = {
  studio: StudioState | null
  access: StudioAccess | null
  stage: StageKey
  busy: Busy
  leftCollapsed: boolean
  onOpenLeft: () => void
  showHistory: boolean
  onHistory: () => void
  onPreview: () => void
  onGenerate: () => void
  onStage: (stage: StageKey) => void
}

/** Project identity and the actions that apply to the whole project. Saving is never manual: every change is a server revision. */
export function StudioTopBar({
  studio,
  access,
  stage,
  busy,
  leftCollapsed,
  onOpenLeft,
  showHistory,
  onHistory,
  onPreview,
  onGenerate,
  onStage,
}: TopBarProps) {
  const name = studio?.definition.metadata.name ?? 'Opening…'
  const stageName = STAGES.find(([key]) => key === stage)?.[1] ?? ''
  const assistant = studio?.assistant
  const ready = !!studio && studio.approval.design.state === 'valid'
  const saving = busy === 'applying' || busy === 'creating'
  return (
    <header className="sw-top">
      <div className="sw-top__crumbs">
        {leftCollapsed ? (
          <button
            type="button"
            className="sw-icon-button sw-only-narrow"
            onClick={onOpenLeft}
            aria-label="Open navigation"
          >
            <PanelLeftOpen size={18} />
          </button>
        ) : null}
        <Link to="/design-studio" className="sw-top__back" aria-label="All projects">
          <ArrowLeft size={16} aria-hidden="true" />
        </Link>
        {studio ? (
          <select
            className="sw-mobile-stage"
            aria-label="Application stage"
            value={stage}
            onChange={(event) => onStage(event.target.value as StageKey)}
          >
            {STAGES.map(([key, label], index) => (
              <option
                key={key}
                value={key}
                disabled={
                  !!studio.flow && key !== studio.flow.active && !studio.flow.reviewed.includes(key)
                }
              >
                {index + 1}. {label}
              </option>
            ))}
          </select>
        ) : null}
        <nav aria-label="Breadcrumb">
          <ol>
            <li>
              <Link to="/design-studio">Projects</Link>
            </li>
            <li aria-hidden="true">
              <ChevronRight size={14} />
            </li>
            <li className="sw-top__name" title={name}>
              {name}
            </li>
            <li aria-hidden="true">
              <ChevronRight size={14} />
            </li>
            <li aria-current="page">
              <strong>{stageName}</strong>
            </li>
          </ol>
        </nav>
      </div>
      <div className="sw-top__actions">
        {assistant ? (
          <span className="sw-ai" data-on={assistant.enabled} title={assistant.reason}>
            <Bot size={14} aria-hidden="true" />
            {assistant.enabled ? 'AI assistant active' : 'Built-in rules only'}
          </span>
        ) : null}
        {studio ? (
          <span className="sw-saved" role="status" aria-live="polite">
            {saving ? (
              <>
                <LoaderCircle className="sw-spin" size={14} aria-hidden="true" /> Saving…
              </>
            ) : (
              <>
                <CloudCheck size={14} aria-hidden="true" /> Saved · revision {studio.revision}
              </>
            )}
          </span>
        ) : null}
        {studio ? (
          <button
            type="button"
            className="sw-button sw-button--quiet"
            onClick={onHistory}
            aria-expanded={showHistory}
          >
            <History size={14} aria-hidden="true" /> History
          </button>
        ) : null}
        {studio ? (
          <button
            type="button"
            className="sw-button"
            onClick={onPreview}
            disabled={!studio.definition.workflow_definitions.length}
            title="Preview or generate the application's own interface. The running application is started in Generate Application."
          >
            <Eye size={14} aria-hidden="true" /> Preview
          </button>
        ) : null}
        {studio && access?.studio_role_labels.length ? (
          <span
            className="sw-role"
            title={`Project access: ${access.project_capabilities.join(', ') || 'none'}`}
          >
            <ShieldCheck size={14} aria-hidden="true" />
            {access.studio_role_labels.join(' · ')}
          </span>
        ) : null}
        {studio && (!access || access.can.generate) ? (
          <button
            type="button"
            className="sw-button sw-button--primary sw-button--generate"
            aria-label="Generate application"
            onClick={onGenerate}
            disabled={!!studio.flow && studio.flow.active !== 'export'}
            title={
              ready
                ? 'Generate, check and test the application from the approved design.'
                : 'See what still has to happen before the application can be generated.'
            }
          >
            <Rocket size={15} aria-hidden="true" /> <span>Generate application</span>
          </button>
        ) : studio && access ? (
          <span className="sw-unavailable" role="note" title={access.denied.generate}>
            Generating is not part of your access
          </span>
        ) : null}
      </div>
    </header>
  )
}

/** The project heading: what is being built, and its phase. */
export function ProjectHeading({ studio }: { studio: StudioState }) {
  const phase = projectPhase(studio)
  const description =
    studio.definition.metadata.description || studio.definition.business.brief.goal
  return (
    <div className="sw-project-head">
      <DomainIcon studio={studio} />
      <div>
        <h1>
          {studio.definition.metadata.name}
          <span className="sw-phase" data-tone={phase.tone}>
            {phase.label}
          </span>
        </h1>
        {description ? <p title={description}>{description}</p> : null}
      </div>
    </div>
  )
}

/** The nine stages as one horizontal pipeline. Every status is the server's, computed from the saved specification. */
export function PipelineStepper({
  studio,
  stage,
  onStage,
}: {
  studio: StudioState
  stage: StageKey
  onStage: (stage: StageKey) => void
}) {
  return (
    <nav className="sw-pipeline" aria-label="Pipeline">
      <ol>
        {STAGES.map(([key, label], index) => {
          const status = studio.stages[key].status
          const current = key === stage
          return (
            <li key={key} data-status={status} data-current={current || undefined}>
              <button
                type="button"
                disabled={
                  !!studio.flow && key !== studio.flow.active && !studio.flow.reviewed.includes(key)
                }
                onClick={() => onStage(key)}
                aria-current={current ? 'step' : undefined}
                aria-label={`Pipeline step ${index + 1} of ${STAGES.length}: ${label}`}
                title={studio.stages[key].reason}
              >
                <span className="sw-pipeline__dot" aria-hidden="true">
                  {status === 'completed' ? <Check size={14} strokeWidth={3} /> : index + 1}
                </span>
                <span className="sw-pipeline__label">{label}</span>
                <span className="sw-pipeline__status">
                  {current && status === 'not_started' ? 'Here now' : STATUS_LABEL[status]}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

/** While the microphone, the transcription or the spoken reply is live, the workspace shows it plainly, with the way to stop it. */
export function VoiceStrip({
  activity,
  level,
  onStop,
}: {
  activity: Activity
  level: number
  onStop: () => void
}) {
  if (activity !== 'listening' && activity !== 'transcribing' && activity !== 'speaking')
    return null
  const bars = Array.from(
    { length: 24 },
    (_, index) => 0.25 + Math.abs(Math.sin(index * 1.7)) * 0.75,
  )
  return (
    <section
      className="sw-voice-strip"
      data-activity={activity}
      aria-label="Voice"
      role="status"
      aria-live="polite"
    >
      <span
        className="sw-voice-strip__wave"
        aria-hidden="true"
        style={
          {
            '--level': activity === 'listening' ? Math.min(1, level * 6).toFixed(2) : '0.6',
          } as CSSProperties
        }
      >
        {bars.map((height, index) => (
          <i
            key={index}
            style={
              { '--h': height.toFixed(2), animationDelay: `${(index % 6) * 90}ms` } as CSSProperties
            }
          />
        ))}
      </span>
      <strong>
        {activity === 'listening'
          ? 'I’m listening…'
          : activity === 'transcribing'
            ? 'Writing down what you said…'
            : 'Speaking the reply'}
      </strong>
      <span className="sw-voice-strip__hint">
        {activity === 'listening'
          ? 'Pause when you are done, or press Stop.'
          : activity === 'speaking'
            ? 'Press Stop or say “stop” to interrupt.'
            : ACTIVITY_TEXT[activity]}
      </span>
      <button type="button" className="sw-button" onClick={onStop}>
        <Square size={12} aria-hidden="true" /> Stop
      </button>
    </section>
  )
}

/** The project cannot be opened: say why in plain words and where to go next. Nothing about the project is revealed to someone without access. */
export function AccessDenied({
  kind,
  message,
}: {
  kind: 'forbidden' | 'missing'
  message: string | null
}) {
  return (
    <section className="sw-denied" role="alert" aria-labelledby="sw-denied-title">
      <h2 id="sw-denied-title">
        {kind === 'forbidden'
          ? 'Your role does not include this'
          : 'This project is not available to you'}
      </h2>
      <p>
        {kind === 'forbidden'
          ? (message ?? 'Your role in this organization does not allow this.')
          : 'It may not exist, or it has not been assigned to you. Design Studio only opens projects you are assigned to.'}
      </p>
      <p className="sw-muted">
        Ask a project owner or your organization administrator to assign you to the project, then
        try again.
      </p>
      <Link className="sw-button sw-button--primary" to="/workspace">
        Back to your workspace
      </Link>
    </section>
  )
}
