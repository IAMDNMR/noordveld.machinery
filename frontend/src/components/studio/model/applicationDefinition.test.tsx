// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup,  render, screen } from '@testing-library/react'
import { ApplicationRenderer } from '../canvas/ApplicationRenderer'
import {
  
  emptyDefinition,
  
  
  
  
  
  
  
  validateEditorDefinition,
} from './applicationDefinition'


afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})





it('fails closed on unsupported components, properties and trees', () => {
  const base = emptyDefinition()
  for (const candidate of [
    {
      ...base,
      screens: [
        { ...base.screens[0], components: [{ ...base.screens[0].components[0], kind: 'script' }] },
      ],
    },
    { ...base, extra: 'unsafe' },
    {
      ...base,
      screens: [
        {
          ...base.screens[0],
          components: [{ ...base.screens[0].components[0], placement: { span: 99 } }],
        },
      ],
    },
  ])
    expect(validateEditorDefinition(candidate).value).toBeNull()
  const fetch = vi.spyOn(globalThis, 'fetch')
  render(<ApplicationRenderer definition={{ ...base, unsafe: true }} />)
  expect(screen.getByRole('alert')).toBeTruthy()
  expect(fetch).not.toHaveBeenCalled()
})






