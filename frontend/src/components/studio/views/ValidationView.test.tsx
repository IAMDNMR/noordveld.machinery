// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { Finding } from '../../../api/applicationDefinition'
import type { StudioState } from '../../../api/studio'
import { emptyDefinition } from '../model/applicationDefinition'
import { emptyBusiness } from '../model/businessDefinition'
import { ValidationView } from './ValidationView'
import { findingGroup, findingText } from '../findingPresentation'
import type { ViewProps } from './types'

afterEach(cleanup)
const finding = (severity: Finding['severity']): Finding => ({
  id: 'exception:qa',
  code: 'ESCALATION_NO_AUTHORITY',
  severity,
  category: 'defect',
  message: "Exception 'exc_missing' has no approver.",
  remediation: 'Choose an approver.',
  tab: 'workflow',
  artefacts: [],
  rationale: 'Review recovery.',
})
function props(severity: Finding['severity']): ViewProps {
  const definition = { ...emptyDefinition(), business: emptyBusiness(), workflow_definitions: [] }
  definition.business!.brief.goal = 'Manage warehouse work'
  definition.business!.requirements.push({
    id: 'req_work',
    statement: 'Receive goods',
    priority: 'must',
    kind: 'functional',
    status: 'agreed',
    acceptance_criteria: [],
    deferral_reason: '',
    origin: null,
  })
  const analysis = {
    findings: [finding(severity)],
    counts: {
      error: severity === 'error' ? 1 : 0,
      warning: severity === 'warning' ? 1 : 0,
      info: 0,
    },
    blocking: severity === 'error',
  }
  return {
    studio: {
      definition,
      revision: 1,
      flow: { active: 'checks', reviewed: [], ready: false },
      analysis: { design: analysis, process: analysis },
      approval: {
        design: { state: 'none', record: null },
        process: { state: 'none', record: null },
      },
    } as unknown as StudioState,
    access: { can: { edit: true, approve: true }, denied: {} } as ViewProps['access'],
    busy: false,
    recent: new Set(),
    ask: vi.fn(),
    say: vi.fn(),
    act: vi.fn(),
    go: vi.fn(),
    answer: vi.fn(),
    select: vi.fn(),
    selection: null,
    approve: vi.fn(),
    refresh: vi.fn(),
    userName: 'Reviewer',
  }
}
it('opening validation never sends a repair or changes the saved design', () => {
  const p = props('error')
  render(<ValidationView {...p} />)
  expect(p.say).not.toHaveBeenCalled()
  expect(p.act).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Suggest fixes' }))
  expect(p.say).toHaveBeenCalledOnce()
  expect(p.say).toHaveBeenCalledWith(expect.stringContaining('before saving'))
})
it('warnings remain available but never appear as blocking defects', () => {
  render(<ValidationView {...props('warning')} />)
  expect(screen.queryByRole('button', { name: 'Suggest fixes' })).toBeNull()
  expect(screen.queryByText('Fix before generating')).toBeNull()
  expect(screen.getByLabelText('Warnings and notes').getAttribute('open')).toBeNull()
  expect(findingGroup(finding('warning'))).toBe('information')
  expect(findingGroup(finding('error'))).toBe('defect')
})
it('explains unavailable behavior before application generation', () => {
  const p = props('warning')
  p.studio.execution_gaps = [
    {
      item: 'rule_test',
      category: 'missing_logic',
      detail: 'Packing approval',
      text: 'This rule is not implemented yet.',
      decision: null,
    },
  ]
  render(<ValidationView {...p} />)
  expect(screen.getByText('1 capabilities need setup')).toBeTruthy()
  expect(screen.getByText('Packing approval')).toBeTruthy()
})
it('uses business names in findings and preserves unknown references', () => {
  const definition = { ...emptyDefinition(), business: emptyBusiness(), workflow_definitions: [] }
  definition.business!.exceptions.push({
    id: 'exc_missing',
    name: 'No storage space',
    trigger: 'No free bin',
    recovery: 'Ask supervisor',
    resolution: null,
    resolution_state_id: null,
    origin: null,
  })
  expect(findingText("Exception 'exc_missing' and unknown_id", definition)).toBe(
    "Exception 'No storage space' and unknown_id",
  )
})
