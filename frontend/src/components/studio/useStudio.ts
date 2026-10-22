import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import {
  createProject,
  listProjects,
  type ApplicationDefinition,
} from '../../api/applicationDefinition'
import {
  continueStudio,
  startGuidedStudio,
  ensureOrganization,
  forgetOrganization,
  getStudioAccess,
  getStudioState,
  studioAct,
  studioApply,
  studioRevert,
  studioResolve,
  studioTurn,
  type AppliedChange,
  type StageKey,
  type StudioAccess,
  type StudioState,
  type Turn,
  type TurnResult,
} from '../../api/studio'
import { emptyDefinition } from './model/applicationDefinition'

export type ProposalStatus = 'pending' | 'applying' | 'applied' | 'dismissed' | 'stale'
export type ChatMessage =
  | { id: string; role: 'user'; text: string; via: 'text' | 'voice'; at: number }
  | {
      id: string
      role: 'assistant'
      text: string
      at: number
      turn?: Turn
      proposal?: ProposalStatus
      undo?: { from: number; to: number; done: boolean }
      notice?: boolean
      notes?: string[]
    }

export type Busy = 'idle' | 'thinking' | 'applying' | 'creating'
const KEY = (projectId: string) => `studio-conversation:${projectId}`
const MAX_MESSAGES = 60

const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
const read = (projectId: string): ChatMessage[] => {
  try {
    const raw = localStorage.getItem(KEY(projectId))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
const write = (projectId: string, messages: ChatMessage[]) => {
  try {
    localStorage.setItem(KEY(projectId), JSON.stringify(messages.slice(-MAX_MESSAGES)))
  } catch {
    /* private window or storage blocked: the conversation just is not remembered */
  }
}
const failure = (cause: unknown, fallback: string) =>
  cause instanceof ApiError && cause.status !== 0 ? cause.message : fallback

/** The workspace's state: the saved project (always from the server), the conversation about it, and every way a turn can change it. */
export function useStudio(signedIn: boolean) {
  const [projects, setProjects] = useState<ApplicationDefinition[]>([])
  const [projectsError, setProjectsError] = useState<string | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [studio, setStudio] = useState<StudioState | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState<Busy>('idle')
  const [error, setError] = useState<string | null>(null)
  const [asked, setAsked] = useState<string | null>(null)
  const [recent, setRecent] = useState<ReadonlySet<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [access, setAccess] = useState<StudioAccess | null>(null)
  const [denied, setDenied] = useState<'forbidden' | 'missing' | null>(null)
  const opening = useRef(0)
  const current = useRef<{
    projectId: string | null
    revision: number
    asked: string | null
    messages: ChatMessage[]
    hasState: boolean
  }>({ projectId: null, revision: 0, asked: null, messages: [], hasState: false })
  useEffect(() => {
    current.current = {
      projectId,
      revision: studio?.revision ?? 0,
      asked,
      messages,
      hasState: studio !== null,
    }
  })

  const remember = useCallback((id: string, next: ChatMessage[]) => {
    write(id, next)
    return next
  }, [])
  const push = useCallback(
    (id: string, ...added: ChatMessage[]) =>
      setMessages((list) =>
        current.current.projectId === id
          ? remember(id, [...list, ...added].slice(-MAX_MESSAGES))
          : list,
      ),
    [remember],
  )

  const refreshProjects = useCallback(async () => {
    try {
      await ensureOrganization()
      setProjects(await listProjects())
      setProjectsError(null)
    } catch (cause) {
      setProjects([])
      setProjectsError(
        cause instanceof ApiError && cause.status === 503
          ? 'Project storage is not available in this environment, so nothing can be saved. Start the local Design Studio to build and keep projects.'
          : failure(cause, 'Projects could not be loaded.'),
      )
    }
  }, [])
  useEffect(() => {
    if (!signedIn) {
      forgetOrganization()
      return
    }
    const timer = window.setTimeout(() => void refreshProjects(), 0)
    return () => window.clearTimeout(timer)
  }, [signedIn, refreshProjects])

  const adopt = useCallback((state: StudioState, changes: AppliedChange[] = []) => {
    if (current.current.projectId !== state.definition.id) return
    // A generation result belongs to one revision: it stays on screen only while that revision is current.
    setStudio((previous) => ({
      ...state,
      compile:
        state.compile ??
        (previous &&
        previous.definition.id === state.definition.id &&
        previous.revision === state.revision
          ? previous.compile
          : null),
    }))
    setRecent(
      new Set(
        changes.flatMap((change) => [
          change.item_id,
          change.item_id.split('/').at(-1) ?? change.item_id,
        ]),
      ),
    )
  }, [])

  const open = useCallback(async (id: string) => {
    const request = ++opening.current
    current.current = { projectId: id, revision: 0, asked: null, messages: [], hasState: false }
    setProjectId(id)
    setStudio(null)
    setMessages([])
    setLoading(true)
    setError(null)
    setDenied(null)
    setAccess(null)
    try {
      await ensureOrganization()
      let state = await getStudioState(id)
      if (request !== opening.current) return
      if (state.flow === null) {
        try {
          state = await startGuidedStudio(id, state.revision)
        } catch (cause) {
          if (cause instanceof ApiError && cause.status === 409) state = await getStudioState(id)
          else if (!(cause instanceof ApiError && cause.status === 403)) throw cause
        }
      }
      if (request !== opening.current) return
      void getStudioAccess(id).then(
        (value) => {
          if (request === opening.current) setAccess(value)
        },
        () => {
          if (request === opening.current) setAccess(null)
        },
      ) // late access from another project must not shape this project
      const stored = read(id).map((message) =>
        message.role === 'assistant' &&
        message.proposal === 'pending' &&
        message.turn?.proposal?.base_sha256 !== state.base_sha256
          ? { ...message, proposal: 'stale' as const }
          : message,
      )
      current.current = {
        projectId: id,
        revision: state.revision,
        asked: null,
        messages: stored,
        hasState: true,
      }
      setProjectId(id)
      setStudio(state)
      setMessages(stored)
      setAsked(null)
      setRecent(new Set())
    } catch (cause) {
      if (request !== opening.current) return
      setError(failure(cause, 'The project could not be opened.'))
      setProjectId(null)
      setStudio(null)
      if (cause instanceof ApiError && (cause.status === 403 || cause.status === 404))
        setDenied(cause.status === 403 ? 'forbidden' : 'missing')
    } finally {
      if (request === opening.current) setLoading(false)
    }
  }, [])

  const close = useCallback(() => {
    opening.current++
    current.current = { projectId: null, revision: 0, asked: null, messages: [], hasState: false }
    setAccess(null)
    setDenied(null)
    setProjectId(null)
    setStudio(null)
    setMessages([])
    setAsked(null)
    setError(null)
    setRecent(new Set())
  }, [])

  const refresh = useCallback(async (compile = false) => {
    const id = current.current.projectId
    if (!id) return null
    try {
      const state = await getStudioState(id, compile)
      if (current.current.projectId !== id) return null
      setStudio(state)
      return state
    } catch (cause) {
      setError(failure(cause, 'The project could not be refreshed.'))
      return null
    }
  }, [])

  /** One turn's result becomes one assistant message; the state it carries replaces the one on screen. */
  const settle = useCallback(
    (id: string, result: TurnResult) => {
      if (current.current.projectId !== id) return null
      adopt(result.state, result.turn.applied)
      setAsked(result.turn.asked_question_id)
      const undo =
        result.turn.revision > result.turn.previous_revision
          ? { from: result.turn.revision, to: result.turn.previous_revision, done: false }
          : undefined
      push(id, {
        id: uid(),
        role: 'assistant',
        text: result.turn.reply,
        at: Date.now(),
        turn: result.turn,
        proposal: result.turn.proposal ? 'pending' : undefined,
        undo,
      })
      void refreshProjects()
      return result.turn
    },
    [adopt, push, refreshProjects],
  )

  const conflict = useCallback(
    async (id: string) => {
      await refresh()
      push(id, {
        id: uid(),
        role: 'assistant',
        at: Date.now(),
        notice: true,
        text: 'The project changed while I was working, so I reloaded it. Please say that again.',
      })
    },
    [push, refresh],
  )

  /** Send what the person said (typed, or transcribed from speech they have seen) as a conversation turn. Returns the turn, or null when it failed. */
  const send = useCallback(
    async (
      text: string,
      via: 'text' | 'voice' = 'text',
      selected: string | null = null,
      stage?: StageKey,
    ): Promise<Turn | null> => {
      const clean = text.trim()
      if (!clean || busy !== 'idle') return null
      setError(null)
      let id = current.current.projectId
      let revision = current.current.revision
      const history = current.current.messages
        .filter((message) => !('notice' in message && message.notice))
        .slice(-6)
        .map((message) => ({ role: message.role, text: message.text.slice(0, 600) }))
      const userMessage: ChatMessage = { id: uid(), role: 'user', text: clean, via, at: Date.now() }
      if (!id) {
        setBusy('creating')
        try {
          await ensureOrganization()
          const created = await createProject({ ...emptyDefinition(), id: `app_${uid()}` })
          id = created.id
          revision = created.revision ?? 1
          setProjectId(id)
          setMessages([])
          setStudio(null)
          current.current = { projectId: id, revision, asked: null, messages: [], hasState: false }
        } catch (cause) {
          setBusy('idle')
          setError(
            cause instanceof ApiError && cause.status === 503
              ? 'Project storage is not available in this environment, so this project cannot be saved. Start the local Design Studio to build and keep projects.'
              : failure(cause, 'The project could not be created.'),
          )
          return null
        }
      }
      setMessages((list) =>
        remember(id!, [...(current.current.projectId === id ? list : []), userMessage]),
      )
      setBusy('thinking')
      try {
        const result = await studioTurn(id, {
          guided: true,
          stage,
          message: clean,
          expected_revision: revision,
          history,
          asked_question_id: current.current.asked,
          selected,
          input_mode: via,
        })
        return settle(id, result)
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 409) await conflict(id)
        else {
          push(id, {
            id: uid(),
            role: 'assistant',
            at: Date.now(),
            notice: true,
            text: `${failure(cause, 'I could not reach the design service. Nothing was changed.')} Your message is above; you can send it again.`,
          })
          if (!current.current.hasState) await refresh() // a brand-new project still needs its (empty) state to be shown
        }
        return null
      } finally {
        setBusy('idle')
      }
    },
    [busy, conflict, push, refresh, remember, settle],
  )

  const continueStage = useCallback(
    async (stage: StageKey) => {
      const id = current.current.projectId
      if (!id || busy !== 'idle') return null
      setBusy('thinking')
      setError(null)
      try {
        return settle(id, await continueStudio(id, current.current.revision, stage))
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 409) await refresh()
        setError(failure(cause, 'The next stage could not be prepared. Please try again.'))
        return null
      } finally {
        setBusy('idle')
      }
    },
    [busy, settle, refresh],
  )

  /** A direct change from a button on a view: the same typed actions, no language model. */
  const act = useCallback(
    async (actions: Record<string, unknown>[], note = ''): Promise<Turn | null> => {
      const id = current.current.projectId
      if (!id || busy !== 'idle') return null
      setBusy('applying')
      setError(null)
      try {
        return settle(id, await studioAct(id, current.current.revision, actions, note))
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 409) await conflict(id)
        else setError(failure(cause, 'That change could not be made. Nothing was changed.'))
        return null
      } finally {
        setBusy('idle')
      }
    },
    [busy, conflict, settle],
  )

  const applyProposal = useCallback(
    async (messageId: string): Promise<boolean> => {
      const id = current.current.projectId
      const message = current.current.messages.find((item) => item.id === messageId)
      if (
        !id ||
        message?.role !== 'assistant' ||
        !message.turn?.proposal ||
        message.proposal !== 'pending' ||
        busy !== 'idle'
      )
        return false
      setMessages((list) =>
        list.map((item) =>
          item.id === messageId && item.role === 'assistant'
            ? { ...item, proposal: 'applying' as const }
            : item,
        ),
      )
      setBusy('applying')
      try {
        const result = await studioApply(id, message.turn.proposal, current.current.revision)
        if (current.current.projectId !== id) return false
        adopt(result.state, result.changes)
        setMessages((list) =>
          remember(id, [
            ...list.map((item) =>
              item.id === messageId && item.role === 'assistant'
                ? { ...item, proposal: 'applied' as const }
                : item,
            ),
            {
              id: uid(),
              role: 'assistant' as const,
              at: Date.now(),
              notice: true,
              text: `Applied ${result.changes.length} change${result.changes.length === 1 ? '' : 's'}.`,
              undo: { from: result.state.revision, to: result.previous_revision, done: false },
              notes: result.notes ?? [],
            },
          ]),
        )
        void refreshProjects()
        return true
      } catch (cause) {
        const stale = cause instanceof ApiError && cause.status === 409
        setMessages((list) =>
          remember(
            id,
            list.map((item) =>
              item.id === messageId && item.role === 'assistant'
                ? { ...item, proposal: stale ? ('stale' as const) : ('pending' as const) }
                : item,
            ),
          ),
        )
        if (stale) await refresh()
        else setError(failure(cause, 'The change could not be applied. Nothing was changed.'))
        return false
      } finally {
        setBusy('idle')
      }
    },
    [adopt, busy, refresh, refreshProjects, remember],
  )

  const dismissProposal = useCallback(
    (messageId: string) => {
      const id = current.current.projectId
      if (!id) return
      setMessages((list) =>
        remember(
          id,
          list.map((item) =>
            item.id === messageId && item.role === 'assistant' && item.proposal === 'pending'
              ? { ...item, proposal: 'dismissed' as const }
              : item,
          ),
        ),
      )
    },
    [remember],
  )

  /** Undo restores the earlier content as a new revision; history is kept. */
  const undo = useCallback(
    async (messageId: string): Promise<boolean> => {
      const id = current.current.projectId
      const message = current.current.messages.find((item) => item.id === messageId)
      if (
        !id ||
        message?.role !== 'assistant' ||
        !message.undo ||
        message.undo.done ||
        busy !== 'idle'
      )
        return false
      setBusy('applying')
      try {
        const result = await studioRevert(id, current.current.revision, message.undo.to)
        if (current.current.projectId !== id) return false
        adopt(result.state)
        setMessages((list) =>
          remember(id, [
            ...list.map((item) =>
              item.id === messageId && item.role === 'assistant' && item.undo
                ? { ...item, undo: { ...item.undo, done: true } }
                : item,
            ),
            {
              id: uid(),
              role: 'assistant' as const,
              at: Date.now(),
              notice: true,
              text: `Restored the content of revision ${result.restored_from} as revision ${result.state.revision}. Nothing was lost; both are in the history.`,
            },
          ]),
        )
        void refreshProjects()
        return true
      } catch (cause) {
        setError(failure(cause, 'The change could not be undone.'))
        return false
      } finally {
        setBusy('idle')
      }
    },
    [adopt, busy, refreshProjects, remember],
  )

  const restore = useCallback(
    async (toRevision: number) => {
      const id = current.current.projectId
      if (!id || busy !== 'idle') return false
      setBusy('applying')
      try {
        const result = await studioRevert(id, current.current.revision, toRevision)
        if (current.current.projectId !== id) return false
        adopt(result.state)
        push(id, {
          id: uid(),
          role: 'assistant',
          at: Date.now(),
          notice: true,
          text: `Restored the content of revision ${toRevision} as revision ${result.state.revision}.`,
        })
        return true
      } catch (cause) {
        setError(failure(cause, 'That revision could not be restored.'))
        return false
      } finally {
        setBusy('idle')
      }
    },
    [adopt, busy, push],
  )

  /** Let the Studio settle the validation findings it can settle by itself, as one revision. Returns what it changed. */
  const resolve = useCallback(async (): Promise<string[] | null> => {
    const id = current.current.projectId
    if (!id || busy !== 'idle') return null
    setBusy('applying')
    try {
      const result = await studioResolve(id, current.current.revision)
      if (current.current.projectId !== id) return null
      if (!result.changes.length) return []
      adopt(result.state)
      push(id, {
        id: uid(),
        role: 'assistant',
        at: Date.now(),
        notice: true,
        text: [
          `Resolved ${result.changes.length} validation issue${result.changes.length === 1 ? '' : 's'} automatically:`,
          ...result.changes.map((change) => `• ${change}`),
          ...result.stale,
        ].join('\n'),
      })
      return result.changes
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) await conflict(id)
      else setError(failure(cause, 'The issues could not be resolved. Nothing was changed.'))
      return null
    } finally {
      setBusy('idle')
    }
  }, [adopt, busy, conflict, push])

  /** Show what the person said in the conversation without sending it on (a spoken "apply" is shown, then acted on, never hidden). */
  const echo = useCallback(
    (text: string, via: 'text' | 'voice') => {
      const id = current.current.projectId
      if (id) push(id, { id: uid(), role: 'user', text, via, at: Date.now() })
    },
    [push],
  )

  /** The project open right now, read at call time (not from the render that created the caller). */
  const getProjectId = useCallback(() => current.current.projectId, [])

  const notice = useCallback(
    (text: string) => {
      const id = current.current.projectId
      if (id) push(id, { id: uid(), role: 'assistant', at: Date.now(), notice: true, text })
    },
    [push],
  )

  const pending = useMemo(
    () =>
      messages.filter(
        (message): message is Extract<ChatMessage, { role: 'assistant' }> =>
          message.role === 'assistant' && message.proposal === 'pending',
      ),
    [messages],
  )
  return {
    projects: signedIn ? projects : [],
    projectsError,
    projectId,
    studio,
    access,
    denied,
    messages,
    busy,
    error,
    setError,
    asked,
    setAsked,
    recent,
    loading,
    pending,
    open,
    close,
    refresh,
    refreshProjects,
    send,
    continueStage,
    act,
    applyProposal,
    dismissProposal,
    undo,
    restore,
    resolve,
    notice,
    echo,
    getProjectId,
    adopt,
  }
}

export type StudioApi = ReturnType<typeof useStudio>
export type { StageKey }
