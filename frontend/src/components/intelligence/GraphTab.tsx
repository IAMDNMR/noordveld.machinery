import { useMemo, useState } from 'react'
import { getPartGraph, type GraphNode, type GraphView } from '../../api'
import { useApi } from '../../hooks/useApi'
import { humanize } from '../../lib/format'
import { ProvenanceBadge } from './provenance'
import { TabFrame } from './tabs/shared'

const ORDER = ['MACHINE', 'ASSEMBLY', 'SUPPLIER', 'DEALER', 'WAREHOUSE', 'COMPLIANCE', 'PART', 'CATEGORY']
const KIND_LABEL: Record<string, string> = {
  MACHINE: 'Machines', ASSEMBLY: 'Assemblies', SUPPLIER: 'Suppliers', DEALER: 'Dealers', WAREHOUSE: 'Warehouses', COMPLIANCE: 'Compliance', PART: 'Related parts', CATEGORY: 'Category',
}
const SIZE = 460
const C = SIZE / 2
const RING = 168

interface Placed {
  node: GraphNode
  x: number
  y: number
}

/** Radial layout: the part in the middle, each kind of neighbour in its own sector. Pure geometry; no data is added. */
function layout(view: GraphView): { placed: Placed[]; sectors: { kind: string; x: number; y: number; n: number }[] } {
  const neighbours = view.nodes.slice(1)
  const kinds = ORDER.filter((k) => neighbours.some((n) => n.kind === k))
  const weights = kinds.map((k) => Math.max(neighbours.filter((n) => n.kind === k).length, 3))
  const unit = (Math.PI * 2) / weights.reduce((a, b) => a + b, 0)
  const placed: Placed[] = []
  const sectors: { kind: string; x: number; y: number; n: number }[] = []
  let angle = -Math.PI / 2
  kinds.forEach((kind, ki) => {
    const group = neighbours.filter((n) => n.kind === kind)
    const span = weights[ki] * unit
    group.forEach((node, i) => {
      const a = angle + (span * (i + 0.5)) / group.length
      placed.push({ node, x: C + RING * Math.cos(a), y: C + RING * Math.sin(a) })
    })
    const mid = angle + span / 2
    sectors.push({ kind, x: C + (RING + 38) * Math.cos(mid), y: C + (RING + 38) * Math.sin(mid), n: group.length })
    angle += span
  })
  return { placed, sectors }
}

export function GraphTab({ partKey, onOpen }: { partKey: string; onOpen: (partNumber: string) => void }) {
  const state = useApi((s) => getPartGraph(partKey, s), `graph:${partKey}`)
  return (
    <TabFrame state={state} label="Graph">
      {(view) => <Graph key={partKey} view={view} onOpen={onOpen} />}
    </TabFrame>
  )
}

function Graph({ view, onOpen }: { view: GraphView; onOpen: (pn: string) => void }) {
  const root = view.nodes[0]
  const { placed, sectors } = useMemo(() => layout(view), [view])
  const [selectedId, setSelectedId] = useState<string>(root.id)
  const byId = new Map(view.nodes.map((n) => [n.id, n]))
  const selected = byId.get(selectedId) ?? root
  const edgesTo = (id: string) => view.edges.filter((e) => e.target === id)
  const selectedEdges = edgesTo(selectedId)
  const grouped = ORDER.filter((k) => view.nodes.some((n) => n.kind === k && n.id !== root.id))

  return (
    <div className="pg">
      <p className="pw-lead">Everything directly connected to this part. Dashed lines are demonstration data; solid lines come from the source catalogue. Select an item to inspect it.</p>
      <div className="pg__layout">
        <svg className="pg__svg" viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label={`Graph of ${root.label}`}>
          {placed.map(({ node, x, y }) => {
            const demo = edgesTo(node.id).every((ed) => ed.data_class === 'SYNTHETIC_DEMO')
            return <line key={`l-${node.id}`} x1={C} y1={C} x2={x} y2={y} className={`pg__edge ${demo ? 'is-demo' : ''}`} />
          })}
          {sectors.map((s) => (
            <text key={s.kind} x={s.x} y={s.y} className="pg__sector" textAnchor="middle" dominantBaseline="middle">
              {KIND_LABEL[s.kind]} {s.n}
            </text>
          ))}
          {placed.map(({ node, x, y }) => (
            <g key={node.id} className={`pg__node pg__node--${node.kind.toLowerCase()} ${selectedId === node.id ? 'is-selected' : ''}`} transform={`translate(${x} ${y})`} role="button" tabIndex={0}
               aria-label={`${KIND_LABEL[node.kind]}: ${node.label}`} aria-pressed={selectedId === node.id} onClick={() => setSelectedId(node.id)}
               onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), setSelectedId(node.id))}>
              <circle r={selectedId === node.id ? 10 : 7} />
              {selectedId === node.id ? <title>{node.label}</title> : null}
            </g>
          ))}
          <g className={`pg__node pg__node--root ${selectedId === root.id ? 'is-selected' : ''}`} transform={`translate(${C} ${C})`} role="button" tabIndex={0} aria-label={`Selected part ${root.label}`}
             aria-pressed={selectedId === root.id} onClick={() => setSelectedId(root.id)} onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), setSelectedId(root.id))}>
            <circle r={26} />
            <text textAnchor="middle" dominantBaseline="middle" className="pg__root-label">Part</text>
          </g>
        </svg>

        <aside className="pg__inspect" aria-live="polite">
          <p className="pg__kind">{KIND_LABEL[selected.kind] ?? humanize(selected.kind)}</p>
          <h3 className={selected.kind === 'PART' || selected.kind === 'MACHINE' ? 'mono' : undefined}>{selected.label}</h3>
          {selectedEdges.length > 0 ? (
            selectedEdges.map((edge) => (
              <dl className="pw-facts" key={edge.type}>
                <div><dt>Relationship</dt><dd className="mono">{edge.type}</dd></div>
                <div><dt>From</dt><dd className="mono">{root.label}</dd></div>
                <div><dt>Data</dt><dd><ProvenanceBadge value={edge.data_class} /></dd></div>
              </dl>
            ))
          ) : (
            <p className="pw-lead">The part you are investigating.</p>
          )}
          {selected.part_number && selected.id !== root.id ? (
            <button type="button" className="button button--secondary" onClick={() => onOpen(selected.part_number!)}>
              Investigate {selected.part_number}
            </button>
          ) : null}
        </aside>
      </div>

      {view.truncated ? <p className="pw-note-inline">Showing the first connections of each kind. The full counts are on the Insights tab.</p> : null}

      <div className="pg__list">
        <h3 className="pw-sub">Connections</h3>
        {grouped.map((kind) => (
          <section key={kind} aria-label={KIND_LABEL[kind]}>
            <h4>{KIND_LABEL[kind]}</h4>
            <ul className="pw-simple">
              {view.nodes
                .filter((n) => n.kind === kind && n.id !== root.id)
                .map((n) => (
                  <li key={n.id}>
                    <button type="button" className="rcard__open" onClick={() => setSelectedId(n.id)}>
                      {n.label}
                    </button>
                    {edgesTo(n.id).map((e) => (
                      <span key={e.type} className="pg__rel">
                        <span className="mono">{e.type}</span> <ProvenanceBadge value={e.data_class} />
                      </span>
                    ))}
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
