import { expect, it } from 'vitest'
import {
  emptyDefinition,
  normalizeStoredDefinition,
  validateEditorDefinition,
} from './applicationDefinition'
import {  removeBusinessItem } from './businessDefinition'
import { businessDefinition, generatedDefinition } from './__fixtures__/businessDefinition'



const valid = (definition: unknown) =>
  validateEditorDefinition(normalizeStoredDefinition(definition)).value !== null

it('accepts a business design and legacy definitions without one, and rejects unrelated top-level keys', () => {
  expect(validateEditorDefinition(businessDefinition()).error).toBeNull()
  expect(validateEditorDefinition(emptyDefinition()).error).toBeNull()
  expect(valid({ ...businessDefinition(), extra: {} })).toBe(false)
  expect(
    valid({
      ...businessDefinition(),
      business: { ...businessDefinition().business, unsupported: [] },
    }),
  ).toBe(false)
})










it('removes an item together with every reference to it', () => {
  const removed = removeBusinessItem(generatedDefinition(), 'requirements', 'req_order')
  expect(validateEditorDefinition(removed).error).toBeNull()
  expect(JSON.stringify(removed)).not.toContain('req_order')
  const noEntity = removeBusinessItem(generatedDefinition(), 'entities', 'ent_order')
  expect(validateEditorDefinition(noEntity).error).toBeNull()
  const noRule = removeBusinessItem(businessDefinition(), 'rules', 'rule_stock')
  expect(
    noRule.workflow_definitions![0].transitions.every(
      (edge) => edge.condition.field !== 'rule_stock',
    ),
  ).toBe(true)
})
