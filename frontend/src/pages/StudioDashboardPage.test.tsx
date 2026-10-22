// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getProjectDashboard, manageProject, type DashboardData } from '../api/studioProjects'
import StudioDashboardPage from './StudioDashboardPage'

vi.mock('../api/studio', () => ({ ensureOrganization: vi.fn(async () => undefined) }))
vi.mock('../api/studioProjects', () => ({ getProjectDashboard: vi.fn(), manageProject: vi.fn() }))
const overview = (): DashboardData => ({
  counts: { active: 1, archived: 0, trashed: 1, needs_attention: 1, approved: 0 },
  projects: [
    {
      id: 'app_transport',
      name: 'Transport Hub',
      description: 'Plan deliveries and manage vehicles.',
      domain: 'logistics',
      revision: 3,
      status: 'active',
      stage: 'data',
      stage_label: 'Data Model',
      reviewed: 3,
      stage_count: 9,
      errors: 2,
      warnings: 1,
      design_approval: 'none',
      screens: 5,
      entities: 8,
      updated_at: '2026-10-19T12:00:00Z',
      can_edit: true,
    },
    {
      id: 'app_old',
      name: 'Earlier project',
      description: '',
      domain: 'other',
      revision: 4,
      status: 'trashed',
      stage: 'brief',
      stage_label: 'Requirements',
      reviewed: 0,
      stage_count: 9,
      errors: 1,
      warnings: 0,
      design_approval: 'none',
      screens: 1,
      entities: 0,
      updated_at: '',
      can_edit: true,
    },
  ],
  activity: [
    {
      project_id: 'app_transport',
      project_name: 'Transport Hub',
      revision: 3,
      actor: 'alice',
      operation: 'update',
      at: '2026-10-19T12:00:00Z',
    },
  ],
})
const mount = () =>
  render(
    <MemoryRouter>
      <StudioDashboardPage />
    </MemoryRouter>,
  )

it('keeps a failed release visible in Needs attention even when design validation has no errors', async () => {
  const data = overview()
  data.projects[0].errors = 0
  data.projects[0].design_approval = 'valid'
  data.projects[0].release = {
    id: 'release',
    revision: 3,
    created: '2026-10-20T12:00:00Z',
    test_status: 'failed',
  }
  vi.mocked(getProjectDashboard).mockResolvedValue(data)
  mount()
  const filters = await screen.findByRole('button', { name: /Needs attention/ })
  fireEvent.click(filters)
  expect(screen.getByRole('heading', { name: 'Transport Hub' })).toBeTruthy()
  expect(screen.getByText('Release saved · Tests need attention')).toBeTruthy()
})

it('opens the generated application directly from its saved project card', async () => {
  const data = overview()
  data.projects[0].runtime = { running: true, url: 'http://127.0.0.1:8100', revision: 3 }
  vi.mocked(getProjectDashboard).mockResolvedValue(data)
  mount()
  const open = await screen.findByRole('link', { name: 'Open application' })
  expect(open.getAttribute('href')).toBe('http://127.0.0.1:8100')
  expect(open.getAttribute('target')).toBe('_blank')
})
beforeEach(() => {
  vi.mocked(getProjectDashboard).mockResolvedValue(overview())
  vi.mocked(manageProject).mockResolvedValue({ id: 'app_transport', revision: 4, status: 'active' })
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
  }
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})


it('renames using the displayed revision and refreshes the dashboard', async () => {
  mount()
  fireEvent.click(await screen.findByLabelText('Actions for Transport Hub'))
  fireEvent.click(screen.getByRole('button', { name: 'Rename' }))
  fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Operations Hub' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save name' }))
  await waitFor(() =>
    expect(manageProject).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'app_transport', revision: 3 }),
      'rename',
      'Operations Hub',
    ),
  )
  await waitFor(() => expect(getProjectDashboard).toHaveBeenCalledTimes(2))
})



it('requires the exact project name before permanently deleting a trashed project', async () => {
  const data = overview()
  data.projects[1].can_delete = true
  vi.mocked(getProjectDashboard).mockResolvedValue(data)
  mount()
  await screen.findByRole('heading', { name: 'Transport Hub' })
  fireEvent.click(screen.getByRole('button', { name: /^Trash/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  const dialog = within(screen.getByRole('dialog'))
  const confirm = dialog.getByRole('button', { name: 'Delete permanently' }) as HTMLButtonElement
  expect(confirm.disabled).toBe(true)
  fireEvent.change(dialog.getByLabelText('Type the project name to confirm'), {
    target: { value: 'wrong name' },
  })
  expect(confirm.disabled).toBe(true)
  expect(manageProject).not.toHaveBeenCalled()
  fireEvent.change(dialog.getByLabelText('Type the project name to confirm'), {
    target: { value: 'Earlier project' },
  })
  fireEvent.click(confirm)
  await waitFor(() =>
    expect(manageProject).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'app_old', revision: 4 }),
      'delete',
      'Earlier project',
    ),
  )
})


