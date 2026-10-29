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
  // Same arithmetic as before, on index-addressed arrays: the pairwise loop runs ~n²/2 times per pass, so map lookups there dominated the cost.
  const indexOf = new Map(nodes.map((node, i) => [node.id, i]))
  const links = view.edges.flatMap((edge) => {
    const a = indexOf.get(edge.source),
      b = indexOf.get(edge.target)
    return a === undefined || b === undefined || a === b ? [] : [[a, b] as const]
  })
  const fx = new Float64Array(nodes.length),
    fy = new Float64Array(nodes.length)
  for (let pass = 0; pass < 160; pass++) {
    for (let i = 0; i < nodes.length; i++) {
      fx[i] = (500 - nodes[i].x) * 0.008
      fy[i] = (300 - nodes[i].y) * 0.008
    }
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x,
          dy = nodes[i].y - nodes[j].y,
          distance = Math.max(1, Math.hypot(dx, dy))
        const power = Math.min(18, 13000 / (distance * distance))
        const x = (dx / distance) * power,
          y = (dy / distance) * power
        fx[i] += x
        fy[i] += y
        fx[j] -= x
        fy[j] -= y
      }
    for (const [i, j] of links) {
      const dx = nodes[j].x - nodes[i].x,
        dy = nodes[j].y - nodes[i].y,
        distance = Math.max(1, Math.hypot(dx, dy)),
        power = (distance - 175) * 0.012
      const x = (dx / distance) * power,
        y = (dy / distance) * power
      fx[i] += x
      fy[i] += y
      fx[j] -= x
      fy[j] -= y
    }
    const cooling = 1 - pass / 210
    for (let i = 0; i < nodes.length; i++) {
      nodes[i].x += Math.max(-12, Math.min(12, fx[i])) * cooling
      nodes[i].y += Math.max(-12, Math.min(12, fy[i])) * cooling
    }
  }
  return Object.fromEntries(nodes.map((node) => [node.id, { x: node.x, y: node.y }]))
}
