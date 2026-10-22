import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { BusinessEntity } from '../../../api/applicationDefinition'

export const BOX_W = 248
const HEAD = 46
const ROW = 25
const SHOWN = 5
const GAP_X = 112
const GAP_Y = 112
const SHORT = {
  one_to_one: '1 : 1',
  one_to_many: '1 : N',
  many_to_one: 'N : 1',
  many_to_many: 'N : N',
} as const

export type ErBox = { id: string; x: number; y: number; w: number; h: number }
export type ErEdge = {
  id: string
  from: string
  to: string
  label: string
  name: string
  required: boolean
}

const heightOf = (entity: BusinessEntity) =>
  HEAD +
  ROW * Math.min(entity.attributes.length, SHOWN) +
  (entity.attributes.length > SHOWN ? ROW : 0) +
  12

/** Deterministic layout: entities in breadth-first order from the most connected one, so related entities sit near each other, wrapped into rows. */
export function layoutEntities(
  entities: BusinessEntity[],
  maxColumns = 5,
): { boxes: Map<string, ErBox>; edges: ErEdge[]; width: number; height: number } {
  const ids = new Set(entities.map((entity) => entity.id))
  const edges: ErEdge[] = entities.flatMap((entity) =>
    entity.relationships
      .filter((rel) => ids.has(rel.target))
      .map((rel) => ({
        id: `${entity.id}:${rel.id}`,
        from: entity.id,
        to: rel.target,
        label: SHORT[rel.cardinality],
        name: rel.name,
        required: !!rel.required,
      })),
  )
  const degree = new Map<string, number>(entities.map((entity) => [entity.id, 0]))
  const neighbours = new Map<string, string[]>(entities.map((entity) => [entity.id, []]))
  for (const edge of edges) {
    degree.set(edge.from, degree.get(edge.from)! + 1)
    degree.set(edge.to, degree.get(edge.to)! + 1)
    neighbours.get(edge.from)!.push(edge.to)
    neighbours.get(edge.to)!.push(edge.from)
  }
  const order: string[] = []
  const seen = new Set<string>()
  const byDegree = [...entities].sort(
    (a, b) => degree.get(b.id)! - degree.get(a.id)! || a.name.localeCompare(b.name),
  )
  for (const seed of byDegree) {
    if (seen.has(seed.id)) continue
    const queue = [seed.id]
    seen.add(seed.id)
    while (queue.length) {
      const current = queue.shift()!
      order.push(current)
      for (const next of [...new Set(neighbours.get(current)!)].sort(
        (a, b) => degree.get(b)! - degree.get(a)!,
      ))
        if (!seen.has(next)) {
          seen.add(next)
          queue.push(next)
        }
    }
  }
  const columns = Math.max(1, Math.min(maxColumns, Math.ceil(Math.sqrt(entities.length * 1.3))))
  const byId = new Map(entities.map((entity) => [entity.id, entity]))
  const boxes = new Map<string, ErBox>()
  let y = 76,
    rowHeight = 0,
    width = 0
  order.forEach((id, index) => {
    const column = index % columns
    if (column === 0 && index > 0) {
      y += rowHeight + GAP_Y
      rowHeight = 0
    }
    const h = heightOf(byId.get(id)!)
    rowHeight = Math.max(rowHeight, h)
    const x = 40 + column * (BOX_W + GAP_X)
    boxes.set(id, { id, x, y, w: BOX_W, h })
    width = Math.max(width, x + BOX_W + 96)
  })
  return { boxes, edges, width: Math.max(width, 240), height: y + rowHeight + 24 }
}

/** Route in row/column gutters so connections never run through unrelated entity cards. */
export function routeRelationship(a: ErBox, b: ErBox, boxes: Map<string, ErBox>, lane = 0) {
  const offset = lane % 6
  let points: { x: number; y: number }[], label: { x: number; y: number }
  if (a.id === b.id) {
    const x = a.x + a.w + 30 + offset * 9
    points = [
      { x: a.x + a.w, y: a.y + 18 },
      { x, y: a.y + 18 },
      { x, y: a.y + a.h - 18 },
      { x: a.x + a.w, y: a.y + a.h - 18 },
    ]
    label = { x, y: a.y + a.h / 2 }
  } else if (a.y === b.y) {
    const y = a.y - 24 - offset * 8
    points = [
      { x: a.x + a.w / 2, y: a.y },
      { x: a.x + a.w / 2, y },
      { x: b.x + b.w / 2, y },
      { x: b.x + b.w / 2, y: b.y },
    ]
    label = { x: (a.x + b.x + a.w) / 2, y }
  } else if (a.x === b.x) {
    const x = a.x + a.w + 28 + offset * 10
    points = [
      { x: a.x + a.w, y: a.y + a.h / 2 },
      { x, y: a.y + a.h / 2 },
      { x, y: b.y + b.h / 2 },
      { x: b.x + b.w, y: b.y + b.h / 2 },
    ]
    label = { x, y: (points[0].y + points[3].y) / 2 }
  } else {
    const rowBottom = Math.max(
      ...[...boxes.values()].filter((box) => box.y === a.y).map((box) => box.y + box.h),
    )
    const y = rowBottom + 24 + offset * 9
    const rightward = b.x > a.x
    const x = rightward ? b.x - 28 - offset * 9 : b.x + b.w + 28 + offset * 9
    const end = { x: rightward ? b.x : b.x + b.w, y: b.y + b.h / 2 }
    points = [
      { x: a.x + a.w / 2, y: a.y + a.h },
      { x: a.x + a.w / 2, y },
      { x, y },
      { x, y: end.y },
      end,
    ]
    label = { x: (points[1].x + x) / 2, y }
  }
  return { points, label, path: points.map((p, i) => `${i ? 'L' : 'M'} ${p.x} ${p.y}`).join(' ') }
}

type Props = {
  entities: BusinessEntity[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  zoom: number
  showAll?: boolean
  recent: ReadonlySet<string>
  onScale?: (scale: number) => void
}

export function ErDiagram({
  entities,
  selectedId,
  onSelect,
  zoom,
  recent,
  showAll = true,
  onScale,
}: Props) {
  const holder = useRef<HTMLDivElement | null>(null)
  const [available, setAvailable] = useState(900)
  useEffect(() => {
    const node = holder.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) =>
      setAvailable(entries[0].contentRect.width || 900),
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  // Zoom scales a stable layout; it must not move entities into different rows.
  const columns = available >= 1400 ? 4 : available >= 940 ? 3 : available >= 540 ? 2 : 1
  const { boxes, edges, width, height } = useMemo(
    () => layoutEntities(entities, columns),
    [entities, columns],
  )
  const scale = zoom || Math.min(1, Math.max(0.35, (available - 12) / width))
  const markerId = useId().replace(/:/g, '')
  useEffect(() => {
    onScale?.(scale)
  }, [scale, onScale])
  useEffect(() => {
    const box = selectedId ? boxes.get(selectedId) : null
    const viewport = holder.current?.parentElement
    if (box && viewport)
      viewport.scrollTo?.({
        left: Math.max(0, (box.x + box.w / 2) * scale - viewport.clientWidth / 2),
        top: Math.max(0, (box.y + box.h / 2) * scale - viewport.clientHeight / 2),
        behavior: 'smooth',
      })
  }, [selectedId, boxes, scale])
  const related = new Set<string>()
  if (selectedId)
    edges.forEach((edge) => {
      if (edge.from === selectedId) related.add(edge.to)
      if (edge.to === selectedId) related.add(edge.from)
    })
  return (
    <div className="sw-er" ref={holder} role="group" aria-label="Entity relationship diagram">
      <svg
        width={width * scale}
        height={height * scale}
        viewBox={`0 0 ${width} ${height}`}
        role="group"
        aria-label={`${entities.length} data entities and ${edges.length} relationships`}
      >
        <defs>
          {['one', 'many'].map((kind) => (
            <marker
              key={kind}
              id={`${markerId}-${kind}`}
              viewBox="0 0 12 12"
              refX="11"
              refY="6"
              markerWidth="10"
              markerHeight="10"
              orient="auto-start-reverse"
              markerUnits="userSpaceOnUse"
            >
              <path
                d={kind === 'many' ? 'M1 6 L11 1 M1 6 L11 6 M1 6 L11 11' : 'M7 1 L7 11'}
                fill="none"
                stroke="#478475"
                strokeWidth="1.7"
              />
            </marker>
          ))}
        </defs>
        {edges
          .filter(
            (edge) => showAll || !selectedId || edge.from === selectedId || edge.to === selectedId,
          )
          .map((edge, index) => {
            const a = boxes.get(edge.from),
              b = boxes.get(edge.to)
            if (!a || !b) return null
            const route = routeRelationship(a, b, boxes, index)
            const active =
              selectedId !== null && (edge.from === selectedId || edge.to === selectedId)
            return (
              <g
                key={edge.id}
                aria-hidden="true"
                className={`sw-er__edge${active ? ' is-active' : selectedId ? ' is-dim' : ''}`}
              >
                <path
                  d={route.path}
                  fill="none"
                  markerStart={`url(#${markerId}-${edge.label.startsWith('N') ? 'many' : 'one'})`}
                  markerEnd={`url(#${markerId}-${edge.label.endsWith('N') ? 'many' : 'one'})`}
                  strokeDasharray={edge.required ? undefined : '6 4'}
                >
                  <title>{`${edge.name} (${edge.label})${edge.required ? ' · required' : ' · optional'}`}</title>
                </path>
                <rect
                  className="sw-er__edge-badge"
                  x={route.label.x - 23}
                  y={route.label.y - 10}
                  width={46}
                  height={20}
                  rx={7}
                />
                <text x={route.label.x} y={route.label.y + 4} textAnchor="middle">
                  {edge.label}
                </text>
              </g>
            )
          })}
        {entities.map((entity) => {
          const box = boxes.get(entity.id)!
          const selected = entity.id === selectedId
          const key = entity.attributes.filter((attribute) => attribute.key)
          return (
            <g
              key={entity.id}
              transform={`translate(${box.x},${box.y})`}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${entity.name}, ${entity.attributes.length} attributes`}
              className={`sw-er__box${selected ? ' is-selected' : related.has(entity.id) ? ' is-related' : selectedId ? ' is-dim' : ''}${recent.has(entity.id) ? ' is-changed' : ''}`}
              onClick={() => onSelect(selected ? null : entity.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect(selected ? null : entity.id)
                }
              }}
            >
              <rect width={box.w} height={box.h} rx={9} />
              <title>{entity.name}</title>
              <rect className="sw-er__header" width={box.w} height={HEAD - 2} rx={9} />
              <text x={14} y={27} className="sw-er__name">
                {entity.name.length > 28 ? `${entity.name.slice(0, 27)}…` : entity.name}
              </text>
              <line x1={0} x2={box.w} y1={HEAD - 2} y2={HEAD - 2} />
              {entity.attributes.slice(0, SHOWN).map((attribute, index) => (
                <g key={attribute.id}>
                  <text
                    x={14}
                    y={HEAD + 18 + index * ROW}
                    className={`sw-er__attr${attribute.key ? ' is-key' : ''}`}
                  >
                    {key.includes(attribute) ? '◆ ' : attribute.required ? '● ' : '○ '}
                    {attribute.name.length > 22
                      ? `${attribute.name.slice(0, 21)}…`
                      : attribute.name}
                  </text>
                  <text
                    x={box.w - 12}
                    y={HEAD + 18 + index * ROW}
                    textAnchor="end"
                    className="sw-er__type"
                  >
                    {attribute.type === 'integer'
                      ? 'int'
                      : attribute.type === 'string'
                        ? 'text'
                        : attribute.type}
                  </text>
                </g>
              ))}
              {entity.attributes.length > SHOWN ? (
                <text x={14} y={HEAD + 18 + SHOWN * ROW} className="sw-er__more">
                  View {entity.attributes.length - SHOWN} more fields →
                </text>
              ) : null}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
