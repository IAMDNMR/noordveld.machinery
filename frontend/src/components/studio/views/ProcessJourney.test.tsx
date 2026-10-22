// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { emptyDefinition } from '../model/applicationDefinition'
import type { WorkflowDefinition } from '../../../api/applicationDefinition'
import { ProcessJourney } from './ProcessJourney'
afterEach(cleanup)
it('shows owners and real paths, distinguishes documentation, and selects a next step', () => {
  const definition = emptyDefinition()
  const workflow: WorkflowDefinition = {
    version: 1,
    id: 'flow',
    name: 'Review requests',
    states: [
      {
        id: 'review',
        label: 'Review the request',
        kind: 'review',
        outputs: [],
        role_id: null,
        rule_ids: [],
      },
      { id: 'done', label: 'Request completed', kind: 'end', outputs: [], outcome: 'success' },
    ],
    transitions: [
      {
        id: 'next',
        source: 'review',
        target: 'done',
        condition: { kind: 'always', field: null, value: null },
      },
    ],
  }
  const select = vi.fn()
  render(<ProcessJourney workflow={workflow} definition={definition} onSelect={select} />)
  expect(screen.getByText('No role assigned')).toBeTruthy()
  expect(screen.queryByText('No rules attached')).toBeNull() // empty sections are not shown
  fireEvent.click(screen.getByRole('button', { name: /Next\s*Request completed/ }))
  expect(select).toHaveBeenCalledWith('done')
  expect(screen.getByText('This process path ends here.')).toBeTruthy()
})
