// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import ProfilePage from './ProfilePage'

vi.mock('../store/session', () => ({
  useSession: () => ({ user: { id: 'U-1', name: 'Anna', email: 'a@example.com' }, ready: true }),
}))
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('stores the profile only after explicit consent, and unticking consent erases it', async () => {
  const writes: Record<string, unknown>[] = []
  let stored = false
  const state = () => ({
    stored,
    consent_at: stored ? '2026-10-27T10:00:00' : null,
    profile: stored ? { machines: [], name: 'Anna', preferred_machine: 'M-1' } : null,
    account: { name: 'Anna', email: 'a@example.com', company: null },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/me/profile') && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body))
        writes.push(body)
        stored = body.consent === true
      }
      if (url.endsWith('/me/profile')) return new Response(JSON.stringify(state()))
      return new Response('[]')
    }),
  )
  render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  )
  const consent = (await screen.findByRole('checkbox')) as HTMLInputElement
  expect(consent.checked).toBe(false)
  expect(screen.getByText('No profile is stored.')).toBeTruthy()

  fireEvent.change(screen.getByLabelText('Preferred machine model'), { target: { value: 'M-1' } })
  fireEvent.click(consent)
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
  await screen.findByText('Profile saved.')
  expect(writes[0]).toMatchObject({ consent: true, preferred_machine: 'M-1', name: 'Anna' })

  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: /Save/ }))
  await waitFor(() => expect(screen.getByText(/Consent withdrawn/)).toBeTruthy())
  expect(writes[1]).toMatchObject({ consent: false })
  expect(stored).toBe(false)
})
