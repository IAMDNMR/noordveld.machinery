import type { BusinessRule, WorkflowDefinition } from '../../../api/applicationDefinition'

export type NodeBox = { id: string; x: number; y: number; rank: number; unreachable: boolean }
export const NODE_W = 224
export const NODE_H = 86
const GAP_X = 70
const GAP_Y = 34

/** Deterministic layered layout: ranks follow breadth-first discovery from the start; edges back to an earlier
 * step are drawn as loops instead of pushing it right. Unreachable steps get a column of their own. */
export function layoutProcess(workflow: WorkflowDefinition): {
  nodes: Map<string, NodeBox>
  width: number
  height: number
} {
  const ids = workflow.states.map((state) => state.id)
  const start = workflow.states.find((state) => state.kind === 'start')?.id
  const order = new Map<string, number>()
  if (start) {
    const queue = [start]
    order.set(start, 0)
    while (queue.length) {
      const current = queue.shift()!
      for (const edge of workflow.transitions) {
        if (edge.source === current && ids.includes(edge.target) && !order.has(edge.target)) {
          order.set(edge.target, order.size)
          queue.push(edge.target)
        }
      }
    }
  }
  const rank = new Map<string, number>([...order.keys()].map((id) => [id, 0]))
  for (const id of [...order.keys()].sort((a, b) => order.get(a)! - order.get(b)!)) {
    for (const edge of workflow.transitions) {
      if (edge.source === id && order.has(edge.target) && order.get(edge.target)! > order.get(id)!)
        rank.set(edge.target, Math.max(rank.get(edge.target)!, rank.get(id)! + 1))
    }
  }
  const lastRank = Math.max(0, ...rank.values())
  const unreachable = ids.filter((id) => !order.has(id))
  unreachable.forEach((id) => rank.set(id, lastRank + 1))
  const columns = new Map<number, string[]>()
  for (const id of ids
    .slice()
    .sort(
      (a, b) => (order.get(a) ?? 1e6 + ids.indexOf(a)) - (order.get(b) ?? 1e6 + ids.indexOf(b)),
    )) {
    const column = columns.get(rank.get(id)!) ?? []
    column.push(id)
    columns.set(rank.get(id)!, column)
  }
  const nodes = new Map<string, NodeBox>()
  const bandHeights = new Map<number, number>()
  for (const [column, members] of columns)
    bandHeights.set(
      Math.floor(column / 4),
      Math.max(bandHeights.get(Math.floor(column / 4)) ?? 0, members.length),
    )
  const bandOffset = (band: number) =>
    [...bandHeights]
      .filter(([key]) => key < band)
      .reduce((sum, [, rows]) => sum + rows * (NODE_H + GAP_Y) + 42, 0)
  for (const [column, members] of columns) {
    const band = Math.floor(column / 4)
    const slot = band % 2 ? 3 - (column % 4) : column % 4
    members.forEach((id, row) =>
      nodes.set(id, {
        id,
        rank: column,
        x: 24 + slot * (NODE_W + GAP_X),
        y: 24 + bandOffset(band) + row * (NODE_H + GAP_Y),
        unreachable: !order.has(id),
      }),
    )
  }
  return {
    nodes,
    width: 48 + Math.min(4, Math.max(...columns.keys(), 0) + 1) * (NODE_W + GAP_X) - GAP_X,
    height: 60 + Math.max(0, ...[...nodes.values()].map((node) => node.y)) + NODE_H,
  }
}

/** Problems per step that the diagram marks: the same structural checks the editor and the server apply. */
export function stepIssues(
  workflow: WorkflowDefinition,
  rules: BusinessRule[],
): Map<string, string[]> {
  const issues = new Map<string, string[]>(workflow.states.map((state) => [state.id, []]))
  const add = (id: string, message: string) => issues.get(id)?.push(message)
  const start = workflow.states.find((state) => state.kind === 'start')
  const ends = new Set(
    workflow.states.filter((state) => state.kind === 'end').map((state) => state.id),
  )
  const reach = (seed: Set<string>, forward: boolean) => {
    const seen = new Set(seed)
    for (;;) {
      const next = new Set([
        ...seen,
        ...workflow.transitions
          .filter((edge) => seen.has(forward ? edge.source : edge.target))
          .map((edge) => (forward ? edge.target : edge.source)),
      ])
      if (next.size === seen.size) return seen
      next.forEach((id) => seen.add(id))
    }
  }
  const reached = start ? reach(new Set([start.id]), true) : new Set<string>()
  const finishing = reach(ends, false)
  const outcomes = new Map(rules.map((rule) => [rule.id, rule.outcomes ?? []]))
  for (const state of workflow.states) {
    if (!reached.has(state.id)) add(state.id, 'Cannot be reached from the start.')
    if (!finishing.has(state.id)) add(state.id, 'Has no route to an end.')
    if (state.kind !== 'start' && state.kind !== 'end' && !state.role_id)
      add(state.id, 'No responsible role.')
    if (state.kind === 'end' && !state.outcome) add(state.id, 'End outcome not set.')
    const edges = workflow.transitions.filter((edge) => edge.source === state.id)
    for (const output of state.outputs) {
      const handled = new Set(
        edges
          .filter((edge) => edge.condition.field === output && edge.condition.kind === 'equals')
          .map((edge) => String(edge.condition.value)),
      )
      const missing = (outcomes.get(output) ?? []).filter((outcome) => !handled.has(outcome))
      if (
        missing.length &&
        !edges.some(
          (edge) => edge.condition.field === output && edge.condition.kind === 'not_equals',
        )
      )
        add(state.id, `No path for ${output} = ${missing.join(', ')}.`)
    }
    if (state.kind === 'branch' && edges.length < 2)
      add(state.id, 'A decision needs at least two paths.')
  }
  return issues
}

export const V_GAP_X = 44
export const V_GAP_Y = 58
export type VerticalLayout = {
  nodes: Map<string, NodeBox>
  width: number
  height: number
  laneX: number
}

/** Top-down layered layout for reading a process: one row per rank, parallel paths side by side, rows ordered by the position of
 * their predecessors (fewer crossings), exception paths after the main steps in their row. Loops are routed in a lane on the right
 * (`laneX`), so no edge has to pass through a node. Deterministic: the same process always draws the same way. */
export function layoutProcessVertical(workflow: WorkflowDefinition): VerticalLayout {
  const ids = workflow.states.map((state) => state.id)
  const kind = new Map(workflow.states.map((state) => [state.id, state.kind]))
  const start = workflow.states.find((state) => state.kind === 'start')?.id
  const order = new Map<string, number>()
  if (start) {
    const queue = [start]
    order.set(start, 0)
    while (queue.length) {
      const current = queue.shift()!
      for (const edge of workflow.transitions)
        if (edge.source === current && ids.includes(edge.target) && !order.has(edge.target)) {
          order.set(edge.target, order.size)
          queue.push(edge.target)
        }
    }
  }
  const forward = workflow.transitions.filter(
    (edge) =>
      order.has(edge.source) &&
      order.has(edge.target) &&
      order.get(edge.target)! > order.get(edge.source)!,
  )
  const rank = new Map<string, number>([...order.keys()].map((id) => [id, 0]))
  for (const id of [...order.keys()].sort((a, b) => order.get(a)! - order.get(b)!)) {
    for (const edge of forward)
      if (edge.source === id)
        rank.set(edge.target, Math.max(rank.get(edge.target)!, rank.get(id)! + 1))
  }
  const last = Math.max(0, ...rank.values())
  ids.filter((id) => !order.has(id)).forEach((id) => rank.set(id, last + 1))
  const rows = new Map<number, string[]>()
  for (const id of ids) rows.set(rank.get(id)!, [...(rows.get(rank.get(id)!) ?? []), id])
  const columns = Math.max(1, ...[...rows.values()].map((row) => row.length))
  const slot = NODE_W + V_GAP_X
  const x = new Map<string, number>()
  for (const r of [...rows.keys()].sort((a, b) => a - b)) {
    const row = rows.get(r)!
    const centre = (id: string) => {
      const from = forward
        .filter((edge) => edge.target === id && x.has(edge.source))
        .map((edge) => x.get(edge.source)!)
      return from.length
        ? from.reduce((sum, value) => sum + value, 0) / from.length
        : (order.get(id) ?? 0)
    }
    row.sort(
      (a, b) =>
        Number(kind.get(a) === 'exception') - Number(kind.get(b) === 'exception') ||
        centre(a) - centre(b) ||
        (order.get(a) ?? 0) - (order.get(b) ?? 0),
    )
    const offset = (columns - row.length) / 2
    row.forEach((id, index) => x.set(id, 24 + (offset + index) * slot))
  }
  const nodes = new Map<string, NodeBox>(
    ids.map((id) => [
      id,
      {
        id,
        rank: rank.get(id)!,
        x: x.get(id)!,
        y: 24 + rank.get(id)! * (NODE_H + V_GAP_Y),
        unreachable: !order.has(id),
      },
    ]),
  )
  const laneX = 24 + columns * slot - V_GAP_X + 28
  const loops = workflow.transitions.filter(
    (edge) => !forward.includes(edge) && edge.source !== edge.target,
  ).length
  return {
    nodes,
    width: laneX + 24 + loops * 12,
    height: 48 + (Math.max(0, ...rank.values()) + 1) * (NODE_H + V_GAP_Y) - V_GAP_Y,
    laneX,
  }
}
