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

/** The one relationship type whose name the question mentions, else 'all'; the filter stays open for the rest. */
function focusedRelation(view: GraphView, focus: string, preferOne: boolean) {
  const text = focus.toLowerCase()
  if (!text) return preferOne ? firstRelation(view) : 'all'
  const noise = new Set([
    'for',
    'by',
    'has',
    'with',
    'from',
    'the',
    'and',
    'of',
    'to',
    'in',
    'at',
    'is',
    'as',
  ])
  const scored = [...new Set(view.edges.map((edge) => edge.type))]
    .map((type) => {
      const words = type
        .toLowerCase()
        .split('_')
        .filter((word) => word.length > 2 && !noise.has(word))
        .map((word) => word.replace(/(ied|ies|ing|ed|es|s|y)$/, ''))
        .filter((stem) => stem.length >= 3)
      return { type, hits: words.filter((stem) => text.includes(stem)).length }
    })
    .filter((item) => item.hits > 0)
    .sort((a, b) => b.hits - a.hits)
  return scored.length === 1 || (scored[0] && scored[0].hits > (scored[1]?.hits ?? 0))
    ? scored[0].type
    : preferOne
      ? firstRelation(view)
      : 'all'
}

/** One relationship to start with: fitment when the records have it, else the most common type. */
function firstRelation(view: GraphView) {
  const counts = new Map<string, number>()
  for (const edge of view.edges) counts.set(edge.type, (counts.get(edge.type) ?? 0) + 1)
  if (counts.size < 2) return 'all'
  const fitment = [...counts.keys()].find((type) => /fit|compat/i.test(type))
  return fitment ?? [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

export function GraphExplorer({
  view,
  onOpen,
  renderDetail,
  label = 'Relationships',
  allowExpand = true,
  focus = '',
  preferOne = false,
}: {
  view: GraphView
  onOpen?: (part: string) => void
  renderDetail?: (node: GraphNode) => ReactNode
  label?: string
  allowExpand?: boolean
  /** the question being answered: a relationship type it names (suppliers, depots…) is shown on its own at first */
  focus?: string
  /** start on a single relationship type instead of all of them (the filter still offers the rest) */
  preferOne?: boolean
}) {
  const svg = useRef<SVGSVGElement>(null)
  const expanded = useRef<HTMLDialogElement>(null)
  const marker = useId().replaceAll(':', '')
  const base = useMemo(() => graphPositions(view), [view])
  const [moves, setMoves] = useState<Record<string, Point>>({})
  const [box, setBox] = useState({ w: 1000, h: 620 })
  const [picked, setSelected] = useState(view.nodes[0]?.id ?? '')
  const [relation, setRelation] = useState(() => focusedRelation(view, focus, preferOne)),
    [search, setSearch] = useState('')
  const [group, setGroup] = useState(() => '0')
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
  const drag = useRef<{
    id: string | null
    start: Point
    origin: Point
    /** records pulled along with the dragged one, and how strongly (direct links follow most) */
    pulled: { id: string; origin: Point; weight: number }[]
  } | null>(null)
  // the drawing is 1000 units wide; in a narrow column (the chat) it shrinks, so its text is enlarged to stay legible, capped so labels do not collide
  useEffect(() => {
    const el = svg.current
    if (!el || typeof ResizeObserver === 'undefined') return
    // the drawing is measured in real pixels, so records and labels keep their size however wide the column is
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width),
        h = Math.round(entry.contentRect.height)
      if (w > 0 && h > 0)
        setBox((previous) => (previous.w === w && previous.h === h ? previous : { w, h }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // the mouse wheel zooms toward the pointer
  useEffect(() => {
    const el = svg.current
    if (!el) return
    const wheel = (event: WheelEvent) => {
      event.preventDefault()
      const ctm = el.getScreenCTM()
      if (!ctm) return
      const at = new DOMPoint(event.clientX, event.clientY).matrixTransform(ctm.inverse())
      const factor = Math.exp(-event.deltaY * 0.0015)
      setCamera((previous) => {
        const scale = Math.max(0.25, Math.min(3, previous.scale * factor)),
          ratio = scale / previous.scale
        return {
          scale,
          x: at.x - (at.x - previous.x) * ratio,
          y: at.y - (at.y - previous.y) * ratio,
        }
      })
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [])
  const positions = { ...base, ...moves }
  const byId = new Map(view.nodes.map((node) => [node.id, node]))
  // separate groups of records (e.g. one availability state each) are shown one at a time, the largest first
  const adjacency = new Map<string, Set<string>>()
  for (const edge of view.edges) {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set())
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set())
    adjacency.get(edge.source)!.add(edge.target)
    adjacency.get(edge.target)!.add(edge.source)
  }
  const groups: string[][] = []
  const grouped = new Set<string>()
  for (const node of view.nodes) {
    if (grouped.has(node.id) || !adjacency.has(node.id)) continue
    const members = [node.id]
    grouped.add(node.id)
    for (let k = 0; k < members.length; k++)
      for (const next of adjacency.get(members[k]) ?? [])
        if (!grouped.has(next)) {
          grouped.add(next)
          members.push(next)
        }
    groups.push(members)
  }
  groups.sort((a, b) => b.length - a.length)
  const groupName = (members: string[]) => {
    const hub = members.reduce((a, b) =>
      (adjacency.get(b)?.size ?? 0) > (adjacency.get(a)?.size ?? 0) ? b : a,
    )
    return `${byId.get(hub)?.label ?? 'Group'} · ${members.length} records`
  }
  const chosen = group === 'all' || !groups[Number(group)] ? null : new Set(groups[Number(group)])
  // the selected record stays inside the group on show
  const selectedId = chosen && !chosen.has(picked) ? [...chosen][0] : picked
  const selected = view.nodes.find((node) => node.id === selectedId)
  const types = [...new Set(view.edges.map((edge) => edge.type))].sort()
  const edges = view.edges.filter(
    (edge) =>
      (relation === 'all' || edge.type === relation) &&
      (!chosen || (chosen.has(edge.source) && chosen.has(edge.target))),
  )
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
      (!chosen || chosen.has(node.id)) &&
      ((relation === 'all' && !search) ||
        displayedIds.has(node.id) ||
        (search && matches.has(node.id))),
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
    // dragging a record pulls what is linked to it: neighbours follow closely, their neighbours more loosely
    const pulled: { id: string; origin: Point; weight: number }[] = []
    if (id) {
      const near = new Set<string>()
      for (const edge of displayedEdges) {
        if (edge.source === id) near.add(edge.target)
        if (edge.target === id) near.add(edge.source)
      }
      const far = new Set<string>()
      for (const edge of displayedEdges) {
        if (near.has(edge.source) && edge.target !== id && !near.has(edge.target))
          far.add(edge.target)
        if (near.has(edge.target) && edge.source !== id && !near.has(edge.source))
          far.add(edge.source)
      }
      for (const other of near)
        if (positions[other]) pulled.push({ id: other, origin: positions[other], weight: 0.55 })
      for (const other of far)
        if (positions[other]) pulled.push({ id: other, origin: positions[other], weight: 0.22 })
    }
    drag.current = {
      id,
      start: point(event),
      origin: id ? positions[id] : { x: camera.x, y: camera.y },
      pulled,
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
        ...Object.fromEntries(
          drag.current!.pulled.map((other) => [
            other.id,
            {
              x: other.origin.x + (dx / camera.scale) * other.weight,
              y: other.origin.y + (dy / camera.scale) * other.weight,
            },
          ]),
        ),
        [id]: { x: origin.x + dx / camera.scale, y: origin.y + dy / camera.scale },
      }))
    else setCamera((previous) => ({ ...previous, x: origin.x + dx, y: origin.y + dy }))
  }
  const zoom = (factor: number) =>
    setCamera((previous) => {
      const scale = Math.max(0.25, Math.min(3, previous.scale * factor)),
        ratio = scale / previous.scale
      return {
        scale,
        x: box.w / 2 - (box.w / 2 - previous.x) * ratio,
        y: box.h / 2 - (box.h / 2 - previous.y) * ratio,
      }
    })
  const fit = () => {
    if (!nodes.length) return
    const points = nodes.map((node) => positions[node.id]),
      xs = points.map((p) => p.x),
      ys = points.map((p) => p.y)
    const minX = Math.min(...xs) - 60,
      maxX = Math.max(...xs) + 60,
      minY = Math.min(...ys) - 50,
      maxY = Math.max(...ys) + 70
    const fitted = Math.min(1.4, (box.w - 30) / (maxX - minX), (box.h - 30) / (maxY - minY))
    // on a phone the whole graph would shrink to unreadable: keep labels legible and let the user pan
    const scale = box.w < 600 ? Math.max(fitted, 0.62) : fitted
    setCamera({
      scale,
      x: box.w / 2 - ((minX + maxX) / 2) * scale,
      y: box.h / 2 - ((minY + maxY) / 2) * scale,
    })
  }
  // fit once the real size is known, and again when the canvas is resized (full screen)
  const fitRef = useRef(fit)
  useEffect(() => {
    fitRef.current = fit
  })
  useEffect(() => {
    if (box.w && box.h && group) fitRef.current()
    // oxlint-disable-next-line react/exhaustive-effect-dependencies -- refit only when the measured size changes
  }, [box.w, box.h, group])
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
        {groups.length > 1 ? (
          <label>
            <span className="sr-only">Group of records</span>
            <select
              aria-label="Group of records"
              value={chosen ? group : 'all'}
              onChange={(e) => setGroup(e.target.value)}
            >
              {groups.map((members, index) => (
                <option key={members[0]} value={String(index)}>
                  {groupName(members)}
                </option>
              ))}
              <option value="all">Show all groups</option>
            </select>
          </label>
        ) : null}
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
      <div className="gx-legend" aria-label="Record types and relationships">
        {[...new Set(nodes.map((node) => node.kind))].map((kindName) => {
          const look = LOOKS[kindName] ?? fallback
          return (
            <span key={kindName}>
              <i style={{ background: look.fill, borderColor: look.ink }} />
              {humanize(kindName)} · {nodes.filter((node) => node.kind === kindName).length}
            </span>
          )
        })}
        <span className="gx-legend__links">
          Lines: {[...new Set(displayedEdges.map((edge) => humanize(edge.type)))].join(', ')}
        </span>
      </div>
      <div className="gx-workspace">
        <div className="gx-canvas">
          <svg
            ref={svg}
            viewBox={`0 0 ${box.w} ${box.h}`}
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
            <rect width={box.w} height={box.h} fill={`url(#${marker}-dots)`} />
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
