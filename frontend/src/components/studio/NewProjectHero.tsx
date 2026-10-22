import { Link } from 'react-router-dom'
import type { KeyboardEvent, RefObject } from 'react'
import {
  ArrowUpRight,
  ArrowLeft,
  Check,
  Layers3,
  Send,
  Sparkles,
  Truck,
  Users,
  Headphones,
} from 'lucide-react'
import type { ApplicationDefinition } from '../../api/applicationDefinition'
import type { VoiceStatus } from '../../api/studio'
import { ACTIVITY_TEXT, Callout, VoiceOrb, type Activity } from './bits'
import type { useVoice } from './useVoice'

const EXAMPLES = [
  'I want to build a transport management system for our company to manage transport requests, vehicle assignments, shipment tracking, deliveries, and exceptions.',
  'We need an employee leave request system where managers approve or reject requests.',
  'Build a customer support ticket tracker with escalation to a team lead.',
]

type Props = {
  voice: ReturnType<typeof useVoice>
  activity: Activity
  voiceStatus: VoiceStatus | null
  draft: string
  onDraft: (text: string) => void
  onSubmit: (text: string, via: 'text' | 'voice') => void
  composer: RefObject<HTMLTextAreaElement | null>
  busy: boolean
  error: string | null
  projectsError: string | null
  projects: ApplicationDefinition[]
  onOpen: (id: string) => void
}

/** A new project starts as a conversation, not a form: say what you want to build. */
export function NewProjectHero({
  voice,
  activity,
  voiceStatus,
  draft,
  onDraft,
  onSubmit,
  composer,
  busy,
  error,
  projectsError,
  projects,
  onOpen,
}: Props) {
  const submit = () => {
    const text = draft.trim()
    if (text && !busy) {
      onSubmit(text, 'text')
      onDraft('')
    }
  }
  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }
  const speech = voiceStatus?.speech
  const model = voiceStatus?.assistant
  return (
    <section className="sw-hero" aria-labelledby="sw-hero-title">
      <Link to="/design-studio" className="sw-hero__back">
        <ArrowLeft size={16} />
        All projects
      </Link>
      <div className="sw-hero__inner">
        <div className="sw-hero__badge">
          <Sparkles size={14} /> YOUR IDEAS. REAL APPLICATIONS.
        </div>
        <h1 id="sw-hero-title" aria-label="What would you like to bring to life?">
          What would you like
          <br />
          to <em>bring to life?</em>
        </h1>
        <p className="sw-hero__lead">
          Start with an idea. Together, we’ll shape the process, design the experience, and build an
          application that works for you.
        </p>
        <div className="sw-hero__compose">
          <div className="sw-hero__compose-label">
            <Sparkles size={16} />
            <span>Every great application starts with an idea</span>
          </div>
          <textarea
            ref={composer}
            rows={3}
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={onKey}
            aria-label="Describe the application you want to build"
            placeholder="I want to build an application that…"
            maxLength={4000}
          />
          <div className="sw-hero__compose-footer">
            <div className="sw-hero__voice">
              <VoiceOrb
                activity={busy ? 'thinking' : activity}
                level={voice.level}
                onClick={voice.toggle}
                size="sm"
              />
              <p role="status" aria-live="polite" className="sw-hero__state">
                {busy
                  ? 'Thinking…'
                  : activity === 'idle'
                    ? speech?.enabled
                      ? 'Or tell me your idea'
                      : ACTIVITY_TEXT.idle
                    : activity === 'unavailable'
                      ? (voice.message ?? 'Voice unavailable')
                      : ACTIVITY_TEXT[activity]}
              </p>
            </div>
            <button
              type="button"
              className="sw-button sw-button--primary"
              onClick={submit}
              disabled={!draft.trim() || busy}
            >
              <span>Start building</span>
              <Send size={15} aria-hidden="true" />
            </button>
          </div>
          {voice.message && activity !== 'unavailable' ? (
            <p className="sw-voice-message" role="alert">
              {voice.message}
            </p>
          ) : null}
        </div>
        <div className="sw-hero__trust">
          <span>
            <Check size={13} /> Guided from idea to application
          </span>
          <span>
            <Layers3 size={13} /> Process, data & screens in one place
          </span>
        </div>
        <div className="sw-hero__examples" aria-label="Examples">
          <div className="sw-hero__section-label">
            <small>A little inspiration</small>
            <span>Choose a starting point</span>
          </div>
          <div className="sw-hero__cards">
            {EXAMPLES.map((text, index) => {
              const Icon = [Truck, Users, Headphones][index]
              return (
                <button
                  type="button"
                  key={text}
                  aria-label={text}
                  onClick={() => {
                    onDraft(text)
                    composer.current?.focus()
                  }}
                >
                  <span className="sw-hero__card-icon">
                    <Icon size={21} />
                  </span>
                  <strong>
                    {['Transport & logistics', 'People & operations', 'Customer support'][index]}
                    <ArrowUpRight size={16} />
                  </strong>
                  <span>
                    {
                      [
                        'Manage requests, plan shipments, and keep deliveries on track.',
                        'Make leave requests and team approvals feel effortless.',
                        'Organise tickets, resolve issues, and keep customers happy.',
                      ][index]
                    }
                  </span>
                </button>
              )
            })}
          </div>
        </div>
        {error ? (
          <Callout tone="danger" role="alert">
            {error}
          </Callout>
        ) : null}
        {projectsError ? (
          <Callout tone="warn" role="status">
            {projectsError}
          </Callout>
        ) : null}
        <p className="sw-hero__providers">
          <i data-ready={!!model?.enabled} />
          {model?.enabled ? 'Your design assistant is ready' : 'Design with guided suggestions'}
          {speech?.enabled ? ' · Voice enabled' : ''}
        </p>
        {speech && !speech.enabled && speech.reason ? (
          <p className="sw-hero__providers">
            Voice unavailable: {speech.reason} You can still type your idea.
          </p>
        ) : null}
        {projects.length ? (
          <div className="sw-hero__projects">
            <h2>Continue a project</h2>
            <ul>
              {projects.slice(0, 6).map((project) => (
                <li key={project.id}>
                  <button type="button" onClick={() => onOpen(project.id)}>
                    <strong>{project.metadata.name}</strong>
                    <small>revision {project.revision}</small>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  )
}
