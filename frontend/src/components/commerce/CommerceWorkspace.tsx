import { useCallback, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, isAbort } from '../../api'
import {
  askCommerceAgent, discoveryContext, logisticsContext, warrantyContext,
  type AgentResponse, type AgentState, type DiscoveryContext, type Domain, type LogisticsContext, type Scope, type WarrantyContext,
} from '../../api/commerce'
import { roleLabel, useSession } from '../../store/session'
import { bundleFrom, Chip, DiscoveryView, EvidenceView, LogisticsView, Options, WarrantyView } from './views'
import './commerce.css'

type Tab = 'discovery' | 'logistics' | 'warranty' | 'evidence'
interface Message { id: number; role: 'user' | 'assistant'; text: string; response?: AgentResponse }
interface Contexts { DISCOVERY?: DiscoveryContext; LOGISTICS?: LogisticsContext; WARRANTY?: WarrantyContext }

/** Example requests are words the user may send, not data: they name no machine, shipment or claim, so the assistant asks which one (and offers the user's own) when it needs to. */
export const EXAMPLES = [
  'Find a hydraulic pump.',
  'Where is my shipment and what parts are in it?',
  'Is this failed part covered by warranty?',
  'I need a replacement hydraulic pump urgently. Is the failed one covered and how fast can I get the replacement?',
]
const STATE_KEYS = ['machine_instance_id', 'part_id', 'claim_id', 'shipment_id', 'order_id'] as const
const TAB_OF: Record<Domain, Tab> = { DISCOVERY: 'discovery', LOGISTICS: 'logistics', WARRANTY: 'warranty' }

const errorText = (e: unknown): string =>
  e instanceof ApiError ? (e.status === 401 ? 'Sign in to use the commerce assistant.' : e.status === 403 ? 'You do not have access to that record.' : e.message) : 'Something went wrong.'

export function CommerceWorkspace() {
  const { user, ready } = useSession()
  const [thread, setThread] = useState<Message[]>([])
  const [agentState, setAgentState] = useState<AgentState>({})
  const [contexts, setContexts] = useState<Contexts>({})
  const [notice, setNotice] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('discovery')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [lens, setLens] = useState<{ role: 'OEM' | 'DEALER'; dealer: string }>({ role: 'OEM', dealer: '' })
  const last = useRef<string>('')
  const nextId = useRef(1)

  const scope = useCallback((): Scope => (user?.role === 'ORDER_PROCESSOR' && lens.role === 'DEALER' ? { user_role: 'DEALER', dealer_id: lens.dealer.trim() } : {}), [user, lens])

  const run = useCallback(async <T,>(work: () => Promise<T>, done: (r: T) => void) => {
    setBusy(true)
    setError(null)
    try {
      done(await work())
    } catch (e) {
      if (!isAbort(e)) setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }, [])

  const send = useCallback((message: string, patch: Partial<AgentState> = {}) => {
    const text = message.trim()
    if (!text || busy) return
    last.current = text
    const state = { ...agentState, ...patch }
    setThread((t) => [...t, { id: nextId.current++, role: 'user', text }])
    setDraft('')
    return run(() => askCommerceAgent(text, state, scope()), (r) => {
      setAgentState(r.state)
      setThread((t) => [...t, { id: nextId.current++, role: 'assistant', text: r.answer.text, response: r }])
      setNotice(r.answer.synthetic_notice)
      setContexts((c) => ({ ...c, ...r.contexts }))
      const shown = r.answer.sections.find((s) => s.status !== 'REQUIRES_CLARIFICATION') ?? r.answer.sections[0]
      if (shown) setTab(TAB_OF[shown.domain])
    })
  }, [agentState, busy, run, scope])

  /** A clarification option: remember the references it names and ask the same question again. */
  const choose = useCallback((option: Record<string, unknown>) => {
    const patch: Partial<AgentState> = {}
    for (const k of STATE_KEYS) if (typeof option[k] === 'string') patch[k] = option[k] as string
    send(last.current || 'Continue', patch)
  }, [send])

  // a choice made in a panel runs that journey directly (the same API); only the conversation re-asks the assistant
  const pickShipment = (o: Record<string, unknown>) => { if (typeof o.shipment_id === 'string') run(() => logisticsContext({ shipment_id: o.shipment_id as string }, scope()), (c) => setContexts((x) => ({ ...x, LOGISTICS: c }))) }
  const pickWarranty = (o: Record<string, unknown>) => {
    const only = Array.isArray(o.installed_part_ids) && o.installed_part_ids.length === 1 ? (o.installed_part_ids[0] as string) : undefined
    const ref = typeof o.claim_id === 'string' ? { claim_id: o.claim_id } : typeof o.machine_instance_id === 'string' && (typeof o.part_id === 'string' || only)
      ? { machine_instance_id: o.machine_instance_id, part_id: (o.part_id as string | undefined) ?? only } : null
    if (ref) run(() => warrantyContext(ref, scope()), (c) => setContexts((x) => ({ ...x, WARRANTY: c })))
  }
  const submit = (e: FormEvent) => { e.preventDefault(); send(draft) }
  const reset = () => { setThread([]); setAgentState({}); setContexts({}); setNotice(null); setError(null); last.current = '' }

  if (!ready) return null
  if (!user) {
    return (
      <div className="cw-gate">
        <h2>Sign in to use the commerce assistant</h2>
        <p>Answers are scoped to your account: a customer sees their own machines, orders and claims; an order processor sees the OEM or a dealer view.</p>
        <Link to="/sign-in" className="cw-primary">Sign in</Link>
      </div>
    )
  }
  const bundle = Object.keys(contexts).length ? bundleFrom(contexts, notice) : null

  return (
    <div className="cw">
      <div className="cw-grid">
        <section className="cw-assistant" aria-label="Commerce Assistant">
          <header className="cw-assistant__head">
            <h2>Commerce Assistant</h2>
            <span className="cw-meta">{roleLabel(user.role)}{user.customer ? ` · ${user.customer}` : ''}</span>
          </header>
          {user.role === 'ORDER_PROCESSOR' && (
            <div className="cw-lens" role="group" aria-label="View as">
              <label>View as
                <select value={lens.role} onChange={(e) => setLens({ ...lens, role: e.target.value as 'OEM' | 'DEALER' })}>
                  <option value="OEM">OEM (everything)</option>
                  <option value="DEALER">Dealer</option>
                </select>
              </label>
              {lens.role === 'DEALER' && <label>Dealer id<input value={lens.dealer} onChange={(e) => setLens({ ...lens, dealer: e.target.value })} placeholder="Dealer id" /></label>}
            </div>
          )}
          <div className="cw-thread" aria-live="polite" aria-label="Conversation">
            {thread.length === 0 && (
              <div className="cw-welcome">
                <p>Ask about a part, a shipment or a warranty. Every answer comes from the Noordveld records and shows its evidence.</p>
                <ul className="cw-examples">{EXAMPLES.map((q) => <li key={q}><button type="button" onClick={() => send(q)} disabled={busy}>{q}</button></li>)}</ul>
              </div>
            )}
            {thread.map((m) => (m.role === 'user' ? <p key={m.id} className="cw-msg cw-msg--user">{m.text}</p> : <AssistantMessage key={m.id} message={m} onChoose={choose} onOpen={setTab} />))}
            {busy && <p className="cw-msg cw-msg--pending" role="status">Checking the records…</p>}
            {error && <p className="cw-error" role="alert">{error}</p>}
          </div>
          <form className="cw-compose" onSubmit={submit}>
            <label className="cw-sr" htmlFor="cw-input">Your request</label>
            <input id="cw-input" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={500} placeholder="Ask about a part, a shipment or a warranty…" autoComplete="off" />
            <button type="submit" className="cw-primary" disabled={busy || !draft.trim()}>Ask</button>
          </form>
          <Remembered state={agentState} onClear={reset} />
        </section>

        <section className="cw-work" aria-label="Commerce workspace">
          <div role="tablist" aria-label="Workspace areas" className="cw-tabs">
            {([['discovery', 'Part Discovery'], ['logistics', 'Shipment / Logistics'], ['warranty', 'Warranty / Traceability'], ['evidence', 'Evidence / Context']] as [Tab, string][]).map(([id, name]) => (
              <button key={id} type="button" role="tab" id={`cw-tab-${id}`} aria-selected={tab === id} aria-controls={`cw-panel-${id}`} className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>
                {name}{id !== 'evidence' && contexts[id === 'discovery' ? 'DISCOVERY' : id === 'logistics' ? 'LOGISTICS' : 'WARRANTY'] ? <i aria-label="has a result" className="cw-dot" /> : null}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`cw-panel-${tab}`} aria-labelledby={`cw-tab-${tab}`} className="cw-panel">
            {tab === 'discovery' && <DiscoveryPanel ctx={contexts.DISCOVERY} busy={busy} onRun={(q) => run(() => discoveryContext(q, scope()), (c) => setContexts((x) => ({ ...x, DISCOVERY: c })))} />}
            {tab === 'logistics' && <LogisticsPanel ctx={contexts.LOGISTICS} busy={busy} onPick={pickShipment} onRun={(ref) => run(() => logisticsContext(ref, scope()), (c) => setContexts((x) => ({ ...x, LOGISTICS: c })))} />}
            {tab === 'warranty' && <WarrantyPanel ctx={contexts.WARRANTY} busy={busy} onPick={pickWarranty} onRun={(ref) => run(() => warrantyContext(ref, scope()), (c) => setContexts((x) => ({ ...x, WARRANTY: c })))} />}
            {tab === 'evidence' && <EvidenceView bundle={bundle} />}
          </div>
          {notice && <p className="cw-notice" role="note">{notice}</p>}
        </section>
      </div>
    </div>
  )
}

function Remembered({ state, onClear }: { state: AgentState; onClear: () => void }) {
  const items = (['machine_model', 'part_number', 'machine_instance_id', 'claim_id', 'shipment_id', 'order_id'] as const).filter((k) => state[k]).map((k) => `${k.replace(/_/g, ' ')}: ${state[k]}`)
  if (!items.length) return null
  return (
    <p className="cw-remembered" aria-label="What the assistant is remembering">
      Remembering {items.join(' · ')} <button type="button" className="cw-link" onClick={onClear}>Start over</button>
    </p>
  )
}

function AssistantMessage({ message, onChoose, onOpen }: { message: Message; onChoose: (o: Record<string, unknown>) => void; onOpen: (t: Tab) => void }) {
  const r = message.response
  if (!r) return <p className="cw-msg">{message.text}</p>
  return (
    <div className="cw-msg cw-msg--assistant">
      <p className="cw-lead">{message.text}</p>
      {r.answer.sections.map((s) => (
        <div key={s.domain} className="cw-sec">
          <h4>{s.title} <Chip value={s.decision} /></h4>
          {s.notes.map((n) => <p key={n} className="cw-meta">{n}</p>)}
          {s.lines.length > 0 && <ul>{s.lines.filter((l) => !l.startsWith('Option:')).map((l, i) => <li key={i}>{l}</li>)}</ul>}
          <button type="button" className="cw-link" onClick={() => onOpen(TAB_OF[s.domain])}>Open in workspace</button>
        </div>
      ))}
      {r.clarification && (<div className="cw-ask"><p>{r.clarification.question}</p><Options options={r.clarification.options} onPick={onChoose} /></div>)}
      {r.answer.synthetic_notice && <p className="cw-meta">{r.answer.synthetic_notice}</p>}
      <p className="cw-meta cw-how">
        {r.answer.grounding.mode === 'LLM' ? 'Worded by the language model and checked against the evidence.' : 'Written directly from the records.'} Understood as {r.understanding.intent.replace('_', ' ').toLowerCase()}
        {r.understanding.source === 'LLM' ? ' (routed by the language model)' : ''}.
      </p>
    </div>
  )
}

// ── the direct panels: each journey on its own, same APIs ─────────────────────────────────────────
function Empty({ children }: { children: string }) { return <p className="cw-empty">{children}</p> }

function DiscoveryPanel({ ctx, busy, onRun }: { ctx?: DiscoveryContext; busy: boolean; onRun: (q: string) => void }) {
  const [q, setQ] = useState('')
  return (
    <>
      <form className="cw-form" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) onRun(q.trim()) }}>
        <label>Part request<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="a hydraulic filter for my machine" maxLength={500} /></label>
        <button type="submit" className="cw-primary" disabled={busy || q.trim().length < 3}>Find part</button>
      </form>
      {ctx ? <DiscoveryView ctx={ctx} /> : <Empty>Find a part for a machine. The backend checks product type, fitment, approved source and availability before anything is recommended.</Empty>}
    </>
  )
}

function LogisticsPanel({ ctx, busy, onRun, onPick }: { ctx?: LogisticsContext; busy: boolean; onRun: (r: { shipment_id?: string; order_id?: string }) => void; onPick: (o: Record<string, unknown>) => void }) {
  const [id, setId] = useState('')
  const v = id.trim().toUpperCase()
  const ref = /^ORD-/.test(v) ? { order_id: v } : { shipment_id: v }
  return (
    <>
      <form className="cw-form" onSubmit={(e) => { e.preventDefault(); if (v) onRun(ref) }}>
        <label>Shipment or order number<input value={id} onChange={(e) => setId(e.target.value)} placeholder="Shipment or order number" maxLength={64} /></label>
        <button type="submit" className="cw-primary" disabled={busy || !v}>Track</button>
      </form>
      {ctx ? <LogisticsView ctx={ctx} onPick={onPick} /> : <Empty>Track a shipment or an order. A shipment can carry several order lines; an order can be split over several shipments.</Empty>}
    </>
  )
}

function WarrantyPanel({ ctx, busy, onRun, onPick }: { ctx?: WarrantyContext; busy: boolean; onRun: (r: { claim_id?: string; machine_instance_id?: string; part_id?: string }) => void; onPick: (o: Record<string, unknown>) => void }) {
  const [claim, setClaim] = useState('')
  const [instance, setInstance] = useState('')
  const [part, setPart] = useState('')
  const byClaim = claim.trim() !== ''
  const ok = byClaim ? true : instance.trim() !== '' && part.trim() !== ''
  return (
    <>
      <form className="cw-form" onSubmit={(e) => { e.preventDefault(); if (ok) onRun(byClaim ? { claim_id: claim.trim().toUpperCase() } : { machine_instance_id: instance.trim().toUpperCase(), part_id: part.trim().toUpperCase() }) }}>
        <label>Claim<input value={claim} onChange={(e) => setClaim(e.target.value)} placeholder="Claim number" maxLength={64} /></label>
        <span className="cw-or">or</span>
        <label>Machine<input value={instance} onChange={(e) => setInstance(e.target.value)} placeholder="Machine number" maxLength={64} disabled={byClaim} /></label>
        <label>Part<input value={part} onChange={(e) => setPart(e.target.value)} placeholder="Part number" maxLength={64} disabled={byClaim} /></label>
        <button type="submit" className="cw-primary" disabled={busy || !ok}>Check warranty</button>
      </form>
      {ctx ? <WarrantyView ctx={ctx} onPick={onPick} /> : <Empty>Check a claim, or a machine and part. The decision comes from the deterministic warranty rules and lists every check behind it.</Empty>}
    </>
  )
}

