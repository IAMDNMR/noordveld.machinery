import { expect, it } from 'vitest'
import type { WorkflowDefinition } from '../../../api/applicationDefinition'
import { layoutProcessVertical, NODE_H, NODE_W } from './processLayout'

const step = (id: string, kind: string) =>
  ({ id, label: id, kind, outputs: [] }) as unknown as WorkflowDefinition['states'][number]
const edge = (source: string, target: string) =>
  ({
    id: `${source}-${target}`,
    source,
    target,
    condition: { kind: 'always', field: null, value: null },
  }) as WorkflowDefinition['transitions'][number]

// Start → a → decision → (b | exception) ; b → end ; exception → a (recovery loop) ; a skip edge decision → end.
const workflow = {
  version: 1,
  id: 'wf',
  name: 'wf',
  states: [
    step('start', 'start'),
    step('a', 'form'),
    step('d', 'branch'),
    step('b', 'action'),
    step('x', 'exception'),
    step('end', 'end'),
  ],
  transitions: [
    edge('start', 'a'),
    edge('a', 'd'),
    edge('d', 'b'),
    edge('d', 'x'),
    edge('b', 'end'),
    edge('x', 'a'),
    edge('d', 'end'),
  ],
} as WorkflowDefinition

it('lays a process out top-down without overlapping nodes, with loops in a lane to the right', () => {
  const { nodes, laneX, width } = layoutProcessVertical(workflow)
  const boxes = [...nodes.values()]
  for (const a of boxes)
    for (const b of boxes) {
      if (a.id < b.id)
        expect(
          a.x + NODE_W <= b.x || b.x + NODE_W <= a.x || a.y + NODE_H <= b.y || b.y + NODE_H <= a.y,
          `${a.id} overlaps ${b.id}`,
        ).toBe(true)
    }
  for (const item of workflow.transitions.filter((t) => t.id !== 'x-a'))
    expect(nodes.get(item.target)!.y, item.id).toBeGreaterThan(nodes.get(item.source)!.y)
  expect(boxes.every((box) => box.x + NODE_W < laneX) && laneX < width).toBe(true)
  const row = boxes
    .filter((box) => box.y === nodes.get('b')!.y)
    .sort((p, q) => p.x - q.x)
    .map((box) => box.id)
  expect(row).toEqual(['b', 'x']) // the exception path sits after the main step in its row
})
