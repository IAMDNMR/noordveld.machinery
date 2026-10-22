import { expect, it } from 'vitest'
import type { BusinessEntity } from '../../../api/applicationDefinition'
import { layoutEntities,  } from './ErDiagram'

const entity = (id: string, attributes: number, targets: string[] = []): BusinessEntity => ({
  id,
  name: id,
  attributes: Array.from({ length: attributes }, (_, index) => ({
    id: `a${index}`,
    name: `Attribute ${index}`,
    type: 'string' as const,
    required: index === 0,
    key: index === 0,
  })),
  relationships: targets.map((target) => ({
    id: `to_${target}`,
    name: `to ${target}`,
    target,
    cardinality: 'many_to_one' as const,
  })),
})

it('places every entity once, without overlap, at any width, and draws one line per relationship', () => {
  const entities = [
    entity('order', 9, ['customer', 'carrier']),
    entity('customer', 3),
    entity('carrier', 12, ['depot']),
    entity('depot', 2),
    entity('vehicle', 5, ['carrier']),
    entity('route', 1, ['depot', 'ghost']),
  ]
  for (const columns of [2, 3, 5]) {
    const { boxes, edges } = layoutEntities(entities, columns)
    expect([...boxes.keys()].sort()).toEqual(entities.map((item) => item.id).sort())
    const all = [...boxes.values()]
    for (const [index, a] of all.entries())
      for (const b of all.slice(index + 1)) {
        const apart = a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y
        expect(apart, `${a.id} and ${b.id} overlap with ${columns} columns`).toBe(true)
      }
    expect(edges).toHaveLength(5) // the relationship to an entity that does not exist is not drawn
  }
})




