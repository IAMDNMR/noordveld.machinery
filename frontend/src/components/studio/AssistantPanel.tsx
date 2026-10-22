import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, RefObject } from 'react'
import {
  Check,
  ChevronDown,
  Info,
  ChevronRight,
  Keyboard,
  LoaderCircle,
  Mic,
  PanelRightClose,
  Send,
  Sparkles,
  Undo2,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react'
import type {
  OpenQuestion,
  Proposal,
  StageKey,
  StudioAccess,
  Turn,
  VoiceStatus,
} from '../../api/studio'
import { ACTIVITY_TEXT, Callout, VoiceOrb, type Activity } from './bits'
import { ChecksPanel, ContextPanel } from './AssistantTabs'
import type { ChatMessage, StudioApi } from './useStudio'
import type { useVoice } from './useVoice'

type Voice = ReturnType<typeof useVoice>
type Props = {
  access: StudioAccess | null
  api: StudioApi
  voice: Voice
  voiceStatus: VoiceStatus | null
  mode: 'panel' | 'dock'
  onMode: (mode: 'panel' | 'dock') => void
  draft: string
  onDraft: (text: string) => void
  onSubmit: (text: string, via: 'text' | 'voice') => void
  suggestions: string[]
  askedQuestion: OpenQuestion | null
  onClearAsked: () => void
  questions: OpenQuestion[]
  onPickQuestion: (question: OpenQuestion) => void
  onSpeak: (text: string) => void
  composer: RefObject<HTMLTextAreaElement | null>
  onNavigate: (stage: StageKey) => void
}

const delta = (before: number, after: number) =>
  after === before ? `${after}` : `${before} → ${after}`

const isDecision = (proposal: Proposal) =>
  proposal.actions.some((action) => action.type === 'answer_decision')

function ProposalCard({
  message,
  proposal,
  api,
}: {
  message: Extract<ChatMessage, { role: 'assistant' }>
  proposal: Proposal
  api: StudioApi
}) {
  const [open, setOpen] = useState(false)
  const status = message.proposal
  const errors = proposal.validation
  return (
    <section className="sw-proposal" data-status={status} aria-label="Proposed change">
      <header>
        <Sparkles size={14} aria-hidden="true" />
        <strong>
          {status === 'applied'
            ? 'Applied'
            : status === 'dismissed'
              ? 'Dismissed'
              : status === 'stale'
                ? 'Out of date'
                : 'Review this change'}
        </strong>
      </header>
      <ul className="sw-changes">
        {proposal.changes.map((change) => (
          <li key={`${change.item_id}:${change.summary}`}>
            <span data-kind={change.kind}>
              {change.kind === 'added' ? '+' : change.kind === 'removed' ? '−' : '~'}
            </span>
            {change.summary}
          </li>
        ))}
      </ul>
      {proposal.reasons.length ? (
        <p className="sw-proposal__why">{proposal.reasons.join(' ')}</p>
      ) : null}
      <p className="sw-proposal__impact">
        Validation errors {delta(errors.before.error, errors.after.error)} · warnings{' '}
        {delta(errors.before.warning, errors.after.warning)}
        {proposal.approvals_made_stale.length
          ? ` · ${proposal.approvals_made_stale.join(' ')}`
          : ''}
      </p>
      {status === 'pending' || status === 'applying' ? (
        <div className="sw-proposal__actions">
          <button
            type="button"
            className="sw-button sw-button--primary"
            disabled={status === 'applying' || api.busy !== 'idle'}
            onClick={() => void api.applyProposal(message.id)}
          >
            {status === 'applying' ? (
              <LoaderCircle className="sw-spin" size={14} />
            ) : (
              <Check size={14} />
            )}{' '}
            Apply
          </button>
          <button
            type="button"
            className="sw-button"
            disabled={status === 'applying' || api.busy !== 'idle'}
            onClick={() => api.dismissProposal(message.id)}
          >
            <X size={14} /> Dismiss
          </button>
          <button
            type="button"
            className="sw-button sw-button--quiet"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Details
          </button>
        </div>
      ) : null}
      {status === 'pending' || status === 'applying' ? (
        <p className="sw-proposal__state">Proposed only — nothing is saved until it is applied.</p>
      ) : null}
      {isDecision(proposal) && (status === 'pending' || status === 'applying') ? (
        <p className="sw-proposal__state">
          A business decision: a project or process owner applies it.
        </p>
      ) : null}
      {status === 'stale' ? (
        <p className="sw-proposal__stale">
          The project changed after this was proposed. Ask again for a fresh proposal.
        </p>
      ) : null}
      {open ? (
        <ul className="sw-diff" aria-label="Detailed changes">
          {proposal.diff.map((item) => (
            <li key={`${item.area}:${item.item_id}`}>
              <code>{item.area}</code> {item.item_id}{' '}
              <em>
                {item.change}
                {item.fields?.length ? `: ${item.fields.join(', ')}` : ''}
              </em>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function Bubble({
  message,
  api,
  onSpeak,
}: {
  message: ChatMessage
  api: StudioApi
  onSpeak: (text: string) => void
}) {
  if (message.role === 'user')
    return (
      <div className="sw-msg sw-msg--user">
        <p>
          {message.via === 'voice' ? <Mic size={12} aria-label="Spoken" /> : null}
          {message.text}
        </p>
      </div>
    )
  const turn: Turn | undefined = message.turn
  const canUndo = message.undo && !message.undo.done && api.studio?.revision === message.undo.from
  return (
    <div className={`sw-msg sw-msg--assistant${message.notice ? ' sw-msg--notice' : ''}`}>
      <p>{message.text}</p>
      {turn?.degraded ? (
        <small className="sw-note">{turn.degraded} Answered with the built-in rules.</small>
      ) : null}
      {turn?.applied.length ? (
        <ul className="sw-applied" aria-label="Changes made">
          {turn.applied.map((change) => (
            <li key={`${change.item_id}:${change.summary}`}>
              <Check size={12} aria-hidden="true" />
              {change.summary}
            </li>
          ))}
        </ul>
      ) : null}
      {turn?.approvals_made_stale.map((text) => (
        <small className="sw-note sw-note--warn" key={text}>
          {text}
        </small>
      ))}
      {[...(turn?.notes ?? []), ...(message.notes ?? [])].length ? (
        <ul className="sw-effects" aria-label="What this means">
          {[...(turn?.notes ?? []), ...(message.notes ?? [])].map((text) => (
            <li key={text}>
              <Info size={12} aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      ) : null}
      {turn?.rejected.length ? (
        <ul className="sw-rejected" aria-label="Not done">
          {turn.rejected.map((item) => (
            <li key={`${item.type}:${item.reason}`}>{item.reason}</li>
          ))}
        </ul>
      ) : null}
      {turn?.proposal ? (
        <ProposalCard message={message} proposal={turn.proposal} api={api} />
      ) : null}
      <div className="sw-msg__tools">
        {canUndo ? (
          <button
            type="button"
            className="sw-link-button"
            onClick={() => void api.undo(message.id)}
          >
            <Undo2 size={12} /> Undo
          </button>
        ) : null}
        {message.undo?.done ? <small>Undone</small> : null}
        {!message.notice ? (
          <button
            type="button"
            className="sw-link-button"
            onClick={() => onSpeak(message.text)}
            aria-label="Read this reply aloud"
          >
            <Volume2 size={12} /> Listen
          </button>
        ) : null}
      </div>
    </div>
  )
}

/** Conversation, voice and proposals. The same panel is the compact dock when the person wants the room for the work. */
export function AssistantPanel({
  access,
  api,
  voice,
  voiceStatus,
  mode,
  onMode,
  draft,
  onDraft,
  onSubmit,
  suggestions,
  askedQuestion,
  onClearAsked,
  questions,
  onPickQuestion,
  onSpeak,
  composer,
  onNavigate,
}: Props) {
  const end = useRef<HTMLDivElement | null>(null)
  const thinking = api.busy !== 'idle'
  const activity: Activity = voice.state === 'idle' && thinking ? 'thinking' : voice.state
  const last = api.messages.at(-1)
  // Scroll after a new message or an assistant activity change.
  // eslint-disable-next-line react/exhaustive-effect-dependencies
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [api.messages.length, thinking])
  const submit = () => {
    const text = draft.trim()
    if (text) {
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
  const assistant = voiceStatus?.assistant ?? api.studio?.assistant
  const model = assistant?.enabled
    ? `Language model · ${assistant.provider}`
    : 'Built-in rules · no language model'
  const [tab, setTab] = useState<'chat' | 'context' | 'checks'>('chat')
  const blocking = api.studio
    ? api.studio.analysis.design.findings.filter((item) => item.severity === 'error').length
    : 0

  if (mode === 'dock') {
    return (
      <div className="sw-dock" role="complementary" aria-label="Assistant (collapsed)">
        <VoiceOrb activity={activity} level={voice.level} onClick={voice.toggle} size="sm" />
        <div className="sw-dock__text">
          <strong>{ACTIVITY_TEXT[activity]}</strong>
          <span>{last?.role === 'assistant' ? last.text : 'Ask for anything, or just talk.'}</span>
        </div>
        <button
          type="button"
          className="sw-icon-button"
          onClick={() => onMode('panel')}
          aria-label="Open assistant"
        >
          <ChevronRight size={18} style={{ transform: 'rotate(-90deg)' }} />
        </button>
      </div>
    )
  }

  return (
    <aside className="sw-right" aria-label="Assistant">
      <header className="sw-right__head">
        <div className="sw-right__tabs" role="tablist" aria-label="Assistant panel">
          {(
            [
              ['chat', 'AI Assistant'],
              ['context', 'Project context'],
              ['checks', 'Validation'],
            ] as const
          ).map(([key, label]) => (
            <button
              type="button"
              role="tab"
              key={key}
              id={`sw-tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`sw-tabpanel-${key}`}
              onClick={() => setTab(key)}
            >
              {label}
              {key === 'checks' && blocking ? (
                <span className="sw-tab-count" aria-label={`${blocking} blocking`}>
                  {blocking}
                </span>
              ) : null}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="sw-icon-button"
          onClick={() => onMode('dock')}
          aria-label="Collapse assistant to a compact control"
        >
          <PanelRightClose size={18} />
        </button>
      </header>
      {tab === 'context' && api.studio ? (
        <ContextPanel
          studio={api.studio}
          access={access}
          voiceStatus={voiceStatus}
          onNavigate={onNavigate}
        />
      ) : null}
      {tab === 'checks' && api.studio ? (
        <ChecksPanel
          studio={api.studio}
          onNavigate={onNavigate}
          onFix={(text) => {
            setTab('chat')
            onSubmit(text, 'text')
          }}
          busy={thinking}
        />
      ) : null}
      {tab === 'chat' ? (
        <>
          <div
            className="sw-thread"
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            id="sw-tabpanel-chat"
          >
            {api.messages.length === 0 ? (
              <p className="sw-thread__empty">
                Tell me what you need, or ask about anything on the screen.
              </p>
            ) : null}
            {api.messages.map((message) => (
              <Bubble key={message.id} message={message} api={api} onSpeak={onSpeak} />
            ))}
            {thinking ? (
              <div className="sw-msg sw-msg--assistant sw-msg--thinking" role="status">
                <span className="sw-typing" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                {api.busy === 'creating'
                  ? 'Creating the project…'
                  : api.busy === 'applying'
                    ? 'Applying…'
                    : 'Thinking…'}
              </div>
            ) : null}
            {api.error ? (
              <Callout tone="danger" role="alert">
                {api.error}
              </Callout>
            ) : null}
            <div ref={end} />
          </div>
          {questions.length && !askedQuestion ? (
            <div className="sw-questions" aria-label="Open questions">
              <small>Still worth answering</small>
              {questions.slice(0, 2).map((question) => (
                <button type="button" key={question.id} onClick={() => onPickQuestion(question)}>
                  {question.text}
                </button>
              ))}
            </div>
          ) : null}
          {suggestions.length && !draft ? (
            <div className="sw-suggestions" aria-label="Suggestions">
              {suggestions.map((text) => (
                <button
                  type="button"
                  key={text}
                  onClick={() => onSubmit(text, 'text')}
                  disabled={thinking}
                >
                  {text}
                </button>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      <div className="sw-composer">
        {access && !access.can.edit ? (
          <p className="sw-readonly" role="note">
            {access.denied.edit ?? 'You can read this project but not change it.'} The assistant
            works on changes, so it is unavailable to you here; use Project context and the stages
            to review.
          </p>
        ) : null}
        {askedQuestion ? (
          <div className="sw-asked">
            <span>Answering: {askedQuestion.text}</span>
            <button type="button" onClick={onClearAsked} aria-label="Stop answering this question">
              <X size={12} />
            </button>
          </div>
        ) : null}
        <div className="sw-composer__row">
          <textarea
            ref={composer}
            rows={1}
            disabled={!!access && !access.can.edit}
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={onKey}
            placeholder={
              askedQuestion
                ? 'Your answer…'
                : 'Describe a change, ask a question, or press the microphone'
            }
            aria-label="Message to the assistant"
            maxLength={4000}
          />
          <VoiceOrb
            activity={access && !access.can.edit ? 'unavailable' : activity}
            level={voice.level}
            onClick={voice.toggle}
            size="md"
          />
          <button
            type="button"
            className="sw-send"
            onClick={submit}
            disabled={!draft.trim() || thinking}
            aria-label="Send message"
          >
            <Send size={16} />
          </button>
        </div>
        <div className="sw-voicebar" role="status" aria-live="polite">
          <span data-activity={activity}>
            <i aria-hidden="true" />
            {activity === 'unavailable'
              ? (voice.message ?? 'Voice unavailable')
              : activity === 'thinking' && api.busy === 'applying'
                ? 'Applying…'
                : ACTIVITY_TEXT[activity]}
          </span>
          {activity === 'listening' ? (
            <button type="button" className="sw-link-button" onClick={voice.cancel}>
              Cancel
            </button>
          ) : null}
          {activity === 'speaking' ? (
            <button type="button" className="sw-link-button" onClick={voice.interrupt}>
              Stop speaking
            </button>
          ) : null}
        </div>
        {voice.message && activity !== 'unavailable' ? (
          <p className="sw-voice-message" role="alert">
            {voice.message}{' '}
            <button type="button" className="sw-link-button" onClick={voice.dismiss}>
              Dismiss
            </button>
          </p>
        ) : null}
        <div className="sw-toggles">
          <label title="Hear the assistant's replies when you speak to it">
            <input
              type="checkbox"
              checked={voice.speakReplies}
              onChange={(event) => voice.setSpeakReplies(event.target.checked)}
              disabled={activity === 'unavailable'}
            />
            {voice.speakReplies ? <Volume2 size={13} /> : <VolumeX size={13} />} Read replies aloud
          </label>
          <label title="After the assistant speaks, listen again automatically. Speaking over it interrupts it.">
            <input
              type="checkbox"
              checked={voice.handsFree}
              onChange={(event) => voice.setHandsFree(event.target.checked)}
              disabled={activity === 'unavailable'}
            />
            <Mic size={13} /> Keep listening
          </label>
          <span className="sw-keys" title={assistant?.reason}>
            <Keyboard size={13} aria-hidden="true" /> Enter sends · {model}
          </span>
        </div>
      </div>
    </aside>
  )
}
