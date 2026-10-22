import type { CSSProperties, ReactNode } from 'react'
import {
  AudioLines,
  BookOpen,
  Check,
  Database,
  FileText,
  GitBranch,
  LoaderCircle,
  Mic,
  MicOff,
  PanelsTopLeft,
  Rocket,
  Scale,
  ShieldCheck,
  Square,
  TriangleAlert,
  Users,
} from 'lucide-react'
import { STATUS_LABEL, type StageKey, type StageStatus } from '../../api/studio'
import type { VoiceState } from './useVoice'

export const STAGE_ICON: Record<StageKey, typeof FileText> = {
  brief: FileText,
  knowledge: BookOpen,
  workflow: GitBranch,
  data: Database,
  screen: PanelsTopLeft,
  rules: Scale,
  roles: Users,
  checks: ShieldCheck,
  export: Rocket,
}

export function StatusChip({
  status,
  compact = false,
}: {
  status: StageStatus
  compact?: boolean
}) {
  return (
    <span className={`sw-chip sw-chip--${status}`} data-status={status}>
      <i aria-hidden="true" />
      {compact ? null : STATUS_LABEL[status]}
      {compact ? <span className="sw-sr">{STATUS_LABEL[status]}</span> : null}
    </span>
  )
}

/** The state the person sees: what the assistant is doing right now. `thinking` is the language model working, not the microphone. */
export type Activity = VoiceState | 'thinking'
export const ACTIVITY_TEXT: Record<Activity, string> = {
  idle: 'Ready',
  listening: 'Listening…',
  transcribing: 'Transcribing…',
  thinking: 'Thinking…',
  speaking: 'Speaking',
  unavailable: 'Voice unavailable',
  error: 'Voice problem',
}

/** The microphone, as one control whose look follows what is happening. */
export function VoiceOrb({
  activity,
  level,
  onClick,
  size = 'md',
  label,
}: {
  activity: Activity
  level: number
  onClick: () => void
  size?: 'sm' | 'md' | 'lg'
  label?: string
}) {
  const disabled = activity === 'unavailable'
  const name =
    label ??
    (activity === 'listening'
      ? 'Stop listening and send'
      : activity === 'speaking'
        ? 'Interrupt and speak'
        : activity === 'transcribing'
          ? 'Cancel transcription'
          : disabled
            ? 'Voice unavailable'
            : 'Start talking')
  const Icon = disabled
    ? MicOff
    : activity === 'speaking'
      ? AudioLines
      : activity === 'listening'
        ? Square
        : activity === 'transcribing' || activity === 'thinking'
          ? LoaderCircle
          : Mic
  return (
    <button
      type="button"
      className={`sw-orb sw-orb--${size}`}
      data-activity={activity}
      onClick={onClick}
      disabled={disabled}
      aria-label={name}
      title={name}
      style={{ '--level': level.toFixed(2) } as CSSProperties}
    >
      <span className="sw-orb__ring" aria-hidden="true" />
      <span className="sw-orb__ring sw-orb__ring--2" aria-hidden="true" />
      <Icon
        className="sw-orb__icon"
        size={size === 'lg' ? 34 : size === 'md' ? 22 : 18}
        aria-hidden="true"
      />
    </button>
  )
}

export function Check16({ done }: { done: boolean }) {
  return done ? (
    <Check size={14} aria-hidden="true" />
  ) : (
    <span className="sw-dot" aria-hidden="true" />
  )
}

export function Callout({
  tone = 'info',
  children,
  role,
}: {
  tone?: 'info' | 'warn' | 'danger' | 'ok'
  children: ReactNode
  role?: 'alert' | 'status'
}) {
  return (
    <div className={`sw-callout sw-callout--${tone}`} role={role}>
      {tone === 'warn' || tone === 'danger' ? <TriangleAlert size={16} aria-hidden="true" /> : null}
      <div>{children}</div>
    </div>
  )
}

export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="sw-empty">
      {icon ? (
        <div className="sw-empty__icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  )
}

export function Meter({ done, total, label }: { done: number; total: number; label: string }) {
  return (
    <div className="sw-meter" role="img" aria-label={`${label}: ${done} of ${total}`}>
      <i style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
    </div>
  )
}
