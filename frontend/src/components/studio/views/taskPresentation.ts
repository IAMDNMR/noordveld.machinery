import type { WorkflowState } from '../../../api/applicationDefinition'

/** Presentation follows task intent; these choices never change workflow rules. */
export function taskPresentation(step: WorkflowState | null | undefined, title: string) {
  if (step?.kind === 'end') return { layout: 'outcome', label: 'Process outcome' }
  if (step?.kind === 'exception') return { layout: 'recovery', label: 'Exception resolution' }
  if (step?.kind === 'approval' || step?.kind === 'review')
    return { layout: 'decision', label: 'Decision workspace' }
  if (step?.kind === 'search') return { layout: 'search', label: 'Find and select' }
  if (/receiv|receipt|check.?in|reconcile|matching/i.test(title))
    return { layout: 'receiving', label: 'Reference and reconciliation' }
  if (/plan|schedule|assign|dispatch/i.test(title))
    return { layout: 'planning', label: 'Planning workspace' }
  if (/order|requisition|invoice|request|application/i.test(title))
    return { layout: 'document', label: 'Document workspace' }
  return { layout: 'task', label: 'Task workspace' }
}
