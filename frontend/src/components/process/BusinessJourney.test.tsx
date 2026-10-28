// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { BusinessJourney } from './BusinessJourney'
import { OwnershipJourney } from '../../sections/OwnershipJourney'

afterEach(cleanup)

it.each([
  ['aftersales', 5],
  ['portal', 5],
  ['spark', 4],
] as const)('explores %s with bounded navigation and matching details', (kind, count) => {
  const { unmount, container } = render(
    <MemoryRouter>
      <BusinessJourney kind={kind} />
    </MemoryRouter>,
  )
  const previous = screen.getByRole('button', { name: 'Previous process step' })
  const next = screen.getByRole('button', { name: 'Next process step' })
  const status = screen.getByRole('status')
  const details = screen.getByRole('region', { name: / details$/ })
  expect((previous as HTMLButtonElement).disabled).toBe(true)
  for (let index = 0; index < count; index++) {
    expect(status.textContent).toContain(`Step ${index + 1} of ${count}`)
    const selected = container.querySelector('button[aria-expanded="true"]')!
    expect(details.textContent).toContain(selected.querySelector('strong')!.textContent)
    expect(details.textContent).toContain('What moves forward')
    if (index < count - 1) fireEvent.click(next)
  }
  expect((next as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(previous)
  expect(status.textContent).toContain(`Step ${count - 1} of ${count}`)
  unmount()
  if (kind === 'aftersales') {
    render(
      <MemoryRouter>
        <OwnershipJourney />
      </MemoryRouter>,
    )
    const source = screen.getByRole('tab', { name: /Source/ })
    fireEvent.click(source)
    expect(source.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('link', { name: 'Open Parts Portal' }).getAttribute('href')).toBe(
      '/parts-store',
    )
    fireEvent.keyDown(source, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: /Understand/ }))
    expect(screen.getByRole('link', { name: 'Meet Spark' }).getAttribute('href')).toBe('/spark')
  }
})
