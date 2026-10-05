import { ArrowLeft, ArrowRight, Check, CircleAlert, RotateCcw, ShoppingBag, ShoppingCart } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { askAgent, getAgentPipeline, getAgentSuggestions, type AgentCandidate, type AgentInterpretation, type AgentResponse, type AgentStep } from '../api/agent'
import type { ApiError } from '../api'
import { canOrder } from '../components/store/Badges'
import { CartDrawer } from '../components/store/CartDrawer'
import { PartImage } from '../components/store/PartImage'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { formatMoney } from '../lib/format'
import { CHECKOUT_ROUTE, partPath } from '../lib/storeQuery'
import { CartProvider, useCart } from '../store/CartContext'
import '../styles/wf.css'
import '../components/store/store.css'
import '../components/agent/agent.css'

export const AGENT_ROUTE = '/agentic-shopping'
const PI = '/parts-intelligence'
const STEP_MS = 320 // the API answers at once; the steps it reports are revealed one after another so the work can be followed

/**
 * Agentic Shopping: the decision. Parts Store finds the part, Parts Intelligence explains it; this page answers "what should we
 * do?". The agent reads the request, checks fitment, availability and fulfilment in the Noordveld graph, ranks the valid options
 * against the user's requirements and gets the best one ready for the cart. Every value on the page comes from the API.
 */
export default function AgenticShoppingPage() {
  usePageMeta({ title: 'Agentic Shopping', description: "Tell us what you need. We'll work out the best way to fulfil it, from Noordveld fitment, price, stock and supply data.", path: AGENT_ROUTE })
  return (
    <CartProvider>
      <AgentShop />
      <CartDrawer />
    </CartProvider>
  )
}

function AgentShop() {
  const [params, setParams] = useSearchParams()
  const request = params.get('q') ?? ''
  const run = (q: string) => setParams(q.trim() ? { q: q.trim() } : {})
  return (
    <div className="ag wf">
      <CartButton />
      {request ? <Run key={request} request={request} onRun={run} /> : <Compose onRun={run} />}
    </div>
  )
}

function CartButton() {
  const { count, setOpen, justAdded } = useCart()
  return (
    <button type="button" className={`ag-cart ${justAdded ? 'is-bump' : ''}`} onClick={() => setOpen(true)} aria-label={`Open cart, ${count} ${count === 1 ? 'item' : 'items'}`}>
      <ShoppingBag size={17} strokeWidth={1.8} aria-hidden="true" />
      <span>Cart</span>
      {count > 0 ? <span className="ag-cart__n">{count}</span> : null}
    </button>
  )
}

// ── compose ─────────────────────────────────────────────────────────────────────────────────────
function Compose({ onRun }: { onRun: (q: string) => void }) {
  const suggestions = useApi((s) => getAgentSuggestions(s), 'agent-suggestions')
  return (
    <section className="ag-compose" aria-labelledby="ag-title">
      <div className="wf-container">
        <a className="back-link" href="/agentic-commerce/">
          <ArrowLeft size={14} strokeWidth={2} aria-hidden="true" /> Agentic E-Commerce
        </a>
        <div className="ag-compose__inner">
          <p className="eyebrow">Agentic Shopping</p>
          <h1 id="ag-title" className="ag-compose__title">
            What do you need?
          </h1>
          <p className="ag-compose__lede">Describe what you're looking for in plain language. The agent checks the right part against your requirements and finds the best available path.</p>
          <p className="ag-compose__aside">
            Built on Parts Intelligence: the same machines, parts, fitment and availability. <Link to={PI}>Open Parts Intelligence</Link>
          </p>
          <RequestBox onRun={onRun} placeholder={suggestions.data?.[0]?.request ? `e.g. ${suggestions.data[0].request}` : undefined} />
          {suggestions.data?.length ? (
            <ul className="ag-pills" aria-label="Example requests">
              {suggestions.data.map((s) => (
                <li key={s.request}>
                  <button type="button" onClick={() => onRun(s.request)}>
                    {s.request}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  )
}

function RequestBox({ onRun, placeholder }: { onRun: (q: string) => void; placeholder?: string }) {
  const [text, setText] = useState('')
  const id = useId()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim().length >= 2) onRun(text)
  }
  return (
    <form className="ag-request" onSubmit={submit}>
      <label className="sr-only" htmlFor={id}>
        Describe what you need
      </label>
      <textarea
        id={id}
        rows={2}
        maxLength={400}
        value={text}
        placeholder={placeholder ?? 'Describe the machine, the part you need and what matters to you.'}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            e.currentTarget.form?.requestSubmit()
          }
        }}
      />
      <button type="submit" className="ag-request__go" disabled={text.trim().length < 2}>
        Find the right part
      </button>
    </form>
  )
}

// ── one request ─────────────────────────────────────────────────────────────────────────────────
function Run({ request, onRun }: { request: string; onRun: (q: string) => void }) {
  const state = useApi((s) => askAgent(request, s), `agent:${request}`)
  const pipeline = useApi((s) => getAgentPipeline(s), 'agent-pipeline')
  const [shown, setShown] = useState(0)
  const [open, setOpen] = useState(false)
  const results = useRef<HTMLDivElement>(null)
  const steps = state.data?.steps ?? null

  useEffect(() => {
    if (!steps) return
    const visible = steps.filter((s) => s.status !== 'skipped').length
    const instant = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches // reduced motion: everything at once
    const timers = instant
      ? [window.setTimeout(() => setShown(visible), 0)]
      : Array.from({ length: visible }, (_, i) => window.setTimeout(() => setShown(i + 1), (i + 1) * STEP_MS))
    return () => timers.forEach(clearTimeout)
  }, [steps])

  const r = state.data
  const done = r ? shown >= r.steps.filter((s) => s.status !== 'skipped').length : false
  const direct = r && r.state !== 'recommendation' // clarifications and limits are shown as soon as the steps finish
  useEffect(() => {
    if (open || (done && direct)) results.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [open, done, direct])

  return (
    <section className="ag-run" aria-labelledby="ag-run-title">
      <div className="wf-container">
        <div className="ag-run__top">
          <p className="eyebrow">Agentic Shopping</p>
          <h1 id="ag-run-title" className="ag-run__request">
            “{request}”
          </h1>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onRun('')}>
            <RotateCcw size={14} strokeWidth={2} aria-hidden="true" /> New request
          </button>
        </div>

        {state.error ? (
          <ServiceState error={state.error} onRetry={state.reload} />
        ) : (
          <div className="ag-work">
            {r && r.state !== 'out_of_scope' ? <YourRequest i={r.interpretation} /> : null}
            <Rail steps={steps} shown={shown} pending={pipeline.data?.map((p) => p.label) ?? []} />
          </div>
        )}

        {r && done && r.state === 'recommendation' && !open ? (
          <div className="ag-run__cta">
            <button type="button" className="btn btn-accent" onClick={() => setOpen(true)}>
              View recommendation <ArrowRight size={18} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
        ) : null}

        <div ref={results} className="ag-results">
          {r && done && (open || direct) ? <Result r={r} onRefine={(extra) => onRun(extra ? `${r.request} ${extra}` : '')} /> : null}
        </div>
      </div>
    </section>
  )
}

/** How the agent read the request. Only what was understood is shown; nothing is filled in. */
function YourRequest({ i }: { i: AgentInterpretation }) {
  const priority = [i.preference === 'cheapest' ? 'Lowest price' : i.preference === 'fastest' ? 'Fastest' : null,
    i.availability === 'require' ? 'Must be in stock' : i.availability === 'prefer' ? 'Prefer in stock' : i.availability === 'future' ? 'Accepts on-order stock' : null].filter(Boolean).join(' · ')
  const fields: [string, string | null][] = [
    ['Machine', i.machine],
    ['Need', i.part_type],
    ['Budget', i.budget_max != null ? `Up to ${formatMoney({ amount: i.budget_max, currency: i.budget_currency ?? 'EUR' })}` : null],
    ['Priority', priority || null],
    ['Location', i.delivery_place],
    ['Quantity', i.quantity != null ? String(i.quantity) : null],
  ]
  const known = fields.filter(([, v]) => v)
  return (
    <section className="ag-req" aria-label="Your request">
      <p className="eyebrow">Your request</p>
      {known.length ? (
        <dl>
          {known.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="small muted">Nothing specific was understood yet.</p>
      )}
    </section>
  )
}

/** The agent's steps, as the API reports them: a numbered stepper, then one line for each thing it found. */
function Rail({ steps, shown, pending }: { steps: AgentStep[] | null; shown: number; pending: string[] }) {
  const visible = steps?.filter((s) => s.status !== 'skipped') ?? []
  const rows = steps ?? pending.map((label, i) => ({ key: String(i), label, status: 'skipped' as const, message: '' }))
  const stateOf = (i: number): string => {
    if (!steps) return i === 0 ? 'is-active' : 'is-idle'
    const s = steps[i]
    const pos = visible.indexOf(s)
    if (s.status === 'skipped' || pos < 0 || pos >= shown) return pos === shown ? 'is-active' : 'is-idle'
    return s.status === 'done' ? 'is-done' : 'is-blocked'
  }
  return (
    <div className="ag-steps">
      <ol className="ag-rail" aria-label="What the agent does">
        {rows.map((s, i) => {
          const st = stateOf(i)
          return (
            <li key={s.key} className={`ag-rail__step ${st}`}>
              <span className="ag-rail__n" aria-hidden="true">
                {st === 'is-done' ? <Check size={13} strokeWidth={3} /> : i + 1}
              </span>
              <span className="ag-rail__label">{s.label}</span>
            </li>
          )
        })}
      </ol>
      <ul className="ag-log" aria-live="polite">
        {!steps ? (
          <li className="is-working">
            <span className="ag-log__spin" aria-hidden="true" /> Understanding your request…
          </li>
        ) : (
          visible.slice(0, shown).map((s) => (
            <li key={s.key} className={`is-${s.status}`}>
              {s.status === 'done' ? <Check size={16} strokeWidth={2.4} aria-hidden="true" /> : <CircleAlert size={16} strokeWidth={2} aria-hidden="true" />}
              <span>{s.message}</span>
            </li>
          ))
        )}
      </ul>
    </div>
  )
}

/** A compact service state, never a page-sized alarm, and no provider or transport details. */
function ServiceState({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const [title, text] =
    error.code === 'llm_unavailable' || error.code === 'llm_invalid_response'
      ? ['Agent temporarily unavailable', 'The question-understanding service is unavailable. Please try again.']
      : error.code === 'graph_unavailable'
        ? ['Parts data temporarily unavailable', 'The parts catalogue could not be reached. Please try again.']
        : error.status === 0 || (error.status >= 500 && error.code === 'error')
          ? ['Agent not reachable', 'The agent could not be reached. Please try again.']
          : ['Request not handled', 'Please rephrase the request and try again.']
  return (
    <div className="ag-service" role="status">
      <CircleAlert size={18} strokeWidth={2} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{text}</span>
      </div>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}

// ── results ─────────────────────────────────────────────────────────────────────────────────────
function Result({ r, onRefine }: { r: AgentResponse; onRefine: (extra: string) => void }) {
  const i = r.interpretation
  const best = r.candidates.find((c) => c.recommended)

  if (r.state === 'out_of_scope') {
    return (
      <div className="ag-note card card-pad">
        <h2>That isn't a parts request.</h2>
        <p className="muted">{r.question}</p>
        <Link className="btn btn-secondary btn-sm" to={PI}>
          Open Parts Intelligence
        </Link>
      </div>
    )
  }

  return (
    <div className="ag-res">
      <h2 className="ag-res__based" tabIndex={-1} ref={(el) => el?.focus({ preventScroll: true })}>
        Based on “{r.request}”
      </h2>

      {r.state !== 'recommendation' ? (
        <div className="ag-need card card-pad">
          <p className="eyebrow">{r.state === 'no_match' ? 'No verified option meets your request' : 'One more detail'}</p>
          <p className="ag-need__q">{r.question}</p>
          {r.options.length ? (
            <div className="chip-row ag-need__opts">
              {r.options.map((o) => (
                <button key={o.label} type="button" className="chip" onClick={() => onRefine(o.refine)}>
                  {o.label}
                </button>
              ))}
            </div>
          ) : null}
          {r.notes.map((n) => (
            <p key={n} className="small muted">
              {n}
            </p>
          ))}
          <Excluded r={r} />
          {r.state === 'no_match' && i.machine ? (
            <Link className="link-more" to={`${PI}?q=${encodeURIComponent(`Which parts fit the ${i.machine}?`)}`}>
              See what fits the {i.machine} in Parts Intelligence →
            </Link>
          ) : null}
        </div>
      ) : null}

      {best && r.state === 'recommendation' ? (
        <>
          {r.decision ? <DecisionPanel d={r.decision} /> : null}
          <Recommended c={best} machine={i.machine} qty={i.quantity} />
          <div className="grid grid-2 ag-explain">
            <Why r={r} best={best} />
            <HowWeKnow r={r} best={best} />
          </div>
          <Alternatives r={r} />
          {r.notes.length || r.excluded.length ? (
            <div className="ag-res__notes">
              {r.notes.map((n) => (
                <p key={n} className="small muted">
                  {n}
                </p>
              ))}
              <Excluded r={r} />
            </div>
          ) : null}
        </>
      ) : null}
      <p className="disclaimer">{r.disclaimer}</p>
    </div>
  )
}

function Excluded({ r }: { r: AgentResponse }) {
  if (!r.excluded.length) return null
  return (
    <p className="small muted">
      Not offered:{' '}
      {r.excluded.map((e, k) => (
        <span key={e.part_number}>
          {k ? ', ' : ''}
          <Link to={`${PI}?part=${encodeURIComponent(e.part_number)}`} className="link-more">
            {e.part_number}
          </Link>{' '}
          ({e.status_label})
        </span>
      ))}
      .
    </p>
  )
}

const tone = (label: string) => (label === 'In stock' ? 'tag-good' : label === 'Low stock' ? 'tag-warn' : label === 'On order' || label === 'Out of stock' ? 'tag-bad' : 'tag-plain')
const fitTone = (c: AgentCandidate) => (c.fitment_label === 'Confirmed fit' ? 'tag-good' : 'tag-warn')
const priceText = (c: AgentCandidate) => (c.part.price ? `${formatMoney(c.part.price)}${c.price_basis ? ` · ${c.price_basis}` : ''}` : 'Price not recorded')

/** The commercial action, truthful about what the demo can do: add to the cart, then review the order. Nothing is paid or placed here. */
function OrderAction({ c, machine, qty, compact = false }: { c: AgentCandidate; machine: string | null; qty: number | null; compact?: boolean }) {
  const { add } = useCart()
  const [added, setAdded] = useState(false)
  const orderable = c.order_action === 'add_to_cart' && canOrder(c.part.availability?.part_status, c.part.availability?.orderable)
  if (c.order_action === 'identify')
    return (
      <Link className="btn btn-secondary btn-sm" to={`${PI}?part=${encodeURIComponent(c.part.part_number)}&tab=store`}>
        Identification required
      </Link>
    )
  if (!orderable) return compact ? null : <span className="small muted">Not orderable online</span>
  if (added)
    return (
      <Link className="btn btn-accent btn-sm" to={CHECKOUT_ROUTE}>
        <Check size={15} strokeWidth={2.2} aria-hidden="true" /> Added · Review order
      </Link>
    )
  return (
    <button
      type="button"
      className={`btn ${compact ? 'btn-secondary' : 'btn-primary'} btn-sm`}
      onClick={() => {
        add(c.part.part_id, qty ?? 1, machine) // the machine the agent resolved goes with the part into the existing cart
        setAdded(true)
      }}
      aria-label={c.recommended ? undefined : `Add ${c.part.part_number} to cart`}
    >
      <ShoppingCart size={15} strokeWidth={1.8} aria-hidden="true" />
      {c.availability_label === 'On order' ? 'Add to cart · on order' : 'Add to cart'}
    </button>
  )
}

/** What the choice was made on, before the choice itself. */
function DecisionPanel({ d }: { d: NonNullable<AgentResponse['decision']> }) {
  return (
    <section className="card card-pad ag-decision" aria-labelledby="ag-decision-title">
      <h3 id="ag-decision-title" className="eyebrow">
        Decision
      </h3>
      <div className="ag-decision__grid">
        <div>
          <p className="small muted">Must meet</p>
          <ul className="chip-row">
            {d.requirements.map((x) => (
              <li key={x} className="chip">
                <Check size={13} strokeWidth={2.4} aria-hidden="true" /> {x}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="small muted">Ranked by</p>
          <ol className="ag-priorities">
            {d.priorities.map((x, n) => (
              <li key={x}>
                <span>{String(n + 1).padStart(2, '0')}</span> {x}
              </li>
            ))}
          </ol>
        </div>
      </div>
      <p className="ag-decision__summary">{d.summary}</p>
    </section>
  )
}

/** The recommended option, complete: every decision field has a value or a plain "not recorded" state. */
function Recommended({ c, machine, qty }: { c: AgentCandidate; machine: string | null; qty: number | null }) {
  const p = c.part
  const rows: [string, React.ReactNode][] = [
    ['Availability', <span key="a" className={`tag ${tone(c.availability_label)}`}><i className="tag-dot" aria-hidden="true" />{c.availability_label}</span>],
    ['Inventory', c.inventory],
    ['Fulfilment', c.fulfilment],
    ['Delivery', c.delivery],
    [c.suppliers.length > 1 ? 'Suppliers' : 'Supplier', c.suppliers.length > 1 ? c.suppliers.map((s) => s.name).join(', ') : c.supplier_label],
  ]
  return (
    <article className="reco-card card is-best ag-recommended" aria-labelledby="ag-rec-title">
      <span className="reco-best-badge">Recommended</span>
      <div className="ag-recommended__grid">
        <div className="ag-recommended__img">
          <PartImage partNumber={p.part_number} category={p.category} name={p.name} />
        </div>
        <div className="ag-recommended__main">
          <p className="part-number">{p.subcategory ?? p.category ?? 'Part'}</p>
          <h3 id="ag-rec-title" className="reco-title">
            {p.part_number}
          </h3>
          <p className="muted reco-name">{p.name}</p>
          <div className="reco-tags">
            <span className={`tag ${fitTone(c)}`}>{c.fitment_label}</span>
            {p.availability?.part_status === 'VERIFIED' ? <span className="tag tag-good">Verified</span> : null}
            {c.within_budget === true ? <span className="tag tag-info">Within budget</span> : null}
          </div>
          <p className="reco-price">
            {p.price ? formatMoney(p.price) : 'Price not recorded'} {c.price_basis ? <span className="small muted">{c.price_basis}</span> : null}
          </p>
          <div className="reco-actions">
            <OrderAction c={c} machine={machine} qty={qty} />
            <Link className="btn btn-secondary btn-sm" to={partPath(p.part_number)}>
              View part
            </Link>
            <Link className="btn btn-secondary btn-sm" to={`${PI}?part=${encodeURIComponent(p.part_number)}`}>
              View evidence
            </Link>
          </div>
          {c.order_note ? <p className="small muted">{c.order_note}</p> : null}
        </div>
        <dl className="kv-list ag-recommended__facts">
          {rows.map(([k, v]) => (
            <div key={k} className="kv-row">
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          {c.stock_locations.length > 1 ? (
            <div className="kv-row ag-stock">
              <dt>By warehouse</dt>
              <dd>
                {c.stock_locations.map((w) => (
                  <small key={w.warehouse}>
                    {w.city ?? w.warehouse} · {w.available}
                  </small>
                ))}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>
    </article>
  )
}

function Why({ r, best }: { r: AgentResponse; best: AgentCandidate }) {
  return (
    <section className="card card-pad ag-why" aria-labelledby="ag-why-title">
      <h3 id="ag-why-title">Why {best.part.part_number}?</h3>
      <ol className="ag-why__list">
        {r.why.map((w, n) => (
          <li key={w.title}>
            <span className="ag-why__n">{String(n + 1).padStart(2, '0')}</span>
            <div>
              <p className="ev-title">{w.title}</p>
              <p className="ev-detail">{w.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** Where each kind of fact comes from, so the commercial fields above can stay clean. */
function HowWeKnow({ r, best }: { r: AgentResponse; best: AgentCandidate }) {
  return (
    <section className="card card-pad ag-how" aria-labelledby="ag-how-title">
      <div className="spread">
        <h3 id="ag-how-title">How we know</h3>
        <Link className="link-more" to={`${PI}?part=${encodeURIComponent(best.part.part_number)}`}>
          View evidence in Parts Intelligence →
        </Link>
      </div>
      <dl className="kv-list">
        {r.how_we_know.map((h) => (
          <div key={h.label} className="kv-row">
            <dt>{h.label}</dt>
            <dd>{h.value}</dd>
          </div>
        ))}
      </dl>
      <ul className="evidence-list">
        {r.evidence.filter((e) => e.key !== 'ranking').map((e) => (
          <li key={e.key} className={`ev-item ${e.ok ? 'is-ok' : 'is-warn'}`}>
            <span className="ev-mark" aria-hidden="true">
              {e.ok ? '✓' : '!'}
            </span>
            <p className="ev-detail">
              <strong>{e.label}</strong> · {e.detail}
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The valid alternatives to the recommendation; the recommendation itself is never repeated here. */
function Alternatives({ r }: { r: AgentResponse }) {
  const alts = r.candidates.filter((c) => !c.recommended)
  return (
    <section className="card card-pad ag-opts" aria-labelledby="ag-opts-title">
      <h3 id="ag-opts-title">Alternatives</h3>
      {alts.length === 0 ? (
        <p className="pi-empty">{r.notes.some((n) => n.startsWith('Not considered') || n.startsWith('Over your')) ? 'No other verified compatible option meets your requirements.' : 'No other verified compatible options were found.'}</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table ag-table">
            <thead>
              <tr>
                <th scope="col">Part</th>
                <th scope="col">Price</th>
                <th scope="col">Fitment</th>
                <th scope="col">Availability</th>
                <th scope="col">Fulfilment</th>
                <th scope="col">Supplier</th>
                <th scope="col">Reason</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {alts.map((c) => (
                <tr key={c.part.part_id}>
                  <th scope="row">
                    <Link to={partPath(c.part.part_number)} className="link-more">
                      {c.part.part_number}
                    </Link>
                    <small>{c.part.name}</small>
                  </th>
                  <td data-label="Price">{priceText(c)}</td>
                  <td data-label="Fitment">{c.fitment_label}</td>
                  <td data-label="Availability">{c.availability_label}</td>
                  <td data-label="Fulfilment">{c.fulfilment}</td>
                  <td data-label="Supplier">{c.supplier_label}</td>
                  <td data-label="Reason">{c.tradeoffs.length ? c.tradeoffs.join(' · ') : 'Ranks lower on your priorities'}</td>
                  <td className="ag-table__act">
                    <div className="row">
                      <Link className="link-more" to={partPath(c.part.part_number)}>
                        View →
                      </Link>
                      <OrderAction c={c} machine={r.interpretation.machine} qty={r.interpretation.quantity} compact />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
