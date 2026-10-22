import { describe, expect, it } from 'vitest'
import { evidenceGraph, graphPositions } from './graphModel'

describe('answer relationship graph', () => {
  it('keeps actual evidence and provenance without adding links between disconnected groups', () => {
    const category = {
      entity: 'NVM-1010-AT',
      entity_kind: 'PART',
      relationship: 'IN_CATEGORY',
      target: 'Bucket',
      target_kind: 'CATEGORY',
      data_class: 'REAL' as const,
    }
    const supplier = {
      entity: 'NVM-2020',
      entity_kind: 'PART',
      relationship: 'SUPPLIED_BY',
      target: 'Supplier A',
      target_kind: 'SUPPLIER',
      data_class: 'SYNTHETIC_DEMO' as const,
    }
    const view = evidenceGraph([category, category, supplier])
    expect(view.nodes).toHaveLength(4)
    expect(view.edges).toHaveLength(2)
    expect(view.edges[0]).toMatchObject({
      source: 'PART:NVM-1010-AT',
      target: 'CATEGORY:Bucket',
      type: 'IN_CATEGORY',
      data_class: 'REAL',
    })
    expect(view.edges[1].data_class).toBe('SYNTHETIC_DEMO')
    const positions = graphPositions(view)
    expect(Object.keys(positions)).toHaveLength(4)
    for (const point of Object.values(positions))
      expect(Number.isFinite(point.x) && Number.isFinite(point.y)).toBe(true)
  })
})
