import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type ReactNode,
} from 'react'
import {
  Box,
  Building2,
  Factory,
  Focus,
  Link2,
  Minus,
  Network,
  Package,
  Plus,
  ScanLine,
  ShieldCheck,
  Truck,
  Warehouse,
  Expand,
  X,
} from 'lucide-react'
import type { GraphNode, GraphView } from '../../api/intelligenceTypes'
import { humanize } from '../../lib/format'
import { ProvenanceBadge } from './provenance'
import { graphPositions, type Point } from './graphModel'
import './graph-explorer.css'

const LOOKS: Record<string, { fill: string; ink: string; icon: typeof Box }> = {
  PART: { fill: '#dcf0e6', ink: '#205e45', icon: Package },
  MACHINE: { fill: '#dfebfb', ink: '#2b548e', icon: Factory },
  SUPPLIER: { fill: '#eae3fb', ink: '#644292', icon: Building2 },
  DEALER: { fill: '#fce9d8', ink: '#92512b', icon: Building2 },
  WAREHOUSE: { fill: '#f5ebc7', ink: '#806420', icon: Warehouse },
  ASSEMBLY: { fill: '#d9eef0', ink: '#24676b', icon: Box },
  COMPLIANCE: { fill: '#f9dfeb', ink: '#96385e', icon: ShieldCheck },
  CATEGORY: { fill: '#e7ece4', ink: '#53654d', icon: ScanLine },
  ORDER: { fill: '#eee5d8', ink: '#796044', icon: Package },
  SHIPMENT: { fill: '#dfe8f5', ink: '#425e84', icon: Truck },
}
const fallback = { fill: '#e8ecef', ink: '#52646f', icon: Network }

export function GraphExplorer({
  view,
  onOpen,
  renderDetail,
  label = 'Relationships',
  allowExpand = true,
}: {
  view: GraphView
  onOpen?: (part: string) => void
  renderDetail?: (node: GraphNode) => ReactNode
  label?: string
  allowExpand?: boolean
}) {
  const svg = useRef<SVGSVGElement>(null)
  const expanded = useRef<HTMLDialogElement>(null)
  const marker = useId().replaceAll(':', '')
  const base = useMemo(() => graphPositions(view), [view])
  const [moves, setMoves] = useState<Record<string, Point>>({})
  const [selectedId, setSelected] = useState(view.nodes[0]?.id ?? '')
  const [relation, setRelation] = useState('all'),
    [search, setSearch] = useState('')
  const [camera, setCamera] = useState(() => {
    const points = Object.values(base)
    if (!points.length) return { x: 0, y: 0, scale: 1 }
    const minX = Math.min(...points.map((p) => p.x)) - 100
    const maxX = Math.max(...points.map((p) => p.x)) + 100
    const minY = Math.min(...points.map((p) => p.y)) - 70
    const maxY = Math.max(...points.map((p) => p.y)) + 90
    const scale = Math.min(1.5, 940 / (maxX - minX), 560 / (maxY - minY))
    return { scale, x: 500 - ((minX + maxX) / 2) * scale, y: 300 - ((minY + maxY) / 2) * scale }
  })
  const drag = useRef<{ id: string | null; start: Point; origin: Point } | null>(null)
  // the drawing is 1000 units wide; in a narrow column (the chat) it shrinks, so its text is enlarged to stay legible, capped so labels do not collide
  useEffect(() => {
    const el = svg.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => {
      const k = Math.min(1.8, Math.max(1, 1000 / Math.max(1, entry.contentRect.width)))
      el.style.setProperty('--gx-k', k.toFixed(2))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const positions = { ...base, ...moves }
  const selected = view.nodes.find((node) => node.id === selectedId)
  const byId = new Map(view.nodes.map((node) => [node.id, node]))
  const types = [...new Set(view.edges.map((edge) => edge.type))].sort()
  const edges = view.edges.filter((edge) => relation === 'all' || edge.type === relation)
  const matches = new Set(
    view.nodes
      .filter((node) => node.label.toLowerCase().includes(search.toLowerCase()))
      .map((node) => node.id),
  )
  const displayedEdges = edges.filter(
    (edge) => !search || matches.has(edge.source) || matches.has(edge.target),
  )
  // edges between the same two records are fanned out; group them once instead of re-scanning every edge for each edge
  const sameEnds = new Map<string, typeof displayedEdges>()
  for (const edge of displayedEdges) {
    const key = `${edge.source}\u0000${edge.target}`
    sameEnds.set(key, [...(sameEnds.get(key) ?? []), edge])
  }
  const displayedIds = new Set(displayedEdges.flatMap((edge) => [edge.source, edge.target]))
  const nodes = view.nodes.filter(
    (node) =>
      (relation === 'all' && !search) ||
      displayedIds.has(node.id) ||
      (search && matches.has(node.id)),
  )
  const connected = displayedEdges.filter(
    (edge) => edge.source === selectedId || edge.target === selectedId,
  )
  const neighbourIds = new Set(connected.flatMap((edge) => [edge.source, edge.target]))
  function point(event: PointerEvent): Point {
    const ctm = svg.current?.getScreenCTM()
    if (!ctm) return { x: 0, y: 0 }
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(ctm.inverse())
    return { x: p.x, y: p.y }
  }
  function begin(event: PointerEvent<SVGSVGElement | SVGGElement>, id: string | null) {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    if (id) setSelected(id)
    svg.current?.setPointerCapture(event.pointerId)
    drag.current = {
      id,
      start: point(event),
      origin: id ? positions[id] : { x: camera.x, y: camera.y },
    }
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return
    const current = point(event),
      { id, start, origin } = drag.current
    const dx = current.x - start.x,
      dy = current.y - start.y
    if (id)
      setMoves((previous) => ({
        ...previous,
        [id]: { x: origin.x + dx / camera.scale, y: origin.y + dy / camera.scale },
      }))
    else setCamera((previous) => ({ ...previous, x: origin.x + dx, y: origin.y + dy }))
  }
  const zoom = (factor: number) =>
    setCamera((previous) => {
      const scale = Math.max(0.25, Math.min(3, previous.scale * factor)),
        ratio = scale / previous.scale
      return { scale, x: 500 - (500 - previous.x) * ratio, y: 300 - (300 - previous.y) * ratio }
    })
  const fit = () => {
    if (!nodes.length) return
    const points = nodes.map((node) => positions[node.id]),
      xs = points.map((p) => p.x),
      ys = points.map((p) => p.y)
    const minX = Math.min(...xs) - 100,
      maxX = Math.max(...xs) + 100,
      minY = Math.min(...ys) - 70,
      maxY = Math.max(...ys) + 90
    const scale = Math.min(1.5, 940 / (maxX - minX), 560 / (maxY - minY))
    setCamera({ scale, x: 500 - ((minX + maxX) / 2) * scale, y: 300 - ((minY + maxY) / 2) * scale })
  }
  if (!view.nodes.length)
    return (
      <p className="gx-empty">
        No relationship evidence is available for this view. No connections have been inferred.
      </p>
    )
  return (
    <section className="gx" aria-label={label}>
      <div className="gx-toolbar">
        <label>
          <span className="sr-only">Search graph records</span>
          <input
            type="search"
            placeholder="Find a record…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          <span className="sr-only">Relationship type</span>
          <select
            aria-label="Relationship type"
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
          >
            <option value="all">All relationships</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {humanize(type)}
              </option>
            ))}
          </select>
        </label>
        <span className="gx-count">
          {nodes.length} records · {displayedEdges.length}{' '}
          {displayedEdges.length === 1 ? 'connection' : 'connections'}
        </span>
        <div className="gx-zoom">
          {allowExpand ? (
            <button
              type="button"
              aria-label="Open full screen graph"
              onClick={() => expanded.current?.showModal()}
            >
              <Expand size={17} />
            </button>
          ) : null}
          <button type="button" aria-label="Zoom out graph" onClick={() => zoom(1 / 1.2)}>
            <Minus size={16} />
          </button>
          <span>{Math.round(camera.scale * 100)}%</span>
          <button type="button" aria-label="Zoom in graph" onClick={() => zoom(1.2)}>
            <Plus size={16} />
          </button>
          <button type="button" aria-label="Fit graph to view" onClick={fit}>
            <Focus size={17} />
          </button>
        </div>
      </div>
      <div className="gx-workspace">
        <div className="gx-canvas">
          <svg
            ref={svg}
            viewBox="0 0 1000 620"
            role="group"
            aria-label={label + ' graph'}
            onPointerDown={(e) => begin(e, null)}
            onPointerMove={move}
            onPointerUp={() => {
              drag.current = null
            }}
            onPointerCancel={() => {
              drag.current = null
            }}
          >
            <defs>
              <pattern id={`${marker}-dots`} width="24" height="24" patternUnits="userSpaceOnUse">
                <circle cx="1" cy="1" r="1" fill="#d7e0d8" />
              </pattern>
              <marker
                id={`${marker}-arrow`}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#7e9387" />
              </marker>
            </defs>
            <rect width="1000" height="620" fill={`url(#${marker}-dots)`} />
            <g transform={`translate(${camera.x} ${camera.y}) scale(${camera.scale})`}>
              {displayedEdges.map((edge, index) => {
                const a = positions[edge.source],
                  b = positions[edge.target]
                if (!a || !b) return null
                const dx = b.x - a.x,
                  dy = b.y - a.y,
                  len = Math.max(1, Math.hypot(dx, dy)),
                  ux = dx / len,
                  uy = dy / len
                const x1 = a.x + ux * 29,
                  y1 = a.y + uy * 29,
                  x2 = b.x - ux * 32,
                  y2 = b.y - uy * 32
                const active = edge.source === selectedId || edge.target === selectedId
                const duplicates = sameEnds.get(`${edge.source}\u0000${edge.target}`) ?? [edge]
                const offset = (duplicates.indexOf(edge) - (duplicates.length - 1) / 2) * 30
                const cx = (x1 + x2) / 2 - uy * offset,
                  cy = (y1 + y2) / 2 + ux * offset
                let angle = (Math.atan2(dy, dx) * 180) / Math.PI
                if (angle > 90 || angle < -90) angle += 180
                const undirected =
                  edge.directed === false ||
                  ['RELATED_COMPONENT', 'CO_ORDERED_WITH', 'SAME_NAME_GROUP_AS'].includes(edge.type)
                return (
                  <g
                    key={`${edge.source}:${edge.type}:${edge.target}:${index}`}
                    className={`gx-edge${active ? ' is-active' : ''}${edge.data_class === 'SYNTHETIC_DEMO' ? ' is-demo' : ''}`}
                    opacity={selectedId && !active ? 0.3 : 1}
                  >
                    <path
                      d={`M${x1},${y1} Q${cx},${cy} ${x2},${y2}`}
                      markerEnd={undirected ? undefined : `url(#${marker}-arrow)`}
                    />
                    <text
                      x={cx}
                      y={cy - 7}
                      textAnchor="middle"
                      transform={`rotate(${angle} ${cx} ${cy - 7})`}
                    >
                      {humanize(edge.type)}
                    </text>
                  </g>
                )
              })}
              {nodes.map((node) => {
                const p = positions[node.id],
                  look = LOOKS[node.kind] ?? fallback,
                  Icon = look.icon,
                  active = node.id === selectedId
                return (
                  <g
                    key={node.id}
                    transform={`translate(${p.x} ${p.y})`}
                    className={`gx-node${active ? ' is-selected' : ''}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${humanize(node.kind)}: ${node.label}`}
                    aria-pressed={active}
                    opacity={
                      selectedId && node.id !== selectedId && !neighbourIds.has(node.id) ? 0.45 : 1
                    }
                    onPointerDown={(event) => begin(event, node.id)}
                    onClick={() => setSelected(node.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelected(node.id)
                      }
                    }}
                  >
                    <title>{node.label}</title>
                    <circle
                      r={active ? 31 : 27}
                      fill={look.fill}
                      stroke={active ? look.ink : '#fff'}
                      strokeWidth={active ? 2.5 : 2}
                    />
                    <Icon
                      x={-11}
                      y={-11}
                      size={22}
                      color={look.ink}
                      strokeWidth={1.7}
                      aria-hidden="true"
                    />
                    <text y="47" textAnchor="middle">
                      {node.label.length > 23 ? node.label.slice(0, 21) + '…' : node.label}
                    </text>
                    <text y="63" textAnchor="middle" className="gx-node-kind">
                      {humanize(node.kind)}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
          {!nodes.length ? (
            <p className="gx-no-match">
              No matching records. Clear the search or change the relationship filter.
            </p>
          ) : null}
          <p className="gx-hint">
            Drag records to arrange · drag the canvas to pan · select a record to inspect
          </p>
        </div>
        <aside className="gx-inspector" aria-label="Selected graph record">
          <p className="eyebrow">{selected ? humanize(selected.kind) : 'Select a record'}</p>
          <h3>{selected?.label}</h3>
          <p className="gx-inspector__count">
            {connected.length} recorded {connected.length === 1 ? 'connection' : 'connections'}
          </p>
          {connected.map((edge, index) => (
            <div className="gx-connection" key={`${edge.type}:${index}`}>
              <span>
                <Link2 size={13} aria-hidden="true" />
                {humanize(edge.type)}
              </span>
              <p>
                {byId.get(edge.source)?.label}{' '}
                <span aria-hidden="true">
                  {edge.directed === false ||
                  ['RELATED_COMPONENT', 'CO_ORDERED_WITH', 'SAME_NAME_GROUP_AS'].includes(edge.type)
                    ? '↔'
                    : '→'}
                </span>{' '}
                {byId.get(edge.target)?.label}
              </p>
              <ProvenanceBadge value={edge.data_class} />
            </div>
          ))}
          {selected?.part_number && onOpen ? (
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              onClick={() => onOpen(selected.part_number!)}
            >
              Investigate part
            </button>
          ) : null}
          {selected && renderDetail ? renderDetail(selected) : null}
          {selected ? (
            <details>
              <summary>Record reference</summary>
              <code>{selected.id}</code>
            </details>
          ) : null}
        </aside>
      </div>
      <div className="gx-legend">
        {[...new Set(nodes.map((node) => node.kind))].map((kind) => (
          <span key={kind}>
            <i
              style={{
                background: (LOOKS[kind] ?? fallback).fill,
                borderColor: (LOOKS[kind] ?? fallback).ink,
              }}
            />
            {humanize(kind)}
          </span>
        ))}
        <span className="gx-legend__data">
          Dashed: synthetic demo data · solid: source or derived data
        </span>
      </div>
      {view.truncated ? (
        <p className="gx-limit">
          The service returned a limited neighbourhood. Use the related sections for full counts.
        </p>
      ) : null}
      {allowExpand ? (
        <dialog ref={expanded} className="gx-fullscreen" aria-label="Full screen relationships">
          <div className="gx-fullscreen__header">
            <strong>{label}</strong>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => expanded.current?.close()}
              aria-label="Close full screen graph"
            >
              <X size={18} /> Close
            </button>
          </div>
          <GraphExplorer
            view={view}
            onOpen={onOpen}
            renderDetail={renderDetail}
            label={label}
            allowExpand={false}
          />
        </dialog>
      ) : null}
    </section>
  )
}
