// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { emptyDefinition } from '../model/applicationDefinition'
import { ThemePicker } from './ThemePicker'
afterEach(cleanup)
it('sends a colour choice through the saved project action and reflects saved values', () => {
  const definition = emptyDefinition(),
    act = vi.fn()
  const view = render(<ThemePicker definition={definition} act={act} disabled={false} />)
  fireEvent.change(screen.getByLabelText('Application colour'), { target: { value: '#245f8b' } })
  expect(act).toHaveBeenCalledWith([{ type: 'set_theme', primary: '#245f8b' }], expect.any(String))
  view.rerender(
    <ThemePicker
      definition={{ ...definition, theme: { ...definition.theme, primary: '#245f8b' } }}
      act={act}
      disabled={true}
    />,
  )
  expect((screen.getByLabelText('Application colour') as HTMLSelectElement).value).toBe('#245f8b')
  expect((screen.getByLabelText('Application colour') as HTMLSelectElement).disabled).toBe(true)
})
