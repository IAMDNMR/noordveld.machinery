// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { emptyDefinition } from '../model/applicationDefinition'
import { ApplicationPreview } from './ApplicationPreview'
afterEach(cleanup)
it('browses saved screens and returns home without mutating the definition', () => {
  const definition = emptyDefinition()
  definition.screens = [
    { id: 'task', title: 'Review request', components: [], trace: { generated: true } },
  ]
  const original = JSON.stringify(definition)
  render(<ApplicationPreview definition={definition} viewport="desktop" />)
  fireEvent.click(
    within(screen.getByRole('navigation', { name: 'Application navigation' })).getByRole('button', {
      name: 'Review request',
    }),
  )
  expect(screen.getByRole('heading', { name: 'Review request' })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Theme'), { target: { value: '#5554cf' } })
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
  expect(screen.getByRole('heading', { name: 'Application overview' })).toBeTruthy()
  expect(JSON.stringify(definition)).toBe(original)
})
