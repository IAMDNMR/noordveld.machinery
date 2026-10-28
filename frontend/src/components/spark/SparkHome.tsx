import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowUp,
  ArrowUpRight,
  Mic,
  ShoppingBag,
  Square,
  Volume2,
  X,
  PanelLeft,
  Copy,
  RotateCcw,
  ArrowDown,
} from 'lucide-react'
import {
  askSpark,
  sparkSpeak,
  sparkTranscribe,
  sparkVoiceStatus,
  type SparkResponse,
} from '../../api/spark'
import {
  orderTurn,
  type OrderResponse,
  type OrderSlots,
  type OrderTurnBody,
} from '../../api/sparkOrder'
import { ApiError, getActiveOrganization } from '../../api/client'
import { ResultView } from '../intelligence/ResultView'
import { PartWorkspace, TABS } from '../intelligence/PartWorkspace'
import { getSuggestions, type PartTab } from '../../api'
import { getAgentSuggestions } from '../../api/agent'
import { ShoppingResult } from '../../pages/AgenticShoppingPage'
import { CommerceAnswer, optionText } from '../commerce/CommerceWorkspace'
import { CartDrawer } from '../store/CartDrawer'
import { CartProvider, useCart } from '../../store/CartContext'
import { SPARK_CHAT_ROUTE } from '../../data/content'
import { useSession } from '../../store/session'
import { useVoice } from '../voice/useVoice'
import { useApi } from '../../hooks/useApi'
import { ChatSidebar } from './ChatSidebar'
import { AnswerText } from './AnswerText'
import { AnswerSources } from './AnswerSources'
import { readPresentation } from './AnswerBlocks'
import { OrderDraftBar, OrderJourney, type OrderChange } from './OrderJourney'
import { SparkLogo } from './SparkLogo'
import { conversationKey, useChatHistory, type ChatHistory } from './useChatHistory'
import '../../styles/wf.css'
import '../intelligence/intelligence.css'
import '../agent/agent.css'
import './spark.css'
import './spark-ui.css'
import './spark-present.css'

type Turn = {
  id: number
  question: string
  response: SparkResponse
  restored?: boolean
  /** asked by voice: shown with a microphone mark, and the reply is spoken */
  spoken?: boolean
  at?: number
  /** A step of the guided order journey. The server re-validates its slots on every turn. */
  order?: OrderResponse
}
const emptyResponse = (message: string): SparkResponse => ({
  message,
  context: '',
  view: 'answer',
  intelligence: null,
  shopping: null,
  account: null,
  sign_in_required: false,
  warnings: [],
  steps: [],
})
/** The latest order step, while that journey is still open (more input expected, nothing final yet).
 *  A question Spark answers in between does not close it: the order and the chat share this one state. */
const openOrderTurn = (turns: Turn[]) => {
  const turn = [...turns].reverse().find((item) => item.order)
  return turn?.order && turn.order.stage !== 'placed' && (!turn.order.blocked || turn.order.ask)
    ? turn
    : null
}
const openOrder = (turns: Turn[]) => openOrderTurn(turns)?.order ?? null
const orderLabel = (order: OrderResponse) =>
  order.part && typeof order.slots.part_id === 'string'
    ? { part_id: order.slots.part_id, label: order.part.part_number }
    : null
/** Starter questions come from the backend's own suggestions; only the account one is fixed text. */
const ACCOUNT_STARTER = { topic: 'Your account', text: 'Where is my last order?' }
const FALLBACK_STARTERS = [
  { topic: 'Parts', text: 'Help me find the right part for my machine' },
  { topic: 'Fitment', text: 'Which machines does a part I name fit?' },
  { topic: 'Suppliers', text: 'Who can supply a part, and how fast can they deliver?' },
]
const VOICE_TRANSPORT = { transcribe: sparkTranscribe, synthesize: sparkSpeak }

function restoreConversation(key: string): Turn[] {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(key) ?? '[]')
    if (!Array.isArray(saved)) return []
    return saved.flatMap((item) => {
      if (
        !item ||
        typeof item.question !== 'string' ||
        typeof item.summary !== 'string' ||
        typeof item.context !== 'string'
      )
        return []
      return [
        {
          id: typeof item.id === 'number' ? item.id : 0,
          question: item.question,
          restored: true,
          at: typeof item.at === 'number' ? item.at : undefined,
          order:
            item.order && typeof item.order.stage === 'string' && Array.isArray(item.order.stages)
              ? (item.order as OrderResponse)
              : undefined,
          response:
            item.version === 2 &&
            item.response &&
            typeof item.response.message === 'string' &&
            item.response.context === item.context &&
            Array.isArray(item.response.steps) &&
            Array.isArray(item.response.warnings)
              ? (item.response as SparkResponse)
              : {
                  message: item.summary,
                  context: item.context,
                  view: 'answer' as const,
                  intelligence: null,
                  shopping: null,
                  account: null,
                  sign_in_required: false,
                  warnings: [],
                  steps: [],
                },
        },
      ]
    })
  } catch {
    return []
  }
}

function summary(response: SparkResponse) {
  return [
    response.message,
    response.intelligence?.answer.summary,
    response.shopping?.question ?? response.shopping?.reason,
    response.account?.answer.text,
  ]
    .filter(Boolean)
    .join(' ')
}

export function SparkHome() {
  const { user } = useSession()
  const [organization, setOrganization] = useState(getActiveOrganization)
  useEffect(() => {
    const changed = () => setOrganization(getActiveOrganization())
    window.addEventListener('active-organization', changed)
    return () => window.removeEventListener('active-organization', changed)
  }, [])
  const identity = `${user?.id ?? 'anonymous'}${organization ? `:${organization}` : ''}`
  return <SparkLibrary key={identity} identity={identity} />
}

function SparkLibrary({ identity }: { identity: string }) {
  const history = useChatHistory(identity)
  return (
    <CartProvider>
      <SparkConversation key={history.active} identity={identity} history={history} />
      <CartDrawer />
    </CartProvider>
  )
}

function SparkConversation({ identity, history }: { identity: string; history: ChatHistory }) {
  const [params, setParams] = useSearchParams()
  const { ready } = useSession()
  const storageKey = conversationKey(identity, history.active)
  const { count, setOpen } = useCart()
  const [turns, setTurns] = useState<Turn[]>(() => restoreConversation(storageKey))
  const [draft, setDraft] = useState(() => {
    try {
      return sessionStorage.getItem(`${storageKey}:draft`) ?? ''
    } catch {
      return ''
    }
  })
  const [sidebarOpen, setSidebarOpen] = useState(
    () => window.matchMedia?.('(min-width: 1001px)').matches ?? true,
  )
  useEffect(() => {
    if (!sidebarOpen) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) {
        setSidebarOpen(false)
        input.current?.focus()
      }
    }
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [sidebarOpen])
  const [copied, setCopied] = useState<number | null>(null)
  const [copyError, setCopyError] = useState('')
  const [away, setAway] = useState(false)
  const nearBottom = useRef(true)
  const [saveError, setSaveError] = useState(false)
  const [dictated, setDictated] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<{
    question: string
    status: 'working' | 'stopped' | 'failed'
  } | null>(null)
  const [failed, setFailed] = useState<{ text: string; message: string; expired: boolean } | null>(
    null,
  )
  const [part, setPart] = useState<{ key: string; tab: PartTab } | null>(null)
  const memory = useRef<string | null>(turns.at(-1)?.response.context ?? null)
  const controller = useRef<AbortController | null>(null)
  const locked = useRef(false)
  const sequence = useRef(turns.at(-1)?.id ?? 0)
  const input = useRef<HTMLTextAreaElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  const partDialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    input.current?.focus()
    const media = window.matchMedia?.('(max-width: 1000px)')
    const changed = (event: MediaQueryListEvent) => setSidebarOpen(!event.matches)
    media?.addEventListener?.('change', changed)
    return () => media?.removeEventListener?.('change', changed)
  }, [])
  const initialSent = useRef(false)
  const restoredQuestions = useRef(turns.map((turn) => turn.question.trim().toLowerCase()))
  const inputId = useId()
  const availability = useApi(sparkVoiceStatus, 'spark-voice')
  const questions = useApi((signal) => getSuggestions(signal), 'suggestions')
  const requests = useApi((signal) => getAgentSuggestions(signal), 'agent-suggestions')
  const starters = [
    ...(questions.data?.length
      ? [...new Map(questions.data.map((item) => [item.category, item])).values()]
          .slice(0, 2)
          .map((item) => ({ topic: item.category, text: item.question }))
      : FALLBACK_STARTERS.slice(0, 2)),
    {
      topic: 'Buying',
      text: requests.data?.[0]?.request ?? 'Help me compare buying options for a part',
    },
    ACCOUNT_STARTER,
  ]
  const voiceMode = availability.data?.mode ?? 'dictate'
  const voice = useVoice({
    available: availability.data?.enabled ?? false,
    unavailableReason: availability.data?.reason ?? 'Checking voice availability…',
    transport: VOICE_TRANSPORT,
    onTranscript: (text) => {
      // hands-free: the spoken message goes into the same conversation as typing and is answered aloud;
      // dictate (SPARK_VOICE_MODE=dictate, the rollback) or a request still running: it waits in the box for Send
      if (voiceMode === 'hands_free' && !locked.current) {
        void sendRef.current(text.slice(0, 500), [], 12, undefined, true)
        return
      }
      setDraft(text.slice(0, 500))
      setDictated(true)
      input.current?.focus()
    },
  })
  const speakRef = useRef(voice.speak)
  useEffect(() => {
    speakRef.current = voice.speak
  }, [voice.speak])

  const queuedOrder = useRef<{ question: string; body: OrderTurnBody; spoken: boolean } | null>(
    null,
  )
  const runOrderRef = useRef<
    ((question: string, body: OrderTurnBody, spoken?: boolean) => Promise<void>) | null
  >(null)
  const turnsRef = useRef(turns)
  useEffect(() => {
    turnsRef.current = turns
  }, [turns])
  const orderKey = useCallback(() => {
    const name = `${storageKey}:order-key`
    try {
      return (
        sessionStorage.getItem(name) ??
        (sessionStorage.setItem(name, crypto.randomUUID()), sessionStorage.getItem(name)!)
      )
    } catch {
      return crypto.randomUUID()
    }
  }, [storageKey])
  const appendOrder = useCallback(
    (question: string, order: OrderResponse, spoken = false) => {
      if (order.order) {
        try {
          sessionStorage.removeItem(`${storageKey}:order-key`)
        } catch {
          /* a new key is generated on the next order */
        }
      }
      setTurns((previous) => [
        ...previous,
        {
          id: ++sequence.current,
          question,
          response: emptyResponse(order.message),
          order,
          at: Date.now(),
          spoken,
        },
      ])
      setPending(null)
      if (order.message) void speakRef.current(order.message.slice(0, 1500), spoken)
    },
    [storageKey],
  )
  const send = useCallback(
    async (
      text: string,
      selected: { kind: string; key: string }[] = [],
      limit = 12,
      context?: string,
      spoken = false,
    ) => {
      if (!text.trim() || locked.current || !ready) return
      locked.current = true
      setBusy(true)
      nearBottom.current = true
      setAway(false)
      setPending({ question: text.trim(), status: 'working' })
      setFailed(null)
      setDraft('')
      setDictated(false)
      const request = new AbortController()
      controller.current = request
      try {
        const journey = openOrder(turnsRef.current)
        // typing "2" picks the second listed choice, same as clicking it
        const listed = journey?.ask?.choices ?? []
        const picked = /^\d{1,2}$/.test(text.trim()) ? listed[Number(text.trim()) - 1] : undefined
        if (journey && picked) {
          const reply = await orderTurn(
            {
              slots: journey.slots,
              patch: picked.patch,
              ...(picked.confirm ? { confirm: true } : {}),
            },
            request.signal,
          )
          if (!request.signal.aborted) appendOrder(text.trim(), reply, spoken)
          return
        }
        if (journey && context === undefined && !selected.length) {
          const reply = await orderTurn(
            { slots: journey.slots, message: text.trim() },
            request.signal,
          )
          if (request.signal.aborted) return
          if (reply.handled && reply.confirm_ready && journey.summary) {
            // "yes" to the summary just shown: place it with that summary's total; the server re-checks price and stock
            queuedOrder.current = {
              question: text.trim(),
              body: {
                slots: reply.slots,
                confirm: true,
                reviewed_total: journey.summary.total ?? null,
                idempotency_key: orderKey(),
              },
              spoken,
            }
            return
          }
          if (reply.handled) {
            appendOrder(text.trim(), reply, spoken)
            return
          }
        }
        const response = await askSpark(
          text.trim(),
          context ?? memory.current,
          selected,
          limit,
          request.signal,
          journey ? orderLabel(journey) : null,
        )
        if (request.signal.aborted) return
        memory.current = response.context
        const id = ++sequence.current
        setTurns((previous) => [
          ...previous,
          { id, question: text.trim(), response, at: Date.now(), spoken },
        ])
        setPending(null)
        const wanted = response.order_part
        if (wanted) {
          const carry = wanted.patch ?? {}
          queuedOrder.current = !journey
            ? // a new order keeps what the user already said: the shopping details and this message
              {
                question: '', // Spark continues on its own: no message the user did not type
                // auto: Spark fills every step it can and asks only for what is missing
                body: {
                  slots: { part_id: wanted.part_id },
                  patch: { ...carry, auto: true },
                  message: text.trim(),
                },
                spoken,
              }
            : journey.slots.part_id === wanted.part_id
              ? // the part already being ordered: continue at the current step, nothing restarts
                {
                  question: `Continue ordering ${wanted.label}`,
                  body: { slots: journey.slots },
                  spoken,
                }
              : // another part: same order, every choice kept; fitment, price, stock and routes are re-checked
                {
                  question: `Change the part to ${wanted.label}`,
                  body: { slots: journey.slots, patch: { ...carry, part_id: wanted.part_id } },
                  spoken,
                }
        }
        // when an order step follows, that step's reply is the one spoken
        const reply = summary(response)
        if (reply && !wanted) void speakRef.current(reply.slice(0, 1500), spoken)
      } catch (error) {
        if (request.signal.aborted) return
        setDraft((current) => (current.trim() ? current : text))
        setPending({ question: text.trim(), status: 'failed' })
        setFailed({
          text,
          message:
            error instanceof ApiError
              ? error.message
              : 'Spark could not connect. Your conversation is still here.',
          expired: error instanceof ApiError && error.code === 'spark_context_expired',
        })
      } finally {
        if (controller.current === request) {
          locked.current = false
          setBusy(false)
          input.current?.focus()
        }
        const queued = queuedOrder.current
        queuedOrder.current = null
        if (queued) void runOrderRef.current?.(queued.question, queued.body, queued.spoken)
      }
    },
    [ready, appendOrder, orderKey],
  )
  const runOrder = useCallback(
    async (question: string, body: OrderTurnBody, spoken = false) => {
      if (locked.current || !ready) return
      locked.current = true
      setBusy(true)
      nearBottom.current = true
      setFailed(null)
      setPending({ question, status: 'working' })
      const request = new AbortController()
      controller.current = request
      try {
        const response = await orderTurn(body, request.signal)
        if (!request.signal.aborted) appendOrder(question, response, spoken)
      } catch (error) {
        if (request.signal.aborted) return
        setPending(null)
        setFailed({
          text: question,
          expired: false,
          message:
            error instanceof ApiError && error.status === 401
              ? 'Sign in to order parts with Spark. Your conversation is still here.'
              : error instanceof ApiError
                ? error.message
                : 'Spark could not reach the ordering service. Nothing was ordered. Try again.',
        })
      } finally {
        if (controller.current === request) {
          locked.current = false
          setBusy(false)
        }
      }
    },
    [ready, appendOrder],
  )
  useEffect(() => {
    runOrderRef.current = runOrder
  }, [runOrder])
  const chooseOrder = useCallback<OrderChange>(
    (patch, choice, revisit) => {
      const current = openOrder(turnsRef.current)
      if (!current) return
      const label =
        choice?.label ??
        Object.values(patch)
          .filter((value) => value !== null)
          .join(' · ')
      const confirm = choice?.confirm === true
      void runOrder(label || 'Continue', {
        slots: current.slots,
        patch: confirm ? {} : patch,
        confirm,
        reviewed_total: confirm ? (current.summary?.total ?? null) : undefined,
        idempotency_key: confirm ? orderKey() : undefined,
        ...(revisit ? { revisit } : {}),
      })
    },
    [runOrder, orderKey],
  )
  const sendRef = useRef(send)
  useEffect(() => {
    sendRef.current = send
  }, [send])
  useEffect(() => {
    const q = params.get('q')
    if (!q || !ready || initialSent.current) return
    // A reload of a bookmarked question restores the conversation; do not ask it twice
    if (restoredQuestions.current.includes(q.trim().toLowerCase())) {
      initialSent.current = true
      return
    }
    const timer = setTimeout(() => {
      initialSent.current = true
      void sendRef.current(q.slice(0, 500))
    }, 0)
    return () => clearTimeout(timer)
  }, [params, ready])
  const startedOrder = useRef<string | null>(null)
  useEffect(() => {
    const partId = params.get('order')
    if (!partId || !ready || startedOrder.current === partId) return
    startedOrder.current = partId
    const resume = openOrder(turns)
    const next = new URLSearchParams(params)
    next.delete('order')
    next.delete('qty')
    next.delete('machine')
    setParams(next, { replace: true })
    // a reload of the same link resumes the open journey instead of starting another
    if (resume && resume.slots.part_id === partId) return
    const qty = Number(params.get('qty'))
    const machine = params.get('machine')
    const patch: OrderSlots = {
      ...(Number.isInteger(qty) && qty > 0 && qty < 100 ? { quantity: qty } : {}),
      ...(machine ? { machine } : {}),
    }
    setTimeout(
      () =>
        void runOrder('Order this part', {
          slots: { part_id: partId },
          patch: { ...patch, auto: true },
        }),
      0,
    )
  }, [params, ready, turns, runOrder, setParams])
  useEffect(() => () => controller.current?.abort(), [])
  // Part links inside answers open the part over the conversation instead of leaving it
  useEffect(() => {
    const node = thread.current
    const open = (event: MouseEvent) => {
      const href = (event.target as Element).closest('a')?.getAttribute('href')
      if (!href?.startsWith(`${SPARK_CHAT_ROUTE}?`)) return
      const query = new URLSearchParams(href.slice(href.indexOf('?')))
      const key = query.get('part')
      if (!key || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return
      event.preventDefault()
      setPart({ key, tab: TABS.find((tab) => tab.id === query.get('tab'))?.id ?? 'overview' })
    }
    node?.addEventListener('click', open)
    return () => node?.removeEventListener('click', open)
  }, [])
  const updateHistory = history.update
  useEffect(() => {
    try {
      sessionStorage.setItem(`${storageKey}:draft`, draft || pending?.question || '')
    } catch {
      queueMicrotask(() => setSaveError(true))
    }
  }, [draft, pending, storageKey])
  useEffect(() => {
    if (!turns.length) return
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify(
          turns.map((turn) => ({
            id: turn.id,
            question: turn.question,
            summary: summary(turn.response),
            context: turn.response.context,
            version: 2,
            at: turn.at,
            order: turn.order,
            // Account answers are refreshed through the authorized API, never restored as records.
            response: {
              ...turn.response,
              account: null,
              message: turn.response.account ? summary(turn.response) : turn.response.message,
            },
          })),
        ),
      )
      queueMicrotask(() => setSaveError(false))
    } catch {
      queueMicrotask(() => setSaveError(true))
    }
    updateHistory(
      history.active,
      turns[0].question,
      turns.map((turn) => `${turn.question}\n${summary(turn.response)}`).join('\n'),
    )
  }, [turns, storageKey, updateHistory, history.active])
  useEffect(() => {
    if ((turns.length || busy || failed) && nearBottom.current) {
      thread.current?.scrollTo({
        top: thread.current.scrollHeight,
        behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
      })
    }
  }, [turns.length, busy, failed])

  const reset = (newDraft = '') => {
    controller.current?.abort()
    voice.cancel()
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
    history.create(newDraft)
  }
  const selectChat = (id: string) => {
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
    history.select(id)
  }
  useEffect(() => {
    const dialog = partDialog.current
    if (part && dialog && !dialog.open) dialog.showModal()
    if (!part && dialog?.open) dialog.close()
  }, [part])
  const submit = (event: FormEvent) => {
    event.preventDefault()
    voice.interrupt()
    void send(draft)
  }
  const openTurn = openOrderTurn(turns)
  return (
    <div
      className={`spark-workspace spark-workspace--redesign wf${sidebarOpen ? ' has-sidebar' : ''}`}
    >
      {sidebarOpen ? (
        <button
          className="spark-sidebar-backdrop"
          aria-label="Dismiss chat history"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}
      <ChatSidebar
        open={sidebarOpen}
        history={{ ...history, create: () => reset(), select: selectChat }}
        busy={busy}
        onClose={() => {
          setSidebarOpen(false)
          input.current?.focus()
        }}
      />
      <header className="spark-toolbar">
        <button
          type="button"
          className="spark-history-toggle"
          aria-label="Toggle chat history"
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((value) => !value)}
        >
          <PanelLeft size={19} />
        </button>
        <div className="spark-brand">
          <SparkLogo size={30} />
          <div>
            <h1>Spark</h1>
            <p>Parts intelligence & commerce</p>
          </div>
        </div>
        <div className="spark-toolbar__actions">
          <Link to="/spark">About Spark</Link>
          <Link to="/profile">My profile</Link>
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label={`Open cart, ${count} items`}
          >
            <ShoppingBag size={17} aria-hidden="true" />
            <span>Cart{count ? ` (${count})` : ''}</span>
          </button>
        </div>
      </header>
      <div
        className="spark-thread"
        ref={thread}
        role="region"
        aria-label="Conversation with Spark"
        aria-busy={busy}
        onScroll={() => {
          const node = thread.current
          if (!node) return
          nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 120
          setAway(!nearBottom.current)
        }}
      >
        {!turns.length && !busy && !failed ? (
          <div className="spark-welcome">
            <SparkLogo size={76} className="spark-welcome__logo" />
            <p className="spark-kicker">Spark</p>
            <h2>Let’s find your next step.</h2>
            <p>
              Start with a part, a machine or the job at hand. We’ll work through the details
              together.
            </p>
            <ul className="spark-starters" aria-label="Example questions">
              {starters.map((starter) => (
                <li key={starter.text}>
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(starter.text)
                      input.current?.focus()
                    }}
                  >
                    <span>{starter.topic}</span>
                    {starter.text}
                    <ArrowUpRight size={16} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="spark-turns">
          {turns.map((turn, index) => {
            const shown = readPresentation(turn.response.presentation)
            return (
              <article className="spark-turn" key={turn.id}>
                <h2 className="spark-question" hidden={!turn.question}>
                  {turn.spoken ? (
                    <Mic size={14} className="spark-question__mic" aria-label="Spoken" />
                  ) : null}
                  {turn.question}
                </h2>
                <div className="spark-answer">
                  {turn.restored ? (
                    <p className="spark-compose-note">
                      Earlier reply · availability and prices may have changed. Ask Spark to
                      refresh.
                    </p>
                  ) : null}
                  {turn.order ? (
                    <OrderJourney
                      order={turn.order}
                      active={turn.id === openTurn?.id}
                      busy={busy}
                      onPatch={chooseOrder}
                    />
                  ) : turn.response.message ? (
                    <AnswerText text={turn.response.message} />
                  ) : null}
                  {turn.response.profile_used?.length ? (
                    <p className="so-prefilled">
                      Used from your saved profile: {turn.response.profile_used.join(', ')}.{' '}
                      <Link to="/profile">Manage profile</Link>
                    </p>
                  ) : null}
                  {turn.response.presentation?.note ? (
                    <p className="spark-present-note">{turn.response.presentation.note}</p>
                  ) : null}
                  {turn.response.intelligence ? (
                    <ResultView
                      conversational
                      format={shown.format}
                      table={shown.table}
                      chart={shown.chart}
                      response={turn.response.intelligence}
                      suggestions={null}
                      limit={turn.response.intelligence.results.length || 12}
                      maxLimit={40}
                      showGraph={turn.response.view === 'graph'}
                      onInvestigate={(key) => setPart({ key, tab: 'overview' })}
                      onAsk={(q) => void send(q)}
                      onSelect={(selected) =>
                        void send(turn.question, [selected], 12, turn.response.context)
                      }
                      onMore={() =>
                        void send(
                          turn.question,
                          [],
                          Math.min(40, turn.response.intelligence!.results.length + 12),
                          turn.response.context,
                        )
                      }
                    />
                  ) : null}
                  {turn.response.shopping ? (
                    <ShoppingResult
                      conversational
                      format={turn.response.presentation?.shopping ?? undefined}
                      r={turn.response.shopping}
                      onRefine={(extra) => void send(extra || 'Please show other buying options')}
                    />
                  ) : null}
                  {turn.response.account ? (
                    <CommerceAnswer
                      turn={{
                        id: turn.id,
                        question: turn.question,
                        response: turn.response.account,
                      }}
                      dim={busy}
                      onChoose={(option) => void send(optionText(option))}
                      onAsk={(q) => void send(q)}
                      typeHint="Answer below and Spark will continue this request."
                      format={turn.response.presentation?.account ?? undefined}
                    />
                  ) : null}
                  {turn.response.sign_in_required ? (
                    <p className="spark-notice">
                      Your orders, shipments and warranty need your account.{' '}
                      <Link to={`/sign-in?next=${encodeURIComponent(SPARK_CHAT_ROUTE)}`}>
                        Sign in to continue
                      </Link>
                    </p>
                  ) : null}
                  {turn.response.warnings.map((warning) => (
                    <p className="spark-notice" key={warning}>
                      {warning}
                    </p>
                  ))}
                  {index === turns.length - 1 && turn.response.warnings.length ? (
                    <button
                      type="button"
                      className="spark-text-button"
                      disabled={busy}
                      onClick={() => void send(turn.question)}
                    >
                      Retry this request
                    </button>
                  ) : null}
                  <AnswerSources response={turn.response} at={turn.at} />
                  {/* a step of the guided order is a short exchange, not an answer worth copying */}
                  {turn.order && !turn.order.order ? null : (
                    <div className="spark-response-actions">
                      <button
                        type="button"
                        aria-label="Copy answer"
                        onClick={async () => {
                          const text = [
                            summary(turn.response),
                            ...(turn.response.intelligence?.results ?? []).map(
                              (item) =>
                                `${item.title}${item.subtitle ? ` — ${item.subtitle}` : ''}\n${item.facts.map((fact) => `${fact.label}: ${fact.value ?? 'Not recorded'}`).join('\n')}`,
                            ),
                          ]
                            .filter(Boolean)
                            .join('\n\n')
                          try {
                            await navigator.clipboard.writeText(text)
                            setCopied(turn.id)
                            setCopyError('')
                          } catch {
                            setCopyError(
                              'Copy is unavailable. You can select and copy the answer text.',
                            )
                          }
                        }}
                      >
                        <Copy size={15} />
                        {copied === turn.id ? 'Copied' : 'Copy'}
                      </button>
                      {index === turns.length - 1 && !turn.order ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void send(turn.question, [], 12, turn.response.context)}
                        >
                          <RotateCcw size={15} /> Regenerate
                        </button>
                      ) : null}
                    </div>
                  )}
                </div>
              </article>
            )
          })}
          {pending ? (
            <article className="spark-turn">
              <h2 className="spark-question" hidden={!pending.question}>
                {pending.question}
              </h2>
              {pending.status === 'working' ? (
                <div className="spark-pending">
                  <p role="status">Spark is working on your request…</p>
                  <div className="spark-skeleton" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              ) : pending.status === 'stopped' ? (
                <p className="spark-compose-note" role="status">
                  Request stopped. You can ask again or send a different question.
                </p>
              ) : null}
            </article>
          ) : null}
          {failed ? (
            <div className="spark-error" role="alert">
              <p>{failed.message}</p>
              <button
                type="button"
                onClick={() => {
                  if (failed.expired) {
                    const question = failed.text
                    reset(question)
                  } else {
                    void send(failed.text)
                  }
                }}
              >
                {failed.expired ? 'Start a new conversation' : 'Try again'}
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="spark-compose-wrap">
        {away ? (
          <button
            type="button"
            className="spark-jump"
            onClick={() => {
              thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: 'instant' })
              nearBottom.current = true
              setAway(false)
            }}
          >
            <ArrowDown size={15} /> Latest messages
          </button>
        ) : null}
        {openTurn?.order && openTurn.order.slots.auto !== true ? (
          <OrderDraftBar order={openTurn.order} />
        ) : null}
        <form className="spark-compose" onSubmit={submit}>
          <label className="sr-only" htmlFor={inputId}>
            Message Spark
          </label>
          <textarea
            ref={input}
            id={inputId}
            value={draft}
            maxLength={500}
            rows={1}
            placeholder="Ask Spark anything about your parts, machines or orders…"
            onChange={(event) => {
              setDraft(event.target.value)
              setDictated(false)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                if (!busy && voice.state !== 'listening' && voice.state !== 'transcribing') {
                  voice.interrupt()
                  void send(draft)
                }
              }
            }}
          />
          <div className="spark-compose__tools">
            {voice.state === 'listening' ||
            voice.state === 'transcribing' ||
            voice.state === 'speaking' ||
            dictated ? (
              <span className={`spark-voice-state spark-voice-state--${voice.state}`} role="status">
                {voice.state === 'listening'
                  ? 'Listening… tap the microphone when you finish'
                  : voice.state === 'transcribing'
                    ? 'Turning speech into text…'
                    : voice.state === 'speaking'
                      ? 'Spark is speaking. Tap the microphone or type to interrupt.'
                      : dictated
                        ? 'Question recorded. Review it, then press Send.'
                        : 'Ask naturally. Spark will ask if it needs a detail.'}
              </span>
            ) : (
              <span />
            )}
            <div>
              <button
                type="button"
                disabled={!availability.data?.enabled || busy}
                aria-label={
                  voice.state === 'listening'
                    ? 'Stop recording'
                    : voice.state === 'transcribing'
                      ? 'Cancel transcription'
                      : 'Speak to Spark'
                }
                aria-pressed={voice.state === 'listening'}
                title={voice.message ?? 'Record your question'}
                onClick={voice.toggle}
              >
                <Mic size={19} aria-hidden="true" />
              </button>
              <button
                type="button"
                disabled={!availability.data?.enabled}
                aria-label="Read replies aloud"
                aria-pressed={voice.speakReplies}
                onClick={() => {
                  voice.setSpeakReplies(!voice.speakReplies)
                  voice.interrupt()
                }}
              >
                <Volume2 size={18} aria-hidden="true" />
              </button>
              {busy ? (
                <button
                  type="button"
                  aria-label="Stop request"
                  onClick={() => {
                    controller.current?.abort()
                    locked.current = false
                    setBusy(false)
                    if (pending) setDraft(pending.question)
                    setPending((current) => (current ? { ...current, status: 'stopped' } : null))
                  }}
                >
                  <Square size={17} aria-hidden="true" />
                </button>
              ) : (
                <button
                  className="spark-send"
                  type="submit"
                  disabled={
                    !draft.trim() ||
                    !ready ||
                    voice.state === 'listening' ||
                    voice.state === 'transcribing'
                  }
                  aria-label="Send message"
                >
                  <ArrowUp size={19} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
        </form>
        <p className="spark-compose-note" role="status">
          {saveError || history.storageError
            ? 'Browser storage is unavailable. New messages may not survive a refresh.'
            : copyError ||
              (voice.message
                ? voice.message
                : 'Check important details. You review and confirm every order.')}
        </p>
      </div>
      <dialog
        ref={partDialog}
        className="spark-part-dialog"
        aria-label="Part details"
        onClose={() => setPart(null)}
      >
        {part ? (
          <>
            <button
              className="spark-dialog-close"
              type="button"
              aria-label="Close part details"
              onClick={() => setPart(null)}
            >
              <X size={20} aria-hidden="true" />
            </button>
            <PartWorkspace
              partKey={part.key}
              tab={part.tab}
              backLabel="Back to the conversation"
              onClose={() => setPart(null)}
              onOpenPart={(key) => setPart({ key, tab: 'overview' })}
              onTab={(tab) => setPart({ ...part, tab })}
            />
          </>
        ) : null}
      </dialog>
    </div>
  )
}
