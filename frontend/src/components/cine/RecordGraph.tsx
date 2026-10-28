import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useInView } from '../../hooks/useInView'
import { useReducedMotion } from '../../hooks/useMediaQuery'
import { ArrowUpRight } from 'lucide-react'
import { apiGet } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { CountUp } from '../CountUp'
import { SparkLogo } from '../spark/SparkLogo'
import './record-graph.css'

type Kpis = {
  parts: number
  machines: number
  fitments: number
  suppliers: number
  dealers: number
  assemblies: number
  relationships: number
  nodes: number
}

/** What Spark reads, as a live graph: each record type with its current count, and what you can ask about it. */
const KINDS: {
  key: keyof Kpis
  label: string
  x: number
  y: number
  ask: string
  question: string
}[] = [
  {
    key: 'machines',
    label: 'Machines',
    x: 18,
    y: 26,
    ask: 'Which parts fit a machine, and which attachments it takes.',
    question: 'Which parts fit my machine?',
  },
  {
    key: 'parts',
    label: 'Parts',
    x: 50,
    y: 12,
    ask: 'What a part is, its specifications, price and status.',
    question: 'Help me find the right part for my machine',
  },
  {
    key: 'suppliers',
    label: 'Suppliers',
    x: 82,
    y: 26,
    ask: 'Who supplies a part, and their recorded lead times.',
    question: 'Who can supply a part, and how fast can they deliver?',
  },
  {
    key: 'dealers',
    label: 'Dealers',
    x: 82,
    y: 74,
    ask: 'Which dealers stock, service or receive a part near you.',
    question: 'Which dealers can help me with a part?',
  },
  {
    key: 'assemblies',
    label: 'Assemblies',
    x: 18,
    y: 74,
    ask: 'Which assembly a part belongs to, and what sits beside it.',
    question: 'Which assembly does a part belong to?',
  },
  {
    key: 'fitments',
    label: 'Fitments',
    x: 50,
    y: 88,
    ask: 'Recorded fitment between parts and machine models, with its status.',
    question: 'Which machines does a part I name fit?',
  },
]

export function RecordGraph({ chatRoute }: { chatRoute: string }) {
  const kpis = useApi(
    (signal) => apiGet<Kpis>('/intelligence/kpis', {}, signal),
    'record-graph-kpis',
  )
  const [active, setActive] = useState<(typeof KINDS)[number]['key']>('parts')
  const stage = useRef<HTMLDivElement>(null)
  const visible = useInView(stage)
  const reduced = useReducedMotion()
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused || reduced || !visible) return
    const timer = window.setInterval(() => {
      if (document.hidden) return
      setActive((key) => {
        const sequence = [
          'parts',
          'suppliers',
          'dealers',
          'fitments',
          'assemblies',
          'machines',
        ] as const
        return sequence[(sequence.indexOf(key as (typeof sequence)[number]) + 1) % sequence.length]
      })
    }, 4000)
    return () => window.clearInterval(timer)
  }, [paused, reduced, visible])
  const chosen = KINDS.find((kind) => kind.key === active)!
  const data = kpis.data
  return (
    <section className="rgraph" aria-labelledby="rgraph-title">
      <div className="rgraph__inner">
        <div className="rgraph__copy">
          <p className="cine-eyebrow">What Spark reads</p>
          <h2 id="rgraph-title">
            One connected record.
            <br />
            <em>Every answer traced back to it.</em>
          </h2>
          <p>
            Spark does not guess. It reads machines, parts, suppliers and dealers from one graph,
            then shows the evidence. Choose a record type to see what you can ask.
          </p>
          {data ? (
            <dl className="rgraph__totals">
              <div>
                <dt>Records</dt>
                <dd>
                  <CountUp value={data.nodes} />
                </dd>
              </div>
              <div>
                <dt>Connections</dt>
                <dd>
                  <CountUp value={data.relationships} />
                </dd>
              </div>
            </dl>
          ) : null}
        </div>
        <div className="rgraph__side">
          <div className="rgraph__stage" ref={stage}>
            {/* percentages, not a stretched viewBox: every connector is one unbroken line from Spark to its record type */}
            <svg aria-hidden="true">
              {KINDS.map((kind, index) => (
                <line
                  key={kind.key}
                  x1="50%"
                  y1="50%"
                  x2={`${kind.x}%`}
                  y2={`${kind.y}%`}
                  className={kind.key === active ? 'is-active' : ''}
                  style={{ '--i': index } as CSSProperties}
                />
              ))}
            </svg>
            <span className="rgraph__hub" aria-hidden="true">
              <SparkLogo size={58} />
            </span>
            <div className="rgraph__nodes" role="group" aria-label="Record types">
              {KINDS.map((kind, index) => (
                <button
                  key={kind.key}
                  type="button"
                  aria-pressed={kind.key === active}
                  onClick={() => {
                    setPaused(true)
                    setActive(kind.key)
                  }}
                  onFocus={() => setPaused(true)}
                  style={{ left: `${kind.x}%`, top: `${kind.y}%`, '--i': index } as CSSProperties}
                >
                  <strong>{data ? data[kind.key].toLocaleString('en') : '–'}</strong>
                  <span>{kind.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="rgraph__controls">
            <span>Explore the records, one connection at a time</span>
            {!reduced ? (
              <button type="button" onClick={() => setPaused(!paused)}>
                {paused ? 'Play sequence' : 'Pause sequence'}
              </button>
            ) : null}
          </div>
          <div className="rgraph__detail" aria-live={paused ? 'polite' : 'off'}>
            <strong>{chosen.label}</strong>
            <p>{chosen.ask}</p>
            <a href={`${chatRoute}?q=${encodeURIComponent(chosen.question)}`}>
              Ask: {chosen.question}
              <ArrowUpRight size={15} aria-hidden="true" />
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
