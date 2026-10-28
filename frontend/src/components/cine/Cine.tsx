import { useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { CountUp } from '../CountUp'
import { useInView } from '../../hooks/useInView'
import { useScrollProgress } from './useScrollProgress'
import './cine.css'

/**
 * The shared cinematic layer: one page-opening pattern, one stat strip, two charts and an animated graph field.
 * Everything here is presentation only. Numbers and labels are passed in from data the backend returned; nothing is invented.
 */

type Stat = { value: number; label: string }

/** Title lines rise into place one after another. Screen readers get the plain title. */
export function SplitTitle({
  lines,
  as: Tag = 'h1',
  id,
}: {
  lines: string[]
  as?: 'h1' | 'h2'
  id?: string
}) {
  return (
    <Tag className="cine-title" id={id} aria-label={lines.join(' ')}>
      {lines.map((line, index) => (
        <span className="cine-title__line" key={line} aria-hidden="true">
          <span style={{ '--line': index } as CSSProperties}>{line}</span>
        </span>
      ))}
    </Tag>
  )
}

/**
 * The opening of an inner page: an animated gradient field with a drifting grid, an optional image that moves slower than the page
 * (parallax), a split title and an optional row of counted statistics.
 */
export function CineHero({
  eyebrow,
  lines,
  lead,
  image,
  actions,
  stats,
  children,
  tone = 'dark',
  id,
}: {
  eyebrow: string
  lines: string[]
  lead?: ReactNode
  image?: string
  actions?: ReactNode
  stats?: Stat[]
  children?: ReactNode
  tone?: 'dark' | 'light'
  id: string
}) {
  const root = useRef<HTMLElement>(null)
  const progress = useScrollProgress(root, 0.5)
  return (
    <section
      ref={root}
      className={`cine-hero cine-hero--${tone}`}
      aria-labelledby={id}
      style={{ '--p': progress } as CSSProperties}
    >
      <div className="cine-hero__field" aria-hidden="true">
        {image ? <img className="cine-hero__image" src={image} alt="" /> : null}
        <span className="cine-hero__aurora" />
        <span className="cine-hero__grid" />
      </div>
      <div className="container cine-hero__inner">
        <p className="cine-eyebrow">{eyebrow}</p>
        <SplitTitle lines={lines} id={id} />
        {lead ? <div className="cine-hero__lead">{lead}</div> : null}
        {actions ? <div className="cine-hero__actions">{actions}</div> : null}
        {children}
      </div>
      {stats?.length ? (
        <div className="container">
          <StatStrip stats={stats} />
        </div>
      ) : null}
    </section>
  )
}

export function StatStrip({ stats }: { stats: Stat[] }) {
  return (
    <dl className="cine-stats">
      {stats.map((stat) => (
        <div key={stat.label}>
          <dt>{stat.label}</dt>
          <dd>
            <CountUp value={stat.value} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** Horizontal bars that grow when they come into view. Values are drawn relative to the largest one. With `onSelect` each row is a toggle button. */
export function BarChart({
  rows,
  label,
  selected,
  onSelect,
}: {
  rows: { name: string; value: number }[]
  label: string
  selected?: string | null
  onSelect?: (name: string | null) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.25 })
  const max = Math.max(1, ...rows.map((row) => row.value))
  if (onSelect)
    return (
      <div
        ref={ref}
        className={`cine-bars cine-bars--select${inView ? ' is-in' : ''}`}
        role="group"
        aria-label={label}
      >
        {rows.map((row, index) => (
          <button
            type="button"
            key={row.name}
            aria-pressed={selected === row.name}
            onClick={() => onSelect(selected === row.name ? null : row.name)}
            style={{ '--w': row.value / max, '--i': index } as CSSProperties}
          >
            <span className="cine-bars__name">{row.name}</span>
            <span className="cine-bars__track" aria-hidden="true">
              <i />
            </span>
            <span className="cine-bars__value">{row.value}</span>
          </button>
        ))}
      </div>
    )
  return (
    <div ref={ref} className={`cine-bars${inView ? ' is-in' : ''}`} role="table" aria-label={label}>
      {rows.map((row, index) => (
        <div
          role="row"
          key={row.name}
          style={{ '--w': row.value / max, '--i': index } as CSSProperties}
        >
          <span role="rowheader" className="cine-bars__name">
            {row.name}
          </span>
          <span role="cell" className="cine-bars__track">
            <i />
          </span>
          <span role="cell" className="cine-bars__value">
            {row.value}
          </span>
        </div>
      ))}
    </div>
  )
}

/** A ring split by share, drawn on entering the viewport, with a legend that carries the actual counts. */
export function Donut({
  rows,
  label,
  total,
}: {
  rows: { name: string; value: number }[]
  label: string
  total: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.3 })
  const [focus, setFocus] = useState<number | null>(null)
  const sum = rows.reduce((n, row) => n + row.value, 0) || 1
  const arcs = arcsOf(rows, sum)
  return (
    <figure ref={ref} className={`cine-donut${inView ? ' is-in' : ''}`} aria-label={label}>
      <div className="cine-donut__ring">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle className="cine-donut__base" cx="60" cy="60" r="48" pathLength={1} />
          {arcs.map((arc) => (
            <circle
              key={arc.name}
              className={`cine-donut__arc${focus !== null && focus !== arc.index ? ' is-dim' : ''}${focus === arc.index ? ' is-focus' : ''}`}
              cx="60"
              cy="60"
              r="48"
              pathLength={1}
              style={
                {
                  '--share': Math.max(0, arc.share - 0.008),
                  '--offset': arc.offset,
                  '--i': arc.index,
                } as CSSProperties
              }
            />
          ))}
        </svg>
        <div className="cine-donut__centre" aria-hidden="true">
          <strong>{focus === null ? sum : arcs[focus].value}</strong>
          <span>{focus === null ? total : arcs[focus].name}</span>
        </div>
      </div>
      <figcaption>
        <ul>
          {arcs.map((arc) => (
            <li key={arc.name} style={{ '--i': arc.index } as CSSProperties}>
              <button
                type="button"
                aria-pressed={focus === arc.index}
                onPointerEnter={() => setFocus(arc.index)}
                onPointerLeave={() => setFocus(null)}
                onFocus={() => setFocus(arc.index)}
                onBlur={() => setFocus(null)}
                onClick={() => setFocus(focus === arc.index ? null : arc.index)}
              >
                <i aria-hidden="true" />
                {arc.name} <b>{arc.value}</b>
              </button>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  )
}

/** Decorative: a slowly breathing network of nodes and links, laid out deterministically from a seed. */
export function NetworkField({ nodes = 26, seed = 7 }: { nodes?: number; seed?: number }) {
  const graph = useMemo(() => buildGraph(nodes, seed), [nodes, seed])
  return (
    <svg
      className="cine-network"
      viewBox="0 0 1000 500"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {graph.links.map((link) => (
        <line
          key={link.index}
          x1={link.a.x}
          y1={link.a.y}
          x2={link.b.x}
          y2={link.b.y}
          pathLength={1}
          style={{ '--i': link.index } as CSSProperties}
        />
      ))}
      {graph.points.map((point) => (
        <circle
          key={point.index}
          cx={point.x}
          cy={point.y}
          r={point.r}
          style={{ '--i': point.index } as CSSProperties}
        />
      ))}
    </svg>
  )
}

/** A business process as a line of stations that draws itself when it scrolls into view. Each station can link to where that step happens. */
export function ProcessFlow({
  steps,
  label,
}: {
  steps: { title: string; text: string; to?: string }[]
  label: string
}) {
  const ref = useRef<HTMLOListElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.3 })
  return (
    <ol
      ref={ref}
      className={`cine-flow${inView ? ' is-in' : ''}`}
      aria-label={label}
      style={{ '--n': steps.length } as CSSProperties}
    >
      {steps.map((step, index) => (
        <li key={step.title} style={{ '--i': index } as CSSProperties}>
          <span className="cine-flow__node" aria-hidden="true">
            {String(index + 1).padStart(2, '0')}
          </span>
          {step.to ? (
            <a href={step.to}>
              <strong>{step.title}</strong>
            </a>
          ) : (
            <strong>{step.title}</strong>
          )}
          <p>{step.text}</p>
        </li>
      ))}
    </ol>
  )
}

function arcsOf(rows: { name: string; value: number }[], sum: number) {
  const arcs: { name: string; value: number; share: number; offset: number; index: number }[] = []
  for (const [index, row] of rows.entries()) {
    const before = arcs.at(-1)
    arcs.push({
      ...row,
      share: row.value / sum,
      offset: before ? before.offset + before.share : 0,
      index,
    })
  }
  return arcs
}

function buildGraph(nodes: number, seed: number) {
  let state = seed
  const random = () => {
    state = (state * 16807) % 2147483647
    return state / 2147483647
  }
  const points = Array.from({ length: nodes }, (_, index) => ({
    x: 40 + random() * 920,
    y: 40 + random() * 420,
    r: 2.5 + random() * 4,
    index,
  }))
  const links: { a: (typeof points)[number]; b: (typeof points)[number]; index: number }[] = []
  for (const a of points)
    points
      .filter((b) => b.index > a.index)
      .sort((p, q) => Math.hypot(p.x - a.x, p.y - a.y) - Math.hypot(q.x - a.x, q.y - a.y))
      .slice(0, 2)
      .forEach((b) => links.push({ a, b, index: links.length }))
  return { points, links }
}
