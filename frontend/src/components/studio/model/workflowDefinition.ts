import type { StepKind, WorkflowDefinition } from '../../../api/applicationDefinition'
import { PERMISSION, STEP_KINDS } from './businessDefinition'

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const exact = (value: Record<string, unknown>, keys: string[]) =>
  Object.keys(value).every((key) => keys.includes(key))
const id = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-z][a-z0-9_-]{1,79}$/.test(value)
const refs = (value: unknown) =>
  Array.isArray(value) &&
  value.length <= 30 &&
  value.every(id) &&
  new Set(value).size === value.length
const REF_KEYS = [
  'requirement_ids',
  'reads_entity_ids',
  'writes_entity_ids',
  'rule_ids',
  'exception_ids',
] as const
const STATE_KEYS = [
  'id',
  'label',
  'kind',
  'outputs',
  'outcome',
  'role_id',
  'permission',
  'preconditions',
  'postconditions',
  'input_fields',
  'input_relationships',
  ...REF_KEYS,
]
const inputMap = (value: unknown) =>
  value == null ||
  (record(value) &&
    Object.keys(value).length <= 30 &&
    Object.entries(value).every(([entity, fields]) => id(entity) && refs(fields)))
const conditions = (value: unknown) =>
  value === undefined ||
  (Array.isArray(value) &&
    value.length <= 20 &&
    value.every((item) => typeof item === 'string' && item.length >= 1 && item.length <= 300))
const STEP_KIND_LIST: readonly string[] = STEP_KINDS

/** Mirrors the backend's structural and graph checks; never evaluates conditions. */
export function parseWorkflow(value: unknown): WorkflowDefinition | null {
  if (
    !record(value) ||
    !exact(value, ['version', 'id', 'name', 'states', 'transitions']) ||
    value.version !== 1 ||
    !id(value.id) ||
    typeof value.name !== 'string' ||
    !value.name ||
    value.name.length > 120 ||
    !Array.isArray(value.states) ||
    value.states.length < 2 ||
    value.states.length > 100 ||
    !Array.isArray(value.transitions) ||
    value.transitions.length < 1 ||
    value.transitions.length > 200
  )
    return null
  const ids = new Set<string>()
  const starts: string[] = []
  const ends = new Set<string>()
  for (const state of value.states) {
    if (
      !record(state) ||
      !exact(state, STATE_KEYS) ||
      !id(state.id) ||
      ids.has(state.id) ||
      typeof state.label !== 'string' ||
      !state.label ||
      state.label.length > 120 ||
      !STEP_KIND_LIST.includes(state.kind as StepKind) ||
      !Array.isArray(state.outputs) ||
      state.outputs.length > 30 ||
      !state.outputs.every(id) ||
      new Set(state.outputs).size !== state.outputs.length ||
      !(
        state.outcome === undefined ||
        state.outcome === null ||
        (state.kind === 'end' &&
          ['success', 'failure', 'cancelled'].includes(state.outcome as string))
      ) ||
      !(state.role_id === undefined || state.role_id === null || id(state.role_id)) ||
      !(
        state.permission === undefined ||
        state.permission === null ||
        (typeof state.permission === 'string' &&
          state.permission.length <= 80 &&
          PERMISSION.test(state.permission))
      ) ||
      !REF_KEYS.every((key) => state[key] === undefined || refs(state[key])) ||
      !inputMap(state.input_fields) ||
      !inputMap(state.input_relationships) ||
      !conditions(state.preconditions) ||
      !conditions(state.postconditions)
    )
      return null
    ids.add(state.id)
    if (state.kind === 'start') starts.push(state.id)
    if (state.kind === 'end') ends.add(state.id)
  }
  if (starts.length !== 1 || !ends.size) return null
  const outputs = new Set(value.states.flatMap((state) => state.outputs))
  const transitionIds = new Set<string>()
  for (const edge of value.transitions) {
    if (
      !record(edge) ||
      !exact(edge, ['id', 'source', 'target', 'condition']) ||
      !id(edge.id) ||
      transitionIds.has(edge.id) ||
      !ids.has(edge.source as string) ||
      !ids.has(edge.target as string) ||
      edge.target === starts[0] ||
      ends.has(edge.source as string) ||
      !record(edge.condition) ||
      !exact(edge.condition, ['kind', 'field', 'value'])
    )
      return null
    const condition = edge.condition
    if (
      !['always', 'equals', 'not_equals'].includes(condition.kind as string) ||
      (condition.kind === 'always'
        ? condition.field != null || condition.value != null
        : !id(condition.field) ||
          !outputs.has(condition.field as string) ||
          !['string', 'number', 'boolean'].includes(typeof condition.value))
    )
      return null
    transitionIds.add(edge.id)
  }
  let reached = new Set(starts)
  while (true) {
    const expanded = new Set([
      ...reached,
      ...value.transitions.filter((edge) => reached.has(edge.source)).map((edge) => edge.target),
    ])
    if (expanded.size === reached.size) break
    reached = expanded
  }
  if (reached.size !== ids.size) return null
  let finishing = new Set(ends)
  while (true) {
    const expanded = new Set([
      ...finishing,
      ...value.transitions.filter((edge) => finishing.has(edge.target)).map((edge) => edge.source),
    ])
    if (expanded.size === finishing.size) break
    finishing = expanded
  }
  return finishing.size === ids.size ? (value as WorkflowDefinition) : null
}

export function starterWorkflow(): WorkflowDefinition {
  return {
    version: 1,
    id: 'workflow_main',
    name: 'Review flow',
    states: [
      { id: 'start', label: 'Start', kind: 'start', outputs: [] },
      { id: 'review', label: 'Review', kind: 'approval', outputs: [] },
      { id: 'end', label: 'End', kind: 'end', outputs: [] },
    ],
    transitions: [
      {
        id: 'transition_1',
        source: 'start',
        target: 'review',
        condition: { kind: 'always', field: null, value: null },
      },
      {
        id: 'transition_2',
        source: 'review',
        target: 'end',
        condition: { kind: 'always', field: null, value: null },
      },
    ],
  }
}

/** Specific, repairable problems in a draft process, in the order a person would fix them. Empty means structurally valid. */
export function workflowProblems(workflow: WorkflowDefinition): string[] {
  const problems: string[] = []
  const ids = new Set(workflow.states.map((state) => state.id))
  const label = (stateId: string) =>
    workflow.states.find((state) => state.id === stateId)?.label ?? stateId
  const starts = workflow.states.filter((state) => state.kind === 'start')
  const ends = new Set(
    workflow.states.filter((state) => state.kind === 'end').map((state) => state.id),
  )
  if (starts.length !== 1)
    problems.push(`A process needs exactly one start step (it has ${starts.length}).`)
  if (!ends.size) problems.push('A process needs at least one end step.')
  if (ids.size !== workflow.states.length) problems.push('Two steps share an ID.')
  if (!workflow.transitions.length) problems.push('Add at least one transition.')
  const outputs = new Set(workflow.states.flatMap((state) => state.outputs))
  for (const edge of workflow.transitions) {
    if (!ids.has(edge.source) || !ids.has(edge.target))
      problems.push(`Transition ${edge.id} points to a step that no longer exists.`)
    if (ends.has(edge.source))
      problems.push(`"${label(edge.source)}" is an end step and cannot have outgoing transitions.`)
    if (starts[0] && edge.target === starts[0].id)
      problems.push(`Transition ${edge.id} leads back to the start step.`)
    if (
      edge.condition.kind !== 'always' &&
      (!edge.condition.field || !outputs.has(edge.condition.field))
    )
      problems.push(`Transition ${edge.id} branches on an output no step declares.`)
    if (
      edge.condition.kind !== 'always' &&
      (edge.condition.value === null || edge.condition.value === '')
    )
      problems.push(`Transition ${edge.id} needs a value to compare.`)
  }
  if (starts.length === 1) {
    let reached = new Set([starts[0].id])
    for (;;) {
      const next = new Set([
        ...reached,
        ...workflow.transitions
          .filter((edge) => reached.has(edge.source))
          .map((edge) => edge.target),
      ])
      if (next.size === reached.size) break
      reached = next
    }
    for (const state of workflow.states)
      if (!reached.has(state.id))
        problems.push(`"${state.label}" cannot be reached from the start.`)
  }
  let finishing = new Set(ends)
  for (;;) {
    const next = new Set([
      ...finishing,
      ...workflow.transitions
        .filter((edge) => finishing.has(edge.target))
        .map((edge) => edge.source),
    ])
    if (next.size === finishing.size) break
    finishing = next
  }
  for (const state of workflow.states)
    if (ends.size && !finishing.has(state.id))
      problems.push(`"${state.label}" has no route to an end step.`)
  return [...new Set(problems)]
}
