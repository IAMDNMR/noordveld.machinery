import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, isAbort } from '../../api'
import {
  askCommerceAgent,
  isLookup,
  isRouteOptions,
  type AgentResponse,
  type AgentSection,
  type AgentState,
  type Domain,
  type Scope,
} from '../../api/commerce'
import { CHECKOUT_ROUTE, partPath } from '../../lib/storeQuery'
import { useCart } from '../../store/CartContext'
import { useApi } from '../../hooks/useApi'
import { useSession } from '../../store/session'
import {
  bundleFrom,
  Chip,
  DiscoveryView,
  EvidenceView,
  LogisticsView,
  LookupView,
  RouteOptionsView,
  WarrantyView,
} from './views'
import './commerce.css'

interface Turn {
  id: number
  question: string
  response: AgentResponse
}
interface Failed {
  message: string
  patch: Partial<AgentState>
  text: string
}

/** Starting points are words the user may send, not data: they name no machine, shipment or claim, so the assistant asks which (and offers the user's own) when it needs to. */
export const EXAMPLES = [
  'Find a hydraulic pump.',
  'Where is my shipment and what parts are in it?',
  'Is this failed part covered by warranty?',
  'I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?',
]
/** Follow-up questions that make sense after an answer of that kind. Prompts only: each is sent to the assistant like anything typed. */
const FOLLOW_UPS: Record<Domain, string[]> = {
  DISCOVERY: [
    'Why are you recommending this part?',
    'Do you have this part available?',
    'Which machine uses this part?',
    'Where did this part come from?',
  ],
  LOGISTICS: [
    'What parts are in this shipment?',
    'Can I get it faster?',
    'Why is it taking so long?',
  ],
  WARRANTY: [
    'Who installed it?',
    'Was it installed correctly?',
    'Has this part been replaced before?',
  ],
}
const REFERENCE_KEYS = [
  'machine_instance_id',
  'part_id',
  'claim_id',
  'shipment_id',
  'order_id',
] as const
const LABELLED: Record<string, string> = { serial_number: 'serial', model_year: 'year' }
const NOT_ELIGIBLE_PROMPT = 'Why is this claim not eligible?'

const errorText = (e: unknown): string =>
  e instanceof ApiError
    ? e.status === 401
      ? 'Sign in to use the commerce assistant.'
      : e.status === 403
        ? 'You do not have access to that record.'
        : e.status === 0
          ? 'The service could not be reached. Check your connection and try again.'
          : e.message
    : 'Something went wrong.'

/** A short, readable label for one clarification option: the identifier first, then what tells similar ones apart. */
export const optionText = (o: Record<string, unknown>): string => {
  const first = REFERENCE_KEYS.find((k) => typeof o[k] === 'string')
  const rest = Object.entries(o)
    .filter(
      ([k, v]) => k !== first && v != null && v !== '' && !(Array.isArray(v) && v.length === 0),
    )
    .map(([k, v]) =>
      LABELLED[k] ? `${LABELLED[k]} ${String(v)}` : Array.isArray(v) ? v.join(', ') : String(v),
    )
  return [first ? String(o[first]) : null, ...rest].filter(Boolean).join(' · ')
}

export function CommerceWorkspace() {
  const { user, ready } = useSession()
  const location = useLocation()
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Failed | null>(null)
  const [lens, setLens] = useState<{ role: 'OEM' | 'DEALER'; dealer: string }>({
    role: 'OEM',
    dealer: '',
  })
  const input = useRef<HTMLInputElement>(null)
  const nextId = useRef(1)
  const abort = useRef<AbortController | null>(null)
  const inputId = useId()
  const latest = turns[turns.length - 1]
  const state = useMemo<AgentState>(() => latest?.response.state ?? {}, [latest])
  const asking = latest?.response.clarification ?? null

  useEffect(() => () => abort.current?.abort(), [])

  const scope = useCallback(
    (): Scope =>
      user?.role === 'ORDER_PROCESSOR' && lens.role === 'DEALER'
        ? { user_role: 'DEALER', dealer_id: lens.dealer.trim() }
        : {},
    [user, lens],
  )

  const send = useCallback(
    async (message: string, patch: Partial<AgentState> = {}, shown?: string) => {
      const text = message.trim()
      if (!text || busy) return
      abort.current?.abort()
      const controller = (abort.current = new AbortController())
      setBusy(true)
      setFailed(null)
      setDraft('')
      try {
        const response = await askCommerceAgent(
          text,
          { ...state, ...patch },
          scope(),
          controller.signal,
        )
        setTurns((t) => [...t, { id: nextId.current++, question: shown ?? text, response }])
      } catch (e) {
        if (!isAbort(e)) setFailed({ message: text, patch, text: errorText(e) })
      } finally {
        setBusy(false)
        input.current?.focus()
      }
    },
    [busy, scope, state],
  )

  /** A clarification option: remember the reference it names and carry on with the same question; the user does not start again. */
  const choose = useCallback(
    (option: Record<string, unknown>) => {
      const patch: Partial<AgentState> = {}
      for (const k of REFERENCE_KEYS)
        if (typeof option[k] === 'string') patch[k] = option[k] as string
      void send(latest?.question ?? 'Continue', patch, optionText(option))
    },
    [latest, send],
  )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(draft)
  }
  const reset = () => {
    abort.current?.abort()
    setTurns([])
    setFailed(null)
    setBusy(false)
    setDraft('')
    input.current?.focus()
  }

  if (!ready) return null
  if (!user) {
    return (
      <div className="cw-gate">
        <h2>Sign in to use the commerce assistant</h2>
        <p>
          Answers are scoped to your account: a customer sees their own machines, orders and claims;
          an order processor sees the OEM or a dealer view.
        </p>
        <Link
          to={`/sign-in?${new URLSearchParams({ next: location.pathname + location.search })}`}
          className="cw-primary"
        >
          Sign in
        </Link>
      </div>
    )
  }
  const remembered = (
    [
      'machine_model',
      'part_number',
      'machine_instance_id',
      'claim_id',
      'shipment_id',
      'order_id',
    ] as const
  )
    .filter((k) => state[k])
    .map((k) => `${k.replace(/_/g, ' ')} ${state[k]}`)

  return (
    <div className="cw">
      <div className="cw-unified">
        {user.role === 'ORDER_PROCESSOR' && (
          <div className="cw-lens" role="group" aria-label="View as">
            <label>
              View as
              <select
                value={lens.role}
                onChange={(e) => setLens({ ...lens, role: e.target.value as 'OEM' | 'DEALER' })}
              >
                <option value="OEM">OEM (everything)</option>
                <option value="DEALER">Dealer</option>
              </select>
            </label>
            {lens.role === 'DEALER' && (
              <label>
                Dealer id
                <input
                  value={lens.dealer}
                  onChange={(e) => setLens({ ...lens, dealer: e.target.value })}
                  placeholder="Dealer id"
                />
              </label>
            )}
          </div>
        )}
        <form className="cw-ask" onSubmit={submit}>
          <label className="cw-ask__label" htmlFor={inputId}>
            What can I help you with?
          </label>
          <div className="cw-ask__row">
            <input
              id={inputId}
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={500}
              autoComplete="off"
              placeholder={asking ? asking.question : 'Ask about a part, order or warranty…'}
              aria-describedby={`${inputId}-hint`}
            />
            <button type="submit" className="cw-primary" disabled={busy || !draft.trim()}>
              Ask
            </button>
          </div>
          <p id={`${inputId}-hint`} className="cw-meta cw-ask__hint">
            {asking
              ? asking.options.length
                ? 'Choose below, or type your answer here.'
                : 'Type your answer here.'
              : 'Every answer comes from the Noordveld records and shows its evidence.'}
            {remembered.length > 0 && (
              <>
                {' '}
                · Remembering {remembered.join(' · ')}{' '}
                <button type="button" className="cw-link" onClick={reset}>
                  Start over
                </button>
              </>
            )}
          </p>
        </form>

        {turns.length === 0 && !busy && !failed && (
          <ul className="cw-chips" aria-label="Things you can ask">
            {EXAMPLES.map((q) => (
              <li key={q}>
                <button type="button" onClick={() => void send(q)}>
                  {q}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="cw-answer-area" aria-live="polite" aria-busy={busy}>
          {busy && (
            <p className="cw-working" role="status">
              <span className="cw-spinner" aria-hidden /> Checking the records…
            </p>
          )}
          {failed && (
            <div className="cw-error" role="alert">
              <p>{failed.text}</p>
              {failed.text !== 'Sign in to use the commerce assistant.' && (
                <button
                  type="button"
                  className="cw-link"
                  onClick={() => void send(failed.message, failed.patch)}
                >
                  Try again
                </button>
              )}
            </div>
          )}
          {latest && (
            <CommerceAnswer
              key={latest.id}
              turn={latest}
              dim={busy}
              onChoose={choose}
              onAsk={(q) => void send(q)}
            />
          )}
        </div>

        {turns.length > 1 && (
          <details className="cw-history">
            <summary>Earlier in this conversation ({turns.length - 1})</summary>
            <ol>
              {turns.slice(0, -1).map((t) => (
                <li key={t.id}>
                  <strong>{t.question}</strong>
                  <span>{t.response.answer.text}</span>
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </div>
  )
}

/**
 * The explicit hand-off into the existing Parts Store cart (the same cart, CartContext, that the store and Agentic Shopping use). Offered only for a part the discovery decision
 * recommends: a canonical match with approved fitment, an approved source and availability. Nothing is ordered here; checkout stays in the Parts Store.
 */
function CartHandoff({
  partId,
  partNumber,
  machine,
}: {
  partId: string
  partNumber: string
  machine: string | null
}) {
  const { add } = useCart()
  const [added, setAdded] = useState(false)
  return added ? (
    <Link to={CHECKOUT_ROUTE} className="cw-primary">
      Added · Review order
    </Link>
  ) : (
    <button
      type="button"
      className="cw-primary"
      onClick={() => {
        add(partId, 1, machine)
        setAdded(true)
      }}
    >
      Add {partNumber} to cart
    </button>
  )
}

/** Only the journeys asked for: their sections and contexts; the lead is their own headlines when others were left out. */
const only = (r: AgentResponse, domains: readonly Domain[]): AgentResponse => {
  const sections = r.answer.sections.filter((s) => domains.includes(s.domain))
  if (sections.length === r.answer.sections.length) return r
  const contexts = Object.fromEntries(
    Object.entries(r.contexts).filter(([d]) => domains.includes(d as Domain)),
  ) as AgentResponse['contexts']
  const text = sections.map((s) => s.headline).join(' ')
  const clarification =
    r.clarification && domains.includes(r.clarification.domain as Domain) ? r.clarification : null
  return { ...r, contexts, clarification, answer: { ...r.answer, sections, text, lead: text } }
}

/**
 * The commerce assistant's answer to one question, shown on the Agentic Shopping screen: the same Commerce Agent API, contexts, evidence and views, restricted to the
 * journeys the request asked about (orders, shipments, warranty, part questions), and no second input. A follow-up question runs through the screen's own request flow.
 * The agent needs a signed-in user (answers are scoped to the account); a signed-out visitor is sent through the existing sign-in and brought back to the same request.
 */
export function CommerceAnswerPanel({
  question,
  domains,
}: {
  question: string
  domains: readonly Domain[]
}) {
  const { user, ready } = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  // the first answer is read like any other API resource; a chosen clarification option asks again with the reference it names
  const first = useApi(
    (signal) => (user ? askCommerceAgent(question, {}, {}, signal) : Promise.resolve(null)),
    `commerce-panel:${user?.id ?? '-'}:${question}`,
  )
  const [chosen, setChosen] = useState<{
    response: AgentResponse | null
    error: string | null
    busy: boolean
  }>({ response: null, error: null, busy: false })
  if (!ready) return null
  if (!user) {
    return (
      <div className="cw-gate">
        <h2>Sign in for your orders, shipments and warranty</h2>
        <p>
          These answers come from your own records, so they need your account. You will come
          straight back to this request.
        </p>
        <Link
          to={`/sign-in?${new URLSearchParams({ next: location.pathname + location.search })}`}
          className="cw-primary"
        >
          Sign in
        </Link>
      </div>
    )
  }
  const raw = chosen.response ?? first.data
  const turn: Turn | null = raw ? { id: 1, question, response: only(raw, domains) } : null
  const error = chosen.error ?? (first.error ? errorText(first.error) : null)
  const choose = async (option: Record<string, unknown>) => {
    const patch: Partial<AgentState> = {}
    for (const k of REFERENCE_KEYS)
      if (typeof option[k] === 'string') patch[k] = option[k] as string
    setChosen((c) => ({ ...c, busy: true, error: null }))
    try {
      setChosen({
        response: await askCommerceAgent(question, { ...(raw?.state ?? {}), ...patch }, {}),
        error: null,
        busy: false,
      })
    } catch (e) {
      setChosen((c) => ({ ...c, busy: false, error: errorText(e) }))
    }
  }
  return (
    <div className="cw-unified cw-embedded" aria-live="polite">
      {first.loading && !turn ? (
        <p className="cw-working">
          <span className="cw-spinner" aria-hidden="true" /> Checking your records…
        </p>
      ) : null}
      {error ? (
        <div className="cw-error" role="alert">
          <p>{error}</p>
          <button type="button" className="cw-link" onClick={first.reload}>
            Try again
          </button>
        </div>
      ) : null}
      {turn ? (
        <CommerceAnswer
          turn={turn}
          dim={chosen.busy}
          onChoose={(o) => void choose(o)}
          onAsk={(q) => navigate(`${location.pathname}?${new URLSearchParams({ q })}`)}
          typeHint="Add it to your request (for example the claim number or the machine model) and ask again."
        />
      ) : null}
    </div>
  )
}

export function CommerceAnswer({
  turn,
  dim,
  onChoose,
  onAsk,
  typeHint = 'Type your answer in the box above and I will carry on with your question.',
  format,
}: {
  turn: Turn
  dim: boolean
  onChoose: (o: Record<string, unknown>) => void
  onAsk: (q: string) => void
  typeHint?: string
  /** Spark's presentation: 'text' keeps the record details one click away; the chat already shows the question */
  format?: 'text' | 'detail'
}) {
  const r = turn.response
  const answeredSections = r.answer.sections.filter((s) => s.status !== 'REQUIRES_CLARIFICATION')
  // a question is asked once, in the clarification box: what precedes it is the part of the request that could be answered
  const lead =
    r.clarification && r.answer.text.endsWith(r.clarification.question)
      ? r.answer.text.slice(0, -r.clarification.question.length).trim()
      : r.answer.text
  const bundle =
    answeredSections.length && Object.keys(r.contexts).length
      ? bundleFrom(r.contexts, r.answer.synthetic_notice)
      : null
  const primary = r.answer.sections.find((s) => s.status !== 'REQUIRES_CLARIFICATION')?.domain
  const d = r.contexts.DISCOVERY
  const part = d ? (isLookup(d) ? d.part : (d.recommended_part ?? d.compatible_part)) : null
  const recommended =
    d && !isLookup(d) && d.decision.decision === 'RECOMMEND' ? d.recommended_part : null
  const machineModel = d && !isLookup(d) ? (d.machine?.model ?? null) : null
  const notEligible =
    r.contexts.WARRANTY && r.contexts.WARRANTY.decision.facts.outcome !== 'ELIGIBLE'
  // shipment questions only make sense once a shipment is in the answer (an order with no shipment yet has nothing to ask about)
  const next =
    r.clarification ||
    !primary ||
    (primary === 'LOGISTICS' &&
      !(
        r.contexts.LOGISTICS &&
        'shipment' in r.contexts.LOGISTICS &&
        r.contexts.LOGISTICS.shipment
      ))
      ? []
      : primary === 'LOGISTICS' &&
          r.contexts.LOGISTICS &&
          'planned_eta' in r.contexts.LOGISTICS &&
          r.contexts.LOGISTICS.planned_eta?.delivered
        ? FOLLOW_UPS.LOGISTICS.slice(0, 1) // a delivered shipment cannot be sped up
        : FOLLOW_UPS[primary]
  return (
    <article className={`cw-answer${dim ? ' is-dim' : ''}`} aria-label="Answer">
      {format ? null : <p className="cw-question">{turn.question}</p>}
      {lead && <p className="cw-lead">{lead}</p>}

      {format === 'text' && answeredSections.length ? (
        <details className="cw-more">
          <summary>Show the details</summary>
          {r.answer.sections.map((s) => (
            <Detail key={s.domain} section={s} response={r} />
          ))}
        </details>
      ) : (
        r.answer.sections.map((s) => <Detail key={s.domain} section={s} response={r} />)
      )}

      {r.clarification && (
        <div className="cw-clarify" role="group" aria-label="Clarification">
          <p className="cw-clarify__q">{r.clarification.question}</p>
          {r.clarification.options.length > 0 ? (
            <ul className="cw-chips cw-chips--options">
              {r.clarification.options.slice(0, 12).map((o, i) => (
                <li key={i}>
                  <button type="button" onClick={() => onChoose(o)}>
                    {optionText(o)}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cw-meta">{typeHint}</p>
          )}
        </div>
      )}

      {r.status === 'OUT_OF_SCOPE' && (
        <ul className="cw-chips" aria-label="Things you can ask">
          {EXAMPLES.slice(0, 3).map((q) => (
            <li key={q}>
              <button type="button" onClick={() => onAsk(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      )}

      {(next.length > 0 || part) && (
        <div className="cw-next" aria-label="What next">
          {recommended && (
            <CartHandoff
              partId={recommended.part_id}
              partNumber={recommended.part_number}
              machine={machineModel}
            />
          )}
          {recommended && (
            <Link
              to={`/spark/chat?${new URLSearchParams({ q: turn.question })}`}
              className="cw-link"
            >
              Compare delivery and fulfilment options
            </Link>
          )}
          {part && (
            <Link to={partPath(part.part_number)} className="cw-link">
              Open {part.part_number} in the parts store
            </Link>
          )}
          {next.map((q) => (
            <button key={q} type="button" className="cw-chip-btn" onClick={() => onAsk(q)}>
              {q}
            </button>
          ))}
          {notEligible && (
            <button
              type="button"
              className="cw-chip-btn"
              onClick={() => onAsk(NOT_ELIGIBLE_PROMPT)}
            >
              {NOT_ELIGIBLE_PROMPT}
            </button>
          )}
        </div>
      )}

      {bundle && (
        <details className="cw-evidence-box">
          <summary>
            Evidence and sources ({bundle.evidence.length || bundle.source_records.length})
          </summary>
          <EvidenceView bundle={bundle} />
        </details>
      )}

      <p className="cw-meta cw-how">
        {r.answer.synthetic_notice ? `${r.answer.synthetic_notice} ` : ''}
        {r.answer.grounding.mode === 'LLM'
          ? 'Worded by the language model and checked against the evidence.'
          : 'Written directly from the records.'}
        {r.understanding.source === 'LLM' ? ' Routed by the language model.' : ''}
      </p>
    </article>
  )
}

/** One journey's detail inside the answer. A journey that was only a question is asked in the conversation, not shown as an empty panel. */
function Detail({ section, response }: { section: AgentSection; response: AgentResponse }) {
  const ctx = response.contexts[section.domain]
  if (section.status === 'REQUIRES_CLARIFICATION')
    return section.notes.length ? <p className="cw-meta">{section.notes.join(' ')}</p> : null
  if (!ctx) return <p className="cw-meta cw-detail--note">{section.headline}</p>
  return (
    <section className="cw-detail" aria-label={section.title}>
      <h3 className="cw-detail__title">
        {section.title} <Chip value={section.decision} />
      </h3>
      {section.notes.map((n) => (
        <p key={n} className="cw-meta">
          {n}
        </p>
      ))}
      {section.domain === 'DISCOVERY' &&
        (isLookup(ctx as never) ? (
          <LookupView ctx={ctx as never} />
        ) : (
          <DiscoveryView ctx={ctx as never} bare />
        ))}
      {section.domain === 'LOGISTICS' &&
        (isRouteOptions(ctx as never) ? (
          <RouteOptionsView ctx={ctx as never} />
        ) : (
          <LogisticsView ctx={ctx as never} bare />
        ))}
      {section.domain === 'WARRANTY' && <WarrantyView ctx={ctx as never} bare />}
    </section>
  )
}
