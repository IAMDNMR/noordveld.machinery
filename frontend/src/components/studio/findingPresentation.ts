import type { ApplicationDefinition, Finding } from '../../api/applicationDefinition'

/** Severity determines what blocks progress; a defect category alone does not. */
export function findingGroup(item: Finding): Finding['category'] {
  if (item.category === 'business_decision' || item.category === 'assumption') return item.category
  return item.severity === 'error' ? 'defect' : 'information'
}

/** Show saved business names while retaining finding IDs in the underlying audit data. */
export function findingText(text: string, definition: ApplicationDefinition): string {
  const names = new Map<string, string>()
  const business = definition.business
  if (!business) return text
  for (const item of [...business.entities, ...business.roles, ...business.exceptions])
    names.set(item.id, item.name)
  for (const item of business.rules) names.set(item.id, item.description)
  for (const item of business.requirements) names.set(item.id, item.statement)
  for (const screen of definition.screens) names.set(screen.id, screen.title)
  for (const workflow of definition.workflow_definitions ?? []) {
    names.set(workflow.id, workflow.name)
    for (const state of workflow.states) {
      // Step IDs are scoped to a process. Do not guess when two steps share an ID.
      if (names.has(state.id) && names.get(state.id) !== state.label) names.set(state.id, '')
      else if (!names.has(state.id)) names.set(state.id, state.label)
    }
  }
  return text.replace(/\b[a-z][a-z0-9_-]*\b/g, (id) => names.get(id) || id)
}
