import type { ApplicationDefinition, Binding } from '../../../api/applicationDefinition'

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const exact = (value: Record<string, unknown>, keys: string[]) =>
  Object.keys(value).every((key) => keys.includes(key))
const id = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-z][a-z0-9_-]{1,79}$/.test(value)

export function validFixtures(value: unknown): value is ApplicationDefinition['fixtures'] {
  if (!Array.isArray(value) || value.length > 20) return false
  const ids = new Set<string>()
  for (const fixture of value) {
    if (
      !record(fixture) ||
      !exact(fixture, ['id', 'fields', 'rows']) ||
      !id(fixture.id) ||
      ids.has(fixture.id) ||
      !Array.isArray(fixture.fields) ||
      fixture.fields.length > 40 ||
      !Array.isArray(fixture.rows) ||
      fixture.rows.length > 100
    )
      return false
    ids.add(fixture.id)
    const types = new Map<string, string>()
    for (const field of fixture.fields) {
      if (
        !record(field) ||
        !exact(field, ['id', 'type']) ||
        !id(field.id) ||
        types.has(field.id) ||
        !['string', 'number', 'boolean'].includes(field.type as string)
      )
        return false
      types.set(field.id, field.type as string)
    }
    for (const row of fixture.rows) {
      if (
        !record(row) ||
        Object.keys(row).length !== types.size ||
        Object.keys(row).some((key) => !types.has(key))
      )
        return false
      for (const [key, fieldValue] of Object.entries(row)) {
        const type = types.get(key)
        if (
          fieldValue !== null &&
          !(type === 'string' && typeof fieldValue === 'string') &&
          !(type === 'number' && typeof fieldValue === 'number' && Number.isFinite(fieldValue)) &&
          !(type === 'boolean' && typeof fieldValue === 'boolean')
        )
          return false
      }
    }
  }
  return true
}

export function validLocalState(value: unknown): value is ApplicationDefinition['local_state'] {
  if (!Array.isArray(value) || value.length > 100) return false
  const ids = new Set<string>()
  return value.every((item) => {
    if (
      !record(item) ||
      !exact(item, ['id', 'type', 'initial']) ||
      !id(item.id) ||
      ids.has(item.id)
    )
      return false
    ids.add(item.id)
    return (
      (item.type === 'string' && typeof item.initial === 'string') ||
      (item.type === 'number' &&
        typeof item.initial === 'number' &&
        Number.isFinite(item.initial)) ||
      (item.type === 'boolean' && typeof item.initial === 'boolean')
    )
  })
}

export function validBinding(
  value: unknown,
  fixtures: ApplicationDefinition['fixtures'],
  state: ApplicationDefinition['local_state'],
): value is Binding {
  if (value === null) return true
  if (
    !record(value) ||
    !exact(value, ['source', 'dataset', 'field']) ||
    !id(value.dataset) ||
    !id(value.field)
  )
    return false
  return value.source === 'fixture'
    ? fixtures.some(
        (fixture) =>
          fixture.id === value.dataset && fixture.fields.some((field) => field.id === value.field),
      )
    : value.source === 'state' &&
        value.field === 'value' &&
        state.some((item) => item.id === value.dataset)
}
