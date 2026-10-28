import { useEffect, useId, useRef, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  X,
  Building2,
  ClipboardList,
  PackageSearch,
  Truck,
  Headphones,
  Search,
  ShieldCheck,
  ShoppingBag,
  FileCheck,
  MessagesSquare,
  Network,
  Scale,
  Workflow,
  Pause,
  Play,
} from 'lucide-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import './business-journey.css'

type Step = { name: string; who: string; action: string; outcome: string; handoff: string }
type Journey = {
  title: string
  description: string
  steps: Step[]
  note: string
  to: string
  cta: string
}
const journeys: Record<'aftersales' | 'portal' | 'spark', Journey> = {
  aftersales: {
    title: 'The business behind the service.',
    description: 'Follow the hand-offs between the dealer, Noordveld, suppliers and finance.',
    steps: [
      {
        name: 'Establish the relationship',
        who: 'Dealer or customer · Noordveld',
        action:
          'Register the dealer, customer and installed machine. Agree account and commercial terms.',
        outcome: 'A known account, machine and service relationship.',
        handoff:
          'Dealer onboarding and account terms are reference activities, not implemented onboarding screens.',
      },
      {
        name: 'Identify the need',
        who: 'Dealer or customer · Service team',
        action:
          'Describe the parts or service need. Confirm the machine and clarify missing details.',
        outcome: 'A specific request linked to the right machine.',
        handoff:
          'Parts Portal and Spark support parts discovery. Broader service intake remains a reference activity.',
      },
      {
        name: 'Check and source',
        who: 'Parts team · Supplier',
        action:
          'Check recorded fitment, ordering eligibility and stock. Send replenishment needs to procurement.',
        outcome: 'A suitable supply option, or an explicit shortage to resolve.',
        handoff:
          'Supplier procurement, goods receipt and supplier invoices connect to stock and accounts payable. These are reference integrations.',
      },
      {
        name: 'Fulfil the request',
        who: 'Order team · Warehouse · Delivery partner',
        action:
          'Review the order, apply commercial checks, allocate stock and follow dispatch and delivery.',
        outcome: 'A fulfilled order, or a visible exception with a responsible team.',
        handoff:
          'The demo supports parts orders and delivery visibility. Company-specific credit and approval policies must be confirmed.',
      },
      {
        name: 'Close and support',
        who: 'Finance · Dealer or customer · Service team',
        action:
          'Connect the customer invoice to finance, reconcile payment and retain the history for service, returns or warranty.',
        outcome: 'A completed commercial cycle and a continuing service relationship.',
        handoff:
          'Customer invoices connect to accounts receivable. Finance posting and the full returns process are reference integrations, not live capabilities.',
      },
    ],
    note: 'Reference business process. Credit limits, payment terms, approvals and system ownership must be agreed with the business.',
    to: '/parts-store',
    cta: 'Explore Parts Portal',
  },
  portal: {
    title: 'From finding a part to receiving it.',
    description: 'Follow an order from the machine and catalogue to delivery and support.',
    steps: [
      {
        name: 'Identify',
        who: 'Dealer or customer',
        action: 'Find the machine and part in the catalogue, or ask Spark to investigate.',
        outcome: 'A part and the machine it is intended for.',
        handoff: 'Clarify uncertain identification before purchasing.',
      },
      {
        name: 'Check',
        who: 'Parts team · Dealer or customer',
        action: 'Check recorded fitment, ordering eligibility, stock and price.',
        outcome: 'An eligible option, or a clear reason it cannot be ordered.',
        handoff:
          'Fitment alone does not mean a part is verified for ordering. Commercial values are labelled demo data.',
      },
      {
        name: 'Review and order',
        who: 'Dealer or customer · Order team',
        action:
          'Review quantities, destination, delivery choices and totals, then explicitly confirm the order.',
        outcome: 'A confirmed order ready for processing.',
        handoff:
          'Company-specific credit or approval checks must be agreed. The assistant does not place the order for you.',
      },
      {
        name: 'Fulfil and deliver',
        who: 'Order team · Warehouse · Delivery partner',
        action: 'Process the order, allocate stock, dispatch and follow delivery.',
        outcome: 'Delivery visibility and an order history.',
        handoff:
          'Shortages may require replenishment or back-order handling. Available actions depend on recorded supply and the implemented workflow.',
      },
      {
        name: 'Invoice and support',
        who: 'Finance · Service team',
        action:
          'Connect the order to invoicing and payment, retaining the records needed for support.',
        outcome: 'A financial hand-off and traceable service history.',
        handoff:
          'Finance posting and payment collection are reference integrations. This demonstration takes no payment.',
      },
    ],
    note: 'The catalogue and order demo support part of this journey. Financial and company-specific hand-offs are identified separately.',
    to: '/parts-services',
    cta: 'See the wider aftersales journey',
  },
  spark: {
    title: 'One conversation, through the parts journey.',
    description: 'Move from a question to evidence, a recommendation and a decision you control.',
    steps: [
      {
        name: 'Describe the need',
        who: 'You · Spark',
        action:
          'Ask in your own words. If a part, machine or reference is unclear, Spark asks for the missing detail.',
        outcome: 'A request with enough context to investigate.',
        handoff: 'Your clarification continues the existing conversation.',
      },
      {
        name: 'Check the records',
        who: 'Spark · Connected records',
        action:
          'Identify the part and machine, then retrieve relevant fitment, suppliers, stock or authorised account records.',
        outcome: 'An answer grounded in recorded evidence.',
        handoff: 'Ask to see the connections in a graph. Unknown information remains unknown.',
      },
      {
        name: 'Compare the options',
        who: 'Spark · Supply records',
        action:
          'Compare eligible parts against the machine, budget, quantity and destination you provide.',
        outcome:
          'A recommendation with recorded price, availability and delivery information—or an explanation of what prevents one.',
        handoff:
          'Changing a constraint prompts a new check. Ordering restrictions remain in place.',
      },
      {
        name: 'Review the next action',
        who: 'You · Order team',
        action:
          'Inspect the recommendation, add an eligible part to the cart and review the order.',
        outcome: 'An informed choice that you confirm yourself.',
        handoff:
          'Order processing, fulfilment and financial hand-offs belong to the wider aftersales process.',
      },
    ],
    note: 'Spark complements your parts portal and existing systems. It does not replace business approvals or finance.',
    to: '/spark/chat',
    cta: 'Start a conversation',
  },
}

const stepIcons = {
  aftersales: [Building2, ClipboardList, PackageSearch, Truck, Headphones],
  portal: [Search, ShieldCheck, ShoppingBag, Truck, FileCheck],
  spark: [MessagesSquare, Network, Scale, ShoppingBag],
}

/** Lanes are the parties that lead a step, in the order they first act; each step sits in its lead's lane, so every hand-off is a change of lane. */
function lanesOf(steps: Step[]) {
  const lead = steps.map((s) => s.who.split(' · ')[0])
  return { lead, lanes: [...new Set(lead)] }
}

export function BusinessJourney({ kind }: { kind: keyof typeof journeys }) {
  const journey = journeys[kind]
  const [selected, setSelected] = useState<number | null>(0)
  const id = useId().replace(/:/g, '')
  const triggers = useRef<(HTMLButtonElement | null)[]>([])
  const detail = useRef<HTMLDivElement | null>(null)
  const step = selected === null ? null : journey.steps[selected]
  const { lead, lanes } = lanesOf(journey.steps)
  const count = journey.steps.length
  const [playing, setPlaying] = useState(false)
  const reduced =
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(
      () =>
        setSelected((current) => {
          const next = current === null ? 0 : current + 1
          if (next >= count) {
            setPlaying(false)
            return current
          }
          return next
        }),
      reduced ? 6000 : 3200,
    )
    return () => window.clearInterval(timer)
  }, [playing, count, reduced])
  const at = (index: number) => ({
    x: 7 + ((index + 0.5) / count) * 86, // inset so the first and last cards stay inside the board
    y: ((lanes.indexOf(lead[index]) + 0.5) / lanes.length) * 100,
  })
  const names = {
    aftersales: 'Aftersales',
    portal: 'Parts Portal',
    spark: 'Spark',
  }
  function move(index: number) {
    setSelected(index)
    if (window.matchMedia?.('(max-width: 700px)').matches) {
      detail.current?.scrollIntoView?.({ block: 'nearest' })
    }
  }
  return (
    <section
      className={`process-explorer process-explorer--${kind}`}
      aria-labelledby={`${id}-title`}
    >
      <header className="process-explorer__intro">
        <div>
          <p className="process-explorer__eyebrow">{names[kind]} / The process</p>
          <h2 id={`${id}-title`}>{journey.title}</h2>
        </div>
        <div>
          <p>{journey.description}</p>
          <span className="process-explorer__hint">
            <span /> Select any step to explore the hand-off
          </span>
        </div>
      </header>
      <div className="process-explorer__workspace">
        <div className="pj-map">
          <div className="pj-map__title">
            <span>
              {lanes.length} parties · {count} steps ·{' '}
              {lead.filter((who, i) => i && who !== lead[i - 1]).length} hand-offs
            </span>
            <button
              type="button"
              className="pj-play"
              aria-pressed={playing}
              onClick={() => {
                if (!playing) setSelected(0) // playing always tells the whole story from the first step
                setPlaying(!playing)
              }}
            >
              {playing ? (
                <Pause size={14} aria-hidden="true" />
              ) : (
                <Play size={14} aria-hidden="true" />
              )}
              {playing ? 'Pause' : 'Play the process'}
            </button>
          </div>
          <div
            className="pj-board"
            style={{ '--lanes': lanes.length, '--steps': count } as CSSProperties}
          >
            <ul className="pj-lanes" aria-label="Who leads each step">
              {lanes.map((lane) => (
                <li key={lane} className={step && lead[selected ?? -1] === lane ? 'is-active' : ''}>
                  <span>{lane}</span>
                </li>
              ))}
            </ul>
            <div className="pj-track">
              <svg className="pj-route" aria-hidden="true">
                {journey.steps.slice(0, -1).map((item, index) => {
                  const a = at(index)
                  const b = at(index + 1)
                  const reached = selected !== null && index < selected
                  return (
                    <g
                      key={item.name}
                      className={reached ? 'is-reached' : ''}
                      style={{ '--i': index } as CSSProperties}
                    >
                      <line x1={`${a.x}%`} y1={`${a.y}%`} x2={`${b.x}%`} y2={`${a.y}%`} />
                      {a.y !== b.y ? (
                        <line x1={`${b.x}%`} y1={`${a.y}%`} x2={`${b.x}%`} y2={`${b.y}%`} />
                      ) : null}
                    </g>
                  )
                })}
              </svg>
              <ol className="process-explorer__nodes pj-nodes">
                {journey.steps.map((item, index) => {
                  const Icon = stepIcons[kind][index]
                  const p = at(index)
                  const state =
                    selected === null
                      ? ''
                      : index < selected
                        ? 'is-done'
                        : index === selected
                          ? 'is-current'
                          : ''
                  return (
                    <li
                      key={item.name}
                      className={state}
                      style={{ '--x': `${p.x}%`, '--y': `${p.y}%`, '--i': index } as CSSProperties}
                    >
                      <button
                        ref={(node) => {
                          triggers.current[index] = node
                        }}
                        type="button"
                        aria-expanded={selected === index}
                        aria-controls={`${id}-detail`}
                        onClick={() => {
                          setPlaying(false)
                          move(index)
                        }}
                      >
                        <span className="pj-node__icon">
                          <Icon size={18} aria-hidden="true" />
                        </span>
                        <span className="pj-node__text">
                          <span className="pj-node__no">{String(index + 1).padStart(2, '0')}</span>
                          <strong>{item.name}</strong>
                          <small>{lead[index]}</small>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ol>
            </div>
          </div>
          <div className="process-explorer__map-foot">
            <span className="process-explorer__key">
              <span /> A change of lane is a business hand-off
            </span>
            <span>Select a step, or play the whole process</span>
          </div>
        </div>
        <div className="process-explorer__inspector" id={`${id}-detail`} ref={detail}>
          {step ? (
            <div
              role="region"
              aria-label={`${step.name} details`}
              className="process-explorer__details"
            >
              <div className="process-explorer__detail-heading">
                <span>
                  Step {String((selected ?? 0) + 1).padStart(2, '0')} /{' '}
                  {String(journey.steps.length).padStart(2, '0')}
                </span>
                <button
                  type="button"
                  aria-label="Close process step"
                  onClick={() => {
                    if (selected !== null) triggers.current[selected]?.focus()
                    setSelected(null)
                  }}
                >
                  <X size={17} aria-hidden="true" />
                </button>
              </div>
              <h3>{step.name}</h3>
              <p className="process-explorer__people">{step.who}</p>
              <p className="process-explorer__action">{step.action}</p>
              <div className="process-explorer__result">
                <ArrowRight size={18} aria-hidden="true" />
                <div>
                  <strong>What moves forward</strong>
                  <p>{step.outcome}</p>
                </div>
              </div>
              <details className="process-explorer__handoff">
                <summary>Before moving on</summary>
                <p>{step.handoff}</p>
              </details>
            </div>
          ) : (
            <div className="process-explorer__empty">
              <Workflow size={28} aria-hidden="true" />
              <h3>Follow the work.</h3>
              <p>Select a step to see who is involved, what happens and what moves forward.</p>
            </div>
          )}
          <div className="process-explorer__controls">
            <span role="status">
              {selected === null
                ? 'Choose a step to explore'
                : `Step ${selected + 1} of ${journey.steps.length} · ${step?.name}`}
            </span>
            <div>
              <button
                type="button"
                aria-label="Previous process step"
                disabled={selected === null || selected === 0}
                onClick={() => move((selected ?? 1) - 1)}
              >
                <ArrowLeft size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label="Next process step"
                disabled={selected === journey.steps.length - 1}
                onClick={() => move(selected === null ? 0 : selected + 1)}
              >
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>
      <footer className="process-explorer__foot">
        <p>{journey.note}</p>
        <Link to={journey.to}>
          {journey.cta}
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </footer>
    </section>
  )
}
