import type { Evidence, GraphView } from '../../api/intelligenceTypes'

/** Evidence is the only source of answer relationships. No keyword matching or inferred edges. */
export function evidenceGraph(evidence: Evidence[]): GraphView {
  const nodes = new Map<string, GraphView['nodes'][number]>()
  const edges = new Map<string, GraphView['edges'][number]>()
  for (const row of evidence) {
    const source = `${row.entity_kind}:${row.entity}`,
      target = `${row.target_kind}:${row.target}`
    nodes.set(source, {
      id: source,
      label: row.entity,
      kind: row.entity_kind,
      part_number: row.entity_kind === 'PART' ? row.entity : null,
    })
    nodes.set(target, {
      id: target,
      label: row.target,
      kind: row.target_kind,
      part_number: row.target_kind === 'PART' ? row.target : null,
    })
    edges.set(`${source}|${row.relationship}|${target}|${row.data_class}`, {
      source,
      target,
      type: row.relationship,
      data_class: row.data_class,
    })
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()], truncated: false }
}

export type Point = { x: number; y: number }
/** Deterministic spring layout over the returned graph, including disconnected evidence groups. */
export function graphPositions(view: GraphView): Record<string, Point> {
  const nodes = view.nodes.map((node, i) => ({
    id: node.id,
    x: 500 + 240 * Math.cos(i * 2.39996),
    y: 310 + 210 * Math.sin(i * 2.39996),
  }))
  const byId = new Map(nodes.map((node) => [node.id, node]))
  for (let pass = 0; pass < 160; pass++) {
    const forces = new Map(
      nodes.map((node) => [node.id, { x: (500 - node.x) * 0.008, y: (300 - node.y) * 0.008 }]),
    )
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i],
          b = nodes[j],
          dx = a.x - b.x,
          dy = a.y - b.y,
          distance = Math.max(1, Math.hypot(dx, dy))
        const power = Math.min(18, 13000 / (distance * distance))
        const x = (dx / distance) * power,
          y = (dy / distance) * power
        forces.get(a.id)!.x += x
        forces.get(a.id)!.y += y
        forces.get(b.id)!.x -= x
        forces.get(b.id)!.y -= y
      }
    for (const edge of view.edges) {
      const a = byId.get(edge.source),
        b = byId.get(edge.target)
      if (!a || !b || a === b) continue
      const dx = b.x - a.x,
        dy = b.y - a.y,
        distance = Math.max(1, Math.hypot(dx, dy)),
        power = (distance - 175) * 0.012
      const x = (dx / distance) * power,
        y = (dy / distance) * power
      forces.get(a.id)!.x += x
      forces.get(a.id)!.y += y
      forces.get(b.id)!.x -= x
      forces.get(b.id)!.y -= y
    }
    for (const node of nodes) {
      const f = forces.get(node.id)!,
        cooling = 1 - pass / 210
      node.x += Math.max(-12, Math.min(12, f.x)) * cooling
      node.y += Math.max(-12, Math.min(12, f.y)) * cooling
    }
  }
  return Object.fromEntries(nodes.map((node) => [node.id, { x: node.x, y: node.y }]))
}
