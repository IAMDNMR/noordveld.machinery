import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import type { BusinessDefinition, WorkflowDefinition } from '../../../api/applicationDefinition'
import { layoutProcess, layoutProcessVertical, NODE_H, NODE_W, stepIssues } from './processLayout'
import './ProcessDiagram.css'

type Props = {
  workflow: WorkflowDefinition
  business: BusinessDefinition
  selectedId: string | null
  onSelect: (id: string) => void
  onConnect: (source: string, target: string) => void
  /** Hides editing tools: the diagram only shows and selects. */
  readOnly?: boolean
  /** Fit the width and let the canvas grow up to this height (pan for the rest), instead of shrinking everything into 440px. */
  maxHeight?: number
}

const short = (text: string, length: number) =>
  text.length > length ? `${text.slice(0, length - 1)}…` : text
const titleLines = (text: string): string[] => {
  if (text.length <= 29) return [text]
  const split = text.lastIndexOf(' ', 29)
  const at = split > 10 ? split : 29
  return [text.slice(0, at), short(text.slice(at).trim(), 29)]
}
const KIND_LABEL: Record<string, string> = {
  start: 'Start',
  end: 'End',
  branch: 'Decision',
  exception: 'Exception',
  approval: 'Approval',
  form: 'Form',
  search: 'Search',
  review: 'Review',
  action: 'Action',
}

/** Selectable diagram of the Studio process model. */
export function ProcessDiagram({
  workflow,
  business,
  selectedId,
  onSelect,
  onConnect,
  readOnly = false,
  maxHeight,
}: Props) {
  // A height limit selects the top-down layout; otherwise use the compact layout.
  const vertical = maxHeight !== undefined
  const { nodes, width, height, laneX } = useMemo(
    () => (vertical ? layoutProcessVertical(workflow) : { ...layoutProcess(workflow), laneX: 0 }),
    [workflow, vertical],
  )
  const loops = useMemo(
    () =>
      new Map(
        workflow.transitions
          .filter((edge) => {
            const a = nodes.get(edge.source),
              b = nodes.get(edge.target)
            return a && b && b.rank <= a.rank
          })
          .map((edge, index) => [edge.id, index]),
      ),
    [workflow, nodes],
  )
  const issues = useMemo(() => stepIssues(workflow, business.rules), [workflow, business.rules])
  const roles = new Map(business.roles.map((role) => [role.id, role.name]))
  const undecided = new Set(
    business.decisions
      .filter((item) => item.status !== 'decided')
      .flatMap((item) => item.affects ?? []),
  )
  const flagged = (stateId: string, rules: string[] = []) =>
    undecided.has(stateId) || rules.some((rule) => undecided.has(rule))
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 })
  const [connectFrom, setConnectFrom] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)
  const frame = useRef<HTMLDivElement>(null)
  const [frameWidth, setFrameWidth] = useState(800)
  useEffect(() => {
    if (!frame.current || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) =>
      setFrameWidth(entries[0].contentRect.width || 800),
    )
    observer.observe(frame.current)
    return () => observer.disconnect()
  }, [])
  const base = maxHeight
    ? Math.min(1.15, frameWidth / width)
    : Math.min(1.2, frameWidth / width, 440 / height)
  const canvasHeight = maxHeight
    ? Math.round(Math.min(maxHeight, Math.max(320, height * base)))
    : 440
  const scale = base * view.scale
  const centerX = vertical ? Math.max(0, (frameWidth / scale - width) / 2) : 0

  // In the tall top-down view the wheel scrolls the canvas, and gives scrolling back to the page at either end.
  const wheel = useRef({ scale, canvasHeight, height, y: view.y })
  useEffect(() => {
    wheel.current = { scale, canvasHeight, height, y: view.y }
  })
  useEffect(() => {
    const node = frame.current
    if (!vertical || !node) return
    const onWheel = (event: WheelEvent) => {
      const { scale: s, canvasHeight: h, height: total, y } = wheel.current
      const next = Math.max(Math.min(0, -(total - h / s) - 24), Math.min(0, y - event.deltaY / s))
      if (next === y) return // at an end: the page scrolls instead
      event.preventDefault()
      wheel.current.y = next
      setView((current) => ({ ...current, y: next }))
    }
    node.addEventListener('wheel', onWheel, { passive: false })
    return () => node.removeEventListener('wheel', onWheel)
  }, [vertical])
  const zoom = (factor: number) =>
    setView((current) => ({
      ...current,
      scale: Math.min(2.5, Math.max(0.25, current.scale * factor)),
    }))
  // Fit to screen shows the whole process; the default view fits the width so labels stay readable.
  const fit = () => {
    const k = Math.min(1, canvasHeight / (height * base))
    setView({
      scale: k,
      x: 0,
      y: 0,
    })
  }
  const choose = (id: string) => {
    if (connectFrom && connectFrom !== id) {
      onConnect(connectFrom, id)
      setConnectFrom(null)
    }
    onSelect(id)
  }
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = 40 / scale
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [step, 0],
      ArrowRight: [-step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    }
    if (event.target !== event.currentTarget) return
    if (moves[event.key]) {
      event.preventDefault()
      setView((current) => ({
        ...current,
        x: current.x + moves[event.key][0],
        y: current.y + moves[event.key][1],
      }))
    }
    if (event.key === '+' || event.key === '=') zoom(1.2)
    if (event.key === '-') zoom(1 / 1.2)
    if (event.key === 'Escape') setConnectFrom(null)
  }
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest('[data-node]')) return
    drag.current = { x: event.clientX, y: event.clientY, vx: view.x, vy: view.y }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    const start = drag.current
    setView((current) => ({
      ...current,
      x: start.vx + (event.clientX - start.x) / scale,
      y: start.vy + (event.clientY - start.y) / scale,
    }))
  }
  const selected = workflow.states.find((state) => state.id === selectedId)

  return (
    <section className="biz-diagram" aria-label="Process diagram">
      <div className="biz-diagram__tools" role="toolbar" aria-label="Diagram tools">
        <button type="button" onClick={() => zoom(1.2)} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoom(1 / 1.2)} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={fit}>
          Fit to screen
        </button>
        <button type="button" onClick={() => setView({ scale: 1, x: 0, y: 0 })}>
          Reset view
        </button>
        {readOnly ? null : (
          <button
            type="button"
            disabled={!selected || selected.kind === 'end'}
            aria-pressed={connectFrom !== null}
            onClick={() => setConnectFrom(connectFrom ? null : selectedId)}
          >
            {connectFrom ? 'Cancel connecting' : 'Connect from selected step'}
          </button>
        )}
        <span className="biz-diagram__hint" role="status">
          {connectFrom
            ? `Choose the step that follows “${workflow.states.find((state) => state.id === connectFrom)?.label}”. Esc cancels.`
            : 'Drag the background or use the arrow keys to pan; + and − zoom.'}
        </span>
      </div>
      {/* The canvas is a focusable pan surface (arrow keys, +/-); every step inside it is its own button. */}
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
      <div
        className="biz-diagram__frame"
        ref={frame}
        role="application"
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        onKeyDown={onKey}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => {
          drag.current = null
        }}
        aria-label="Process diagram canvas. Use arrow keys to pan."
      >
        <svg
          width="100%"
          height={canvasHeight}
          viewBox={`${-view.x - centerX} ${-view.y} ${frameWidth / scale} ${canvasHeight / scale}`}
          role="img"
          aria-label={`Diagram of ${workflow.name}`}
        >
          <defs>
            <marker
              id="biz-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" className="biz-diagram__arrowhead" />
            </marker>
          </defs>
          {workflow.transitions.map((edge) => {
            const from = nodes.get(edge.source),
              to = nodes.get(edge.target)
            if (!from || !to) return null
            if (vertical) {
              const loop = loops.get(edge.id)
              const label =
                edge.condition.kind === 'always'
                  ? ''
                  : `${edge.condition.kind === 'not_equals' ? '≠ ' : ''}${String(edge.condition.value)}`
              const active = edge.source === selectedId || edge.target === selectedId
              let path: string, lx: number, ly: number
              if (loop !== undefined) {
                const lane = laneX + loop * 12,
                  y1 = from.y + NODE_H / 2,
                  y2 = to.y + NODE_H / 2 + 6
                path = `M${from.x + NODE_W},${y1} H${lane} V${y2} H${to.x + NODE_W + 2}`
                lx = from.x + NODE_W + 8
                ly = y1 - 6
              } else {
                const sx = from.x + NODE_W / 2,
                  sy = from.y + NODE_H,
                  tx = to.x + NODE_W / 2,
                  ty = to.y
                const detour =
                  to.rank - from.rank > 1 && Math.abs(sx - tx) < NODE_W ? -(NODE_W * 0.75) : 0 // a long edge bends around the steps it skips
                path = `M${sx},${sy} C${sx + detour},${sy + 34} ${tx + detour},${ty - 34} ${tx},${ty}`
                lx = sx + (tx - sx) * 0.45 + detour * 0.6
                ly = sy + Math.min(28, (ty - sy) * 0.45)
              }
              return (
                <g
                  key={edge.id}
                  className={`biz-diagram__edge${active ? ' biz-diagram__edge--active' : ''}${loop !== undefined ? ' biz-diagram__edge--back' : ''}`}
                >
                  <path d={path} markerEnd="url(#biz-arrow)">
                    <title>{`${edge.source} → ${edge.target}${label ? ` when ${edge.condition.field} ${label}` : ''}`}</title>
                  </path>
                  {label && (
                    <text x={lx} y={ly} textAnchor={loop !== undefined ? 'start' : 'middle'}>
                      {short(label.replaceAll('_', ' ').toLowerCase(), 22)}
                    </text>
                  )}
                </g>
              )
            }
            const back = to.rank <= from.rank
            const direction = to.x >= from.x ? 1 : -1
            const x1 = from.x + (direction > 0 ? NODE_W : 0),
              y1 = from.y + NODE_H / 2,
              x2 = to.x + (direction > 0 ? 0 : NODE_W),
              y2 = to.y + NODE_H / 2
            const loop = Math.max(from.y, to.y) + NODE_H + 18
            const acrossBand = Math.floor(from.rank / 4) !== Math.floor(to.rank / 4)
            const path =
              !back && acrossBand
                ? `M${from.x + NODE_W / 2},${from.y + NODE_H} C${from.x + NODE_W / 2},${from.y + NODE_H + 45} ${to.x + NODE_W / 2},${to.y - 45} ${to.x + NODE_W / 2},${to.y}`
                : back
                  ? `M${from.x + NODE_W / 2},${from.y + NODE_H} C${from.x + NODE_W / 2},${loop} ${to.x + NODE_W / 2},${loop} ${to.x + NODE_W / 2},${to.y + NODE_H}`
                  : `M${x1},${y1} C${x1 + 40 * direction},${y1} ${x2 - 40 * direction},${y2} ${x2},${y2}`
            const label =
              edge.condition.kind === 'always'
                ? ''
                : `${edge.condition.kind === 'not_equals' ? '≠ ' : ''}${String(edge.condition.value)}`
            const lx = back ? (from.x + to.x + NODE_W) / 2 : (x1 + x2) / 2,
              ly = back ? loop - 4 : (y1 + y2) / 2 - 6
            const active = edge.source === selectedId || edge.target === selectedId
            return (
              <g
                key={edge.id}
                className={`biz-diagram__edge${active ? ' biz-diagram__edge--active' : ''}${back ? ' biz-diagram__edge--back' : ''}`}
              >
                <path d={path} markerEnd="url(#biz-arrow)">
                  <title>{`${edge.source} → ${edge.target}${label ? ` when ${edge.condition.field} ${label}` : ''}`}</title>
                </path>
                {label && (
                  <text x={lx} y={ly} textAnchor="middle">
                    {short(label, 22)}
                  </text>
                )}
              </g>
            )
          })}
          {workflow.states.map((state) => {
            const box = nodes.get(state.id)!
            const problems = issues.get(state.id) ?? []
            const kind = state.kind === 'end' ? `end-${state.outcome ?? 'unknown'}` : state.kind
            const role = state.role_id
              ? (roles.get(state.role_id) ?? state.role_id)
              : state.kind === 'start' || state.kind === 'end'
                ? ''
                : 'No role'
            const data = [
              (state.reads_entity_ids ?? []).length
                ? `Reads ${(state.reads_entity_ids ?? []).length}`
                : '',
              (state.writes_entity_ids ?? []).length
                ? `Changes ${(state.writes_entity_ids ?? []).length}`
                : '',
            ]
              .filter(Boolean)
              .join(' · ')
            const description = `${KIND_LABEL[state.kind]} step ${state.label}${role ? `, ${role}` : ''}${problems.length ? `. Problems: ${problems.join(' ')}` : ''}${flagged(state.id, state.rule_ids) ? '. Depends on an unresolved business decision.' : ''}`
            return (
              <g
                key={state.id}
                data-node={state.id}
                className={`biz-node biz-node--${kind}${state.id === selectedId ? ' biz-node--selected' : ''}${problems.length ? ' biz-node--problem' : ''}`}
                transform={`translate(${box.x},${box.y})`}
                role="button"
                // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                tabIndex={0}
                aria-label={description}
                aria-pressed={state.id === selectedId}
                onClick={() => choose(state.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    choose(state.id)
                  }
                }}
              >
                <title>{description}</title>
                {state.kind === 'branch' ? (
                  <polygon
                    points={`${NODE_W / 2},0 ${NODE_W},${NODE_H / 2} ${NODE_W / 2},${NODE_H} 0,${NODE_H / 2}`}
                  />
                ) : (
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx={state.kind === 'start' || state.kind === 'end' ? NODE_H / 2 : 10}
                  />
                )}
                <text
                  x={NODE_W / 2}
                  y={state.kind === 'branch' ? NODE_H / 2 - 2 : 25}
                  textAnchor="middle"
                  className="biz-node__label"
                >
                  {state.kind === 'branch'
                    ? short(state.label, 26)
                    : titleLines(state.label).map((line, index) => (
                        <tspan key={index} x={NODE_W / 2} dy={index ? 17 : 0}>
                          {line}
                        </tspan>
                      ))}
                </text>
                <text
                  x={NODE_W / 2}
                  y={state.kind === 'branch' ? NODE_H / 2 + 14 : 61}
                  textAnchor="middle"
                  className="biz-node__meta"
                >
                  {short([KIND_LABEL[state.kind], role].filter(Boolean).join(' · '), 30)}
                </text>
                {data && state.kind !== 'branch' && (
                  <text x={NODE_W / 2} y={77} textAnchor="middle" className="biz-node__meta">
                    {data}
                  </text>
                )}
                {problems.length > 0 && (
                  <g className="biz-node__badge biz-node__badge--problem">
                    <circle cx={NODE_W - 4} cy={4} r={9} />
                    <text x={NODE_W - 4} y={8} textAnchor="middle">
                      !
                    </text>
                  </g>
                )}
                {flagged(state.id, state.rule_ids) && (
                  <g className="biz-node__badge biz-node__badge--decision">
                    <circle cx={4} cy={4} r={9} />
                    <text x={4} y={8} textAnchor="middle">
                      ?
                    </text>
                  </g>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      <p className="biz-diagram__legend">
        <span>! a structural problem</span>
        <span>? depends on an unresolved business decision</span>
        <span>Read and change counts refer to data entities</span>
        <span>dashed lines loop back</span>
      </p>
    </section>
  )
}
