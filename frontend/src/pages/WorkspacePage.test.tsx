// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { Workspace } from '../api/workspace'

const signedIn = { ready: true, user: { id: 'alice', name: 'Alice' } }
vi.mock('../store/session', () => ({ useSession: () => signedIn }))
vi.mock('../api/workspace', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/workspace')>()),
  getWorkspace: vi.fn(),
}))
import { getWorkspace } from '../api/workspace'

import WorkspacePage from './WorkspacePage'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const app = (
  id: string,
  name: string,
  status: 'operational' | 'in_design' | 'planned',
  extra: object = {},
) => ({
  id,
  name,
  description: `${name} description`,
  domain: 'Domain',
  status,
  route: status === 'operational' ? `/${id}` : null,
  launchable: status === 'operational',
  your_roles: [],
  reason:
    status === 'operational'
      ? null
      : status === 'in_design'
        ? 'Not available for operational use yet: it is being designed.'
        : 'Planned; no project exists yet.',
  ...extra,
})
const base: Workspace = {
  user: { id: 'alice', name: 'Alice', email: 'a@example.invalid' },
  directory_configured: true,
  platform_roles: [],
  organizations: [{ id: 'org_a', name: 'Noordveld Machinery (demo)', roles: ['project_owner'] }],
  active_organization: 'org_a',
  permissions: ['app.launch'],
  applications: [
    app('parts_store', 'Parts Portal', 'operational', { your_roles: ['customer'] }),
    app('tms', 'Transport Management', 'in_design'),
    app('procurement', 'Procurement and suppliers', 'planned'),
  ],
  activity: [],
  onboarding: [],
}
const page = () =>
  render(
    <MemoryRouter>
      <WorkspacePage />
    </MemoryRouter>,
  )

it('shows commerce systems and keeps Studio projects in the separate Studio entry', async () => {
  vi.mocked(getWorkspace).mockResolvedValue(base)
  page()
  expect(await screen.findByRole('heading', { name: 'Noordveld Machinery (demo)' })).toBeTruthy()
  expect(screen.queryByRole('link', { name: 'Open Design Studio' })).toBeNull()
  const store = screen.getByRole('article', { name: 'Parts Portal' })
  expect(within(store).getByText('Available')).toBeTruthy()
  expect(within(store).getByRole('button', { name: 'Open Parts Portal' })).toBeTruthy()
  const tms = screen.getByRole('article', { name: 'Transport Management' })
  expect(within(tms).getByText('In design')).toBeTruthy()
  expect(within(tms).queryByRole('button')).toBeNull()
  expect(within(tms).getByRole('note').textContent).toMatch(/being designed/)
  expect(screen.queryByRole('region', { name: 'Projects' })).toBeNull()
  expect(screen.queryByRole('region', { name: 'Needs your attention' })).toBeNull()
})

it('gives a dealer only the systems they were granted and no Design Studio', async () => {
  vi.mocked(getWorkspace).mockResolvedValue({
    ...base,

    permissions: [],
    applications: [
      app('parts_store', 'Parts Portal', 'operational', { your_roles: ['dealer'] }),
      app('orders', 'Order processing', 'operational', {
        launchable: false,
        route: null,
        reason: 'You have not been given access to this system.',
      }),
    ],
  })
  page()
  await screen.findByRole('article', { name: 'Parts Portal' })
  expect(screen.queryByRole('region', { name: 'Design Studio' })).toBeNull()
  expect(screen.queryByRole('region', { name: 'Projects' })).toBeNull()
  expect(
    within(screen.getByRole('article', { name: 'Order processing' })).getByRole('note').textContent,
  ).toBe('You have not been given access to this system.')
})

it('guides a person without an organization and switches organizations', async () => {
  vi.mocked(getWorkspace).mockResolvedValueOnce({
    ...base,
    organizations: [],
    active_organization: null,

    applications: [],

    platform_roles: ['platform_admin'],
    onboarding: [
      'You have no organization yet. Ask an organization administrator for an invitation.',
    ],
  })
  const { unmount } = page()
  expect(await screen.findByText(/no organization yet/)).toBeTruthy()
  expect(screen.queryByRole('region', { name: 'Systems' })).toBeNull()
  unmount()
  vi.mocked(getWorkspace).mockResolvedValue({
    ...base,
    organizations: [
      { id: 'org_a', name: 'Org A', roles: ['project_owner'] },
      { id: 'org_b', name: 'Org B', roles: ['designer'] },
    ],
  })
  page()
  fireEvent.change(await screen.findByLabelText('Organization'), { target: { value: 'org_b' } })
  await waitFor(() => expect(getWorkspace).toHaveBeenLastCalledWith('org_b', expect.anything()))
})
