import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactElement } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'
import { approveProject, getAudit, type AuditEntry } from '../api/applicationDefinition'
import { ApiError } from '../api/client'
import {
  getVoiceStatus,
  STAGES,
  STATUS_LABEL,
  type OpenQuestion,
  type StageKey,
  type VoiceStatus,
} from '../api/studio'
import { useSession } from '../store/session'
import { AssistantPanel } from '../components/studio/AssistantPanel'
import { StatusChip, type Activity } from '../components/studio/bits'
import { localIntent } from '../components/studio/intents'
import { NewProjectHero } from '../components/studio/NewProjectHero'
import { StageSidebar } from '../components/studio/StageSidebar'
import {
  AccessDenied,
  PipelineStepper,
  ProjectHeading,
  StudioTopBar,
  VoiceStrip,
} from '../components/studio/StudioChrome'
import { useStudio } from '../components/studio/useStudio'
import { OptionalSetup } from '../components/studio/OptionalSetup'
import { useVoice } from '../components/studio/useVoice'
import { DataModelView } from '../components/studio/views/DataModelView'
import { GenerateView } from '../components/studio/views/GenerateView'
import { ApplicationPreviewDialog } from '../components/studio/views/ApplicationPreviewDialog'
import { KnowledgeView } from '../components/studio/views/KnowledgeView'
import { ProcessView } from '../components/studio/views/ProcessView'
import { RequirementsView } from '../components/studio/views/RequirementsView'
import { RolesView } from '../components/studio/views/RolesView'
import { RulesView } from '../components/studio/views/RulesView'
import { ScreensView } from '../components/studio/views/ScreensView'
import type { ViewProps } from '../components/studio/views/types'
import { ValidationView } from '../components/studio/views/ValidationView'
import './StudioWorkspacePage.css'
import './StudioPolish.css'

const VIEWS: Record<StageKey, (props: ViewProps) => ReactElement | null> = {
  brief: RequirementsView,
  knowledge: KnowledgeView,
  workflow: ProcessView,
  data: DataModelView,
  screen: ScreensView,
  rules: RulesView,
  roles: RolesView,
  checks: ValidationView,
  export: GenerateView,
}
const isStage = (value: string | null): value is StageKey => STAGES.some(([key]) => key === value)
const narrow = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(max-width: 1180px)').matches

const SUGGESTIONS: Record<StageKey, string[]> = {
  brief: [
    'Who still needs to be covered?',
    'Summarize the application requirements',
    'Show me the complete process',
  ],
  knowledge: ['What reference knowledge applies?', 'Which decisions are still open?'],
  workflow: [
    'Explain this process from start to finish',
    'Show the approval steps in this process',
    'Show the exception paths in this process',
  ],
  data: ['Show how the records connect', 'Which fields are mandatory?'],
  screen: ['Which screens does each role use?', 'Why does this screen exist?'],
  rules: ['Explain the rules used by this process', 'Which rules need policy confirmation?'],
  roles: ['Which role performs each step?', 'Who can create and change each record?'],
  checks: ['Explain why validation is failing', 'What blocks approval?'],
  export: ['Generate the application now', 'What is not executable yet?'],
}

function HistoryPanel({
  projectId,
  revision,
  onRestore,
  onClose,
}: {
  projectId: string
  revision: number
  onRestore: (revision: number) => void
  onClose: () => void
}) {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  // The saved revision is the cache key for the external audit trail.
  // eslint-disable-next-line react/exhaustive-effect-dependencies
  useEffect(() => {
    void getAudit(projectId).then(setEntries, () => setEntries([]))
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [projectId, revision])
  const label = (operation: string) =>
    ({
      create: 'Project created',
      update: 'Edited',
      'assistant:apply': 'Assistant change',
      'assistant:revert': 'Restored an earlier revision',
      'approve:process': 'Process approved',
      'approve:design': 'Design approved',
      'generate:screens': 'Screens generated',
    })[operation] ?? operation
  return (
    <div className="sw-history" role="dialog" aria-label="Revision history">
      <header>
        <strong>Revision history</strong>
        <button type="button" className="sw-link-button" onClick={onClose}>
          Close
        </button>
      </header>
      {entries === null ? (
        <p className="sw-muted">Loading…</p>
      ) : (
        <ol>
          {[...entries].reverse().map((entry) => (
            <li key={entry.revision}>
              <div>
                <strong>Revision {entry.revision}</strong>
                <span>{label(entry.operation)}</span>
                <small>
                  {entry.actor} · {entry.at.slice(0, 16).replace('T', ' ')}
                </small>
              </div>
              {entry.revision < revision ? (
                <button
                  type="button"
                  className="sw-link-button"
                  onClick={() => onRestore(entry.revision)}
                >
                  <RotateCcw size={12} /> Restore
                </button>
              ) : (
                <small>current</small>
              )}
            </li>
          ))}
        </ol>
      )}
      <p className="sw-muted">
        Restoring writes the earlier content as a new revision. Nothing is deleted and approvals are
        judged against the content again.
      </p>
    </div>
  )
}

/** Design Studio: say what you want built, watch it being designed, review it, and generate the application, in one workspace. */
export default function StudioWorkspacePage() {
  const { user, ready } = useSession()
  const { projectId: routeProject } = useParams()
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const api = useStudio(!!user)
  const { open, close, studio, projectId } = api
  const userId = user?.id ?? null
  const [leftCollapsed, setLeftCollapsed] = useState(narrow)
  const [mode, setMode] = useState<'panel' | 'dock'>(() =>
    narrow() || ['screen', 'data', 'workflow', 'export'].includes(search.get('stage') ?? '')
      ? 'dock'
      : 'panel',
  )
  const [draft, setDraft] = useState('')
  const [selection, setSelection] = useState<string | null>(null)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [autorun, setAutorun] = useState(0)
  const [designRequest, setDesignRequest] = useState<{
    id: number
    projectId: string
    brief: string
  } | null>(null)
  const designRequestCounter = useRef(0)
  const composer = useRef<HTMLTextAreaElement | null>(null)
  const stageContent = useRef<HTMLDivElement | null>(null)
  const requestedStage: StageKey = isStage(search.get('stage'))
    ? (search.get('stage') as StageKey)
    : 'brief'

  const flow = studio?.flow
  const [canvasSidebarOpen, setCanvasSidebarOpen] = useState(false)
  const stage: StageKey =
    flow && !isStage(search.get('stage'))
      ? flow.active
      : flow && requestedStage !== flow.active && !flow.reviewed.includes(requestedStage)
        ? flow.active
        : requestedStage
  const canvas = stage === 'screen' && !!studio
  const navigationCollapsed = canvas ? !canvasSidebarOpen : leftCollapsed
  useEffect(() => {
    if (stageContent.current) stageContent.current.scrollTop = 0
  }, [stage, routeProject])
  const advance = useCallback(async () => {
    if (!studio?.flow) return
    const turn = await api.continueStage(studio.flow.active)
    if (turn?.focus) navigate(`/design-studio/${api.getProjectId()}?stage=${turn.focus}`)
  }, [api, studio, navigate])

  useEffect(() => {
    if (!userId) return
    const controller = new AbortController()
    getVoiceStatus(controller.signal).then(setVoiceStatus, () => setVoiceStatus(null))
    return () => controller.abort()
  }, [userId])
  useEffect(() => {
    if (!userId) return
    if (routeProject) {
      if (routeProject !== projectId) void open(routeProject)
    } else if (projectId) close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeProject, userId])
  useEffect(() => {
    if (projectId && projectId !== routeProject)
      navigate(
        `/design-studio/${projectId}${search.get('stage') ? `?stage=${search.get('stage')}` : ''}`,
        { replace: true },
      )
  }, [projectId, routeProject, navigate, search])

  // Always address the project explicitly: a caller from an earlier render must not navigate to a path without it.
  const { getProjectId } = api
  const setStage = useCallback(
    (next: StageKey) => {
      if (studio?.flow && next !== studio.flow.active && !studio.flow.reviewed.includes(next))
        return
      navigate({
        pathname: getProjectId() ? `/design-studio/${getProjectId()}` : '/design-studio',
        search: `?stage=${next}`,
      })
    },
    [navigate, getProjectId, studio],
  )
  const speechAvailable = voiceStatus ? voiceStatus.speech.enabled : true
  const submitRef = useRef<(text: string, via: 'text' | 'voice') => void>(() => undefined)
  const voice = useVoice({
    available: speechAvailable,
    unavailableReason: voiceStatus?.speech.reason ?? 'Voice is unavailable.',
    onTranscript: (text) => submitRef.current(text, 'voice'),
  })
  const { speak } = voice
  const currentRevision = studio?.revision

  const submit = useCallback(
    async (text: string, via: 'text' | 'voice') => {
      const clean = text.trim()
      if (!clean) return
      if (
        studio?.flow &&
        /^(?:ok(?:ay)?[, ]*)?(?:continue|next|go ahead|proceed)[.! ]*$/i.test(clean)
      ) {
        api.echo(clean, via)
        await advance()
        return
      }
      const waiting = api.pending.length
      const intent = localIntent(clean, waiting)
      if (intent === 'stop') {
        voice.interrupt()
        voice.cancel()
        return
      }
      if (intent) api.echo(clean, via)
      if (intent === 'apply' && api.pending[0]) {
        const ok = await api.applyProposal(api.pending[0].id)
        if (ok) api.notice('Applied.')
        return
      }
      if (intent === 'dismiss' && api.pending[0]) {
        api.dismissProposal(api.pending[0].id)
        return
      }
      if (intent === 'undo') {
        const last = [...api.messages]
          .reverse()
          .find(
            (message) =>
              message.role === 'assistant' &&
              message.undo &&
              !message.undo.done &&
              currentRevision === message.undo.from,
          )
        if (last) {
          await api.undo(last.id)
          return
        }
      }
      const turn = await api.send(clean, via, selection, stage)
      if (!turn) return
      if (turn.focus) setStage(turn.focus)
      if (turn.focus_item) setSelection(turn.focus_item)
      if (turn.client_action === 'compile') setAutorun((value) => value + 1)
      // The assistant understood "go ahead" (in any wording or language) as moving on: press Continue for the person.
      if (turn.client_action === 'continue') await advance()
      if (turn.client_action === 'frontend' && api.getProjectId())
        setDesignRequest({
          id: ++designRequestCounter.current,
          projectId: api.getProjectId()!,
          brief: clean,
        })
      if (via === 'voice' || voice.handsFree) void speak(turn.reply)
    },
    [api, currentRevision, selection, setStage, speak, voice, studio, advance, stage],
  )
  submitRef.current = (text, via) => {
    void submit(text, via)
  }

  const ask = useCallback((text: string) => {
    setDraft(text)
    setMode('panel')
    window.setTimeout(() => composer.current?.focus(), 0)
  }, [])
  const answer = useCallback(
    (questionId: string) => {
      api.setAsked(questionId)
      setMode('panel')
      window.setTimeout(() => composer.current?.focus(), 0)
    },
    [api],
  )
  const say = useCallback(
    (text: string) => {
      setMode('panel')
      void submit(text, 'text')
    },
    [submit],
  )
  const act = useCallback(
    (actions: Record<string, unknown>[], note?: string) => {
      void api.act(actions, note).then((turn) => {
        if (turn?.focus) setStage(turn.focus)
        if (turn?.proposal) setMode('panel')
      })
    },
    [api, setStage],
  )

  const approve = useCallback(
    async (
      scope: 'process' | 'design',
      acknowledged: string[],
      comment: string,
    ): Promise<string | null> => {
      if (!projectId || !studio) return 'Open a project first.'
      try {
        await approveProject(projectId, studio.revision, scope, acknowledged, comment)
        const next = await api.refresh()
        api.notice(
          `The ${scope} is approved at revision ${(next as { revision?: number } | null)?.revision ?? studio.revision + 1}.`,
        )
        return null
      } catch (cause) {
        await api.refresh()
        return cause instanceof ApiError && cause.status !== 0
          ? cause.message
          : 'Approval failed. Nothing was approved.'
      }
    },
    [api, projectId, studio],
  )
  /** The top bar's Generate: always shows the stage (it says what is missing); runs the generator straight away only when the design allows it. */
  const generateNow = useCallback(() => {
    setStage('export')
    if (studio && studio.approval.design.state === 'valid' && studio.definition.generated_frontend)
      setAutorun((value) => value + 1)
  }, [setStage, studio])

  const asked: OpenQuestion | null = useMemo(
    () => studio?.questions.find((question) => question.id === api.asked) ?? null,
    [studio, api.asked],
  )
  const questions = useMemo(
    () =>
      (studio?.flow ? [] : (studio?.questions ?? []))
        .filter((question) => question.id !== api.asked)
        .slice(0, 3),
    [studio, api.asked],
  )
  const activity: Activity =
    voice.state === 'idle' && api.busy !== 'idle' ? 'thinking' : voice.state
  const suggestions = useMemo(() => (studio ? SUGGESTIONS[stage] : []).slice(0, 3), [studio, stage])

  if (!ready)
    return (
      <p className="sw-loading" role="status">
        Loading…
      </p>
    )
  if (!user)
    return (
      <section className="sw-loading">
        <h1>Design Studio</h1>
        <p>Sign in to describe an application and have it designed.</p>
        <Link className="sw-button sw-button--primary" to="/sign-in?next=/design-studio">
          Sign in
        </Link>
      </section>
    )

  const View = VIEWS[stage]
  const info = studio?.stages[stage]
  const stageName = STAGES.find(([key]) => key === stage)?.[1] ?? ''
  const viewProps: ViewProps | null = studio
    ? {
        studio,
        access: api.access,
        recent: api.recent,
        busy: api.busy !== 'idle',
        ask,
        answer,
        say,
        act,
        go: setStage,
        select: setSelection,
        selection,
        approve,
        resolve: api.resolve,
        refresh: api.refresh,
        userName: user.name,
        autorun,
        designRequest: designRequest?.projectId === studio.definition.id ? designRequest : null,
        onDesignRequestHandled: () => setDesignRequest(null),
      }
    : null
  const showHero = !projectId && !api.loading && !api.denied

  return (
    <div
      className="sw"
      data-stage={stage}
      data-canvas={canvas || undefined}
      data-left={navigationCollapsed ? 'collapsed' : 'open'}
      data-right={showHero ? 'hidden' : mode}
      data-hero={showHero || undefined}
    >
      <StageSidebar
        collapsed={navigationCollapsed}
        onToggle={() =>
          canvas ? setCanvasSidebarOpen((value) => !value) : setLeftCollapsed((value) => !value)
        }
        studio={studio}
        stage={stage}
        onStage={setStage}
        projects={api.projects}
        projectId={projectId}
        onOpen={(id) => navigate(`/design-studio/${id}`)}
        onNew={() => {
          close()
          navigate('/design-studio/new')
        }}
      />
      {showHero ? null : (
        <StudioTopBar
          studio={studio}
          access={api.access}
          stage={stage}
          busy={api.busy}
          leftCollapsed={navigationCollapsed}
          onOpenLeft={() => (canvas ? setCanvasSidebarOpen(true) : setLeftCollapsed(false))}
          showHistory={showHistory}
          onHistory={() => setShowHistory((value) => !value)}
          onPreview={() => setPreviewId(studio?.definition.id ?? null)}
          onGenerate={generateNow}
          onStage={setStage}
        />
      )}
      {studio && previewId === studio.definition.id && (
        <ApplicationPreviewDialog
          definition={studio.definition}
          refresh={api.refresh}
          onClose={() => setPreviewId(null)}
        />
      )}
      <main className="sw-center" id="studio-main">
        {showHero ? (
          <NewProjectHero
            voice={voice}
            activity={activity}
            voiceStatus={voiceStatus}
            draft={draft}
            onDraft={setDraft}
            onSubmit={(text, via) => void submit(text, via)}
            composer={composer}
            busy={api.busy !== 'idle'}
            error={api.error}
            projectsError={api.projectsError}
            projects={api.projects}
            onOpen={(id) => navigate(`/design-studio/${id}`)}
          />
        ) : (
          <div
            ref={stageContent}
            className="sw-center__body"
            data-busy={api.busy !== 'idle' || undefined}
          >
            {showHistory && projectId && studio ? (
              <HistoryPanel
                projectId={projectId}
                revision={studio.revision}
                onClose={() => setShowHistory(false)}
                onRestore={(revision) => {
                  void api.restore(revision)
                  setShowHistory(false)
                }}
              />
            ) : null}
            {studio && !canvas ? (
              <header className="sw-center__head">
                <ProjectHeading studio={studio} />
                {!['screen', 'data', 'workflow', 'export'].includes(stage) && (
                  <PipelineStepper studio={studio} stage={stage} onStage={setStage} />
                )}
              </header>
            ) : null}
            <VoiceStrip
              activity={activity}
              level={voice.level}
              onStop={() => {
                voice.interrupt()
                voice.cancel()
              }}
            />
            {info && !flow ? (
              <div className="sw-stagebar" data-status={info.status}>
                <h2>{stageName}</h2>
                <StatusChip status={info.status} />
                <p role="status">
                  <span className="sw-sr">{STATUS_LABEL[info.status]}: </span>
                  {info.reason}
                </p>
              </div>
            ) : null}
            {api.loading || (projectId && !studio) ? (
              <p className="sw-loading" role="status">
                {api.busy === 'creating' || api.busy === 'thinking'
                  ? 'Starting your project…'
                  : 'Opening the project…'}
              </p>
            ) : null}
            {api.denied ? (
              <AccessDenied kind={api.denied} message={api.error} />
            ) : api.error && !showHero ? (
              <div className="sw-callout sw-callout--danger" role="alert">
                <div>{api.error}</div>
              </div>
            ) : null}
            {flow &&
            stage !== 'export' &&
            (!['screen', 'data', 'workflow', 'export'].includes(stage) ||
              !flow.reviewed.includes(stage)) ? (
              <section className="sw-stage-review" aria-label="Stage review">
                <div>
                  <strong>
                    {flow.reviewed.includes(stage)
                      ? 'Reviewed stage'
                      : `${stageName} · Stage ${STAGES.findIndex(([key]) => key === stage) + 1} of ${STAGES.length}`}
                  </strong>
                  <p>
                    {flow.reviewed.includes(stage)
                      ? 'You can revisit this draft. Continue from the current stage when ready.'
                      : info?.status === 'blocked'
                        ? info.reason
                        : 'Review the draft, request changes, or continue.'}
                  </p>
                </div>
                {stage === flow.active ? (
                  <button
                    type="button"
                    className="sw-button sw-button--primary"
                    disabled={!flow.ready || api.busy !== 'idle'}
                    onClick={() => void advance()}
                  >
                    {api.busy !== 'idle' ? 'Preparing…' : 'Looks good, continue'}
                  </button>
                ) : null}
              </section>
            ) : null}
            {studio?.intake && stage === 'brief' && flow?.active === 'brief' ? (
              <OptionalSetup intake={studio.intake} busy={api.busy !== 'idle'} act={act} />
            ) : null}
            {viewProps ? (
              <View key={`${viewProps.studio.definition.id}:${stage}`} {...viewProps} />
            ) : null}
          </div>
        )}
      </main>
      {showHero || api.denied ? null : (
        <AssistantPanel
          api={api}
          access={api.access}
          voice={voice}
          voiceStatus={voiceStatus}
          mode={mode}
          onMode={setMode}
          draft={draft}
          onDraft={setDraft}
          onSubmit={(text, via) => void submit(text, via)}
          suggestions={suggestions}
          askedQuestion={asked}
          onClearAsked={() => api.setAsked(null)}
          questions={questions}
          onPickQuestion={(question) => {
            api.setAsked(question.id)
            setMode('panel')
            window.setTimeout(() => composer.current?.focus(), 0)
          }}
          onSpeak={(text) => void speak(text)}
          composer={composer}
          onNavigate={setStage}
        />
      )}
    </div>
  )
}
