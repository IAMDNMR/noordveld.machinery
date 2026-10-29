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
/**
 * Deterministic hub-and-ring layout. In each connected group the best-connected record sits in the middle, its neighbours on a ring
 * around it (records of one kind side by side), the next layer on a wider ring behind its parents. Rings widen so labels never touch.
 */
export function graphPositions(view: GraphView): Record<string, Point> {
  const ids = view.nodes.map((node) => node.id)
  const kind = new Map(view.nodes.map((node) => [node.id, node.kind]))
  const around = new Map<string, Set<string>>(ids.map((id) => [id, new Set()]))
  for (const edge of view.edges) {
    if (edge.source === edge.target || !around.has(edge.source) || !around.has(edge.target))
      continue
    around.get(edge.source)!.add(edge.target)
    around.get(edge.target)!.add(edge.source)
  }
  const seen = new Set<string>()
  const groups: string[][] = []
  for (const start of ids) {
    if (seen.has(start)) continue
    const group = [start]
    seen.add(start)
    for (let k = 0; k < group.length; k++)
      for (const next of around.get(group[k])!)
        if (!seen.has(next)) {
          seen.add(next)
          group.push(next)
        }
    groups.push(group)
  }
  groups.sort((a, b) => b.length - a.length)
  const out: Record<string, Point> = {}
  const placed: { ids: string[]; w: number; h: number; mx: number; my: number }[] = []
  for (const group of groups) {
    const cx = 0,
      cy = 0
    const hub = group.reduce((best, id) =>
      around.get(id)!.size > around.get(best)!.size ? id : best,
    )
    const layer = new Map([[hub, 0]])
    const order = [hub]
    for (let k = 0; k < order.length; k++)
      for (const next of around.get(order[k])!)
        if (!layer.has(next)) {
          layer.set(next, layer.get(order[k])! + 1)
          order.push(next)
        }
    const angle = new Map<string, number>()
    out[hub] = { x: cx, y: cy }
    const depth = Math.max(...layer.values())
    for (let d = 1; d <= depth; d++) {
      const ring = order.filter((id) => layer.get(id) === d)
      const parentAngle = (id: string) => {
        const parent = [...around.get(id)!].find((p) => layer.get(p) === d - 1)
        return parent ? (angle.get(parent) ?? 0) : 0
      }
      ring.sort((a, b) =>
        d > 1
          ? parentAngle(a) - parentAngle(b) || (kind.get(a) ?? '').localeCompare(kind.get(b) ?? '')
          : (kind.get(a) ?? '').localeCompare(kind.get(b) ?? ''),
      )
      const radius = Math.max(150 * d, (ring.length * 118) / (2 * Math.PI))
      const turn = d % 2 ? -Math.PI / 2 : -Math.PI / 2 + Math.PI / ring.length
      ring.forEach((id, k) => {
        const a = turn + (k / ring.length) * 2 * Math.PI
        angle.set(id, a)
        out[id] = { x: cx + Math.cos(a) * radius * 1.2, y: cy + Math.sin(a) * radius * 0.9 }
      })
    }
    const xs = group.map((id) => out[id].x),
      ys = group.map((id) => out[id].y)
    placed.push({
      ids: group,
      w: Math.max(...xs) - Math.min(...xs) + 190,
      h: Math.max(...ys) - Math.min(...ys) + 190,
      mx: (Math.max(...xs) + Math.min(...xs)) / 2,
      my: (Math.max(...ys) + Math.min(...ys)) / 2,
    })
  }
  // the largest group is centred; the others sit beside it (right, left, below, above, then the corners), never overlapping
  const slots = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
    [1, 1],
    [-1, 1],
    [1, -1],
    [-1, -1],
  ]
  placed.forEach((group, g) => {
    let ox = 500 - group.mx,
      oy = 310 - group.my
    if (g > 0) {
      const [sx, sy] = slots[(g - 1) % slots.length],
        lap = Math.floor((g - 1) / slots.length) + 1
      ox += sx * lap * ((placed[0].w + group.w) / 2)
      oy += sy * lap * ((placed[0].h + group.h) / 2)
    }
    for (const id of group.ids) out[id] = { x: out[id].x + ox, y: out[id].y + oy }
  })
  return out
}
