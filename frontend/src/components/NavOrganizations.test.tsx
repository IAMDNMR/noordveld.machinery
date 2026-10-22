// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const signedIn = {
  ready: true,
  user: { id: 'u1', name: 'U', email: 'u@example.invalid', role: 'END_USER' as const },
  signOut: vi.fn(),
}
vi.mock('../store/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../store/session')>()),
  useSession: () => signedIn,
}))
vi.mock('../api/workspace', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/workspace')>()),
  getWorkspace: vi.fn(),
}))
import { getWorkspace, type Workspace } from '../api/workspace'
import { getActiveOrganization } from '../api/client'
import { Nav } from './Nav'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
const labels = () => [...document.querySelectorAll('.nav__links a')].map((a) => a.textContent)
const workspace = (studio: boolean, configured = true): Workspace => ({
  user: { id: 'u1', name: 'U', email: 'u@example.invalid' },
  directory_configured: configured,
  platform_roles: [],
  organizations: [{ id: 'org_a', name: 'A', roles: [] }],
  active_organization: 'org_a',
  permissions: [],
  studio: { visible: studio, can_create: false },
  applications: [],
  projects: [],
  tasks: [],
  activity: [],
  onboarding: [],
})

it('adds the workspace and removes Design Studio for someone the server did not grant it', async () => {
  vi.mocked(getWorkspace).mockResolvedValue(workspace(false))
  render(
    <MemoryRouter>
      <Nav />
    </MemoryRouter>,
  )
  await waitFor(() => expect(labels()[0]).toBe('Workspace'))
  expect(labels()).not.toContain('Design Studio')
  expect(getActiveOrganization()).toBe('org_a')
})

it('keeps the commerce navigation separate even when Studio is available', async () => {
  vi.mocked(getWorkspace).mockResolvedValue(workspace(true))
  render(
    <MemoryRouter>
      <Nav />
    </MemoryRouter>,
  )
  await waitFor(() => expect(labels()).toContain('Workspace'))
  expect(labels()).not.toContain('Design Studio')
})
