// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OptionalSetup } from './OptionalSetup'
import type { IntakeState } from '../../api/studio'

const intake: IntakeState = {
  catalog_version: 'test',
  selected: { region: null, industry_id: null, skipped: [], catalog_version: 'test' },
  coverage: { systems: 21, industries: 21, regions: 3 },
  systems: [],
  regional_guidance: null,
  note: '',
  questions: [
    {
      id: 'region',
      text: 'Where will the business operate?',
      optional: true,
      options: [
        { id: 'eu', name: 'European Union' },
        { id: 'india', name: 'India' },
      ],
    },
    {
      id: 'industry',
      text: 'Which industry should the draft fit?',
      optional: true,
      options: [{ id: 'transport', name: 'Transport and logistics' }],
    },
  ],
}

describe('optional setup', () => {
  
  it('skips both questions explicitly and never blocks continuing with shared knowledge', () => {
    const act = vi.fn()
    const view = render(<OptionalSetup intake={intake} busy={false} act={act} />)
    fireEvent.click(screen.getByRole('button', { name: 'Skip setup' }))
    expect(act).toHaveBeenCalledWith([{ type: 'set_intake_context', skip: ['region', 'industry'] }])
    view.rerender(<OptionalSetup intake={{ ...intake, questions: [] }} busy={false} act={act} />)
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.getByText(/Setup saved/)).toBeTruthy()
    view.unmount()
  })
})
