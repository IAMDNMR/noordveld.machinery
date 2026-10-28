// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { InvitationPreview } from '../api/workspace'

const session: {
  ready: boolean
  user: { id: string; name: string } | null
  signOut: () => Promise<void>
} = { ready: true, user: null, signOut: vi.fn(async () => undefined) }
vi.mock('../store/session', () => ({ useSession: () => session }))
vi.mock('../api/workspace', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/workspace')>()),
  previewInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
}))
import { acceptInvitation, previewInvitation } from '../api/workspace'
import InvitationPage from './InvitationPage'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  session.user = null
})

const TOKEN = 't'.repeat(40)
const offer: InvitationPreview = {
  organization: { id: 'org_a', name: 'Acme Machinery' },
  email_hint: 'f•••••@example.invalid',
  role: null,
  app_grants: [{ app_id: 'agentic_shopping', app_role: 'customer' }],
  team: null,
  expires_at: '2026-12-01T00:00:00+00:00',
}
const Where = () => {
  const location = useLocation()
  return (
    <p data-testid="where">
      {location.pathname}
      {location.search}
    </p>
  )
}
const open = (token = TOKEN) =>
  render(
    <MemoryRouter initialEntries={[`/invite?token=${token}`]}>
      <Routes>
        <Route path="/invite" element={<InvitationPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )

it('accepting applies it on the server and lands on the workspace welcome', async () => {
  session.user = { id: 'frank', name: 'Frank' }
  vi.mocked(previewInvitation).mockResolvedValue(offer)
  vi.mocked(acceptInvitation).mockResolvedValue({
    org_id: 'org_a',
    role: null,
    app_grants: offer.app_grants,
  })
  open()
  fireEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }))
  await waitFor(() => expect(vi.mocked(acceptInvitation)).toHaveBeenCalledWith(TOKEN))
  expect((await screen.findByTestId('where')).textContent).toBe('/workspace?welcome=1&org=org_a')
})

it('an expired, used or unknown invitation reveals nothing and says what to do', async () => {
  vi.mocked(previewInvitation).mockRejectedValue(
    new ApiError(404, 'not_found', 'This invitation is invalid, expired or already used'),
  )
  open()
  expect((await screen.findByRole('alert')).textContent).toMatch(
    /invalid, has expired, or has already been used/,
  )
  expect(screen.queryByRole('button', { name: 'Accept invitation' })).toBeNull()
})
