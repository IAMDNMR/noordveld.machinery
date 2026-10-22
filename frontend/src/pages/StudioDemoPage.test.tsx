// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StudioDemoPage from './StudioDemoPage'
import snapshot from '../assets/studio/demo-application.json'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('browses the public reference design without sign-in, backend or saving business records', () => {
  const network = vi.fn(() => Promise.reject(new Error('No backend')))
  vi.stubGlobal('fetch', network)
  render(
    <MemoryRouter>
      <StudioDemoPage />
    </MemoryRouter>,
  )
  expect(screen.getByRole('heading', { name: 'Application overview' })).toBeTruthy()
  const task = snapshot.screens.find((item) => item.trace?.generated)!
  fireEvent.click(
    within(screen.getByRole('navigation', { name: 'Application navigation' })).getByRole('button', {
      name: task.title,
    }),
  )
  expect(screen.getByRole('heading', { name: task.title, level: 2 })).toBeTruthy()
  expect(network).not.toHaveBeenCalled()
  expect(screen.getByRole('link', { name: 'Open Design Studio' }).getAttribute('href')).toBe(
    '/design-studio',
  )
  expect(snapshot.approvals).toEqual([])
  expect(snapshot.fixtures).toEqual([])
  expect(snapshot.business.integrations).toEqual([])
})
