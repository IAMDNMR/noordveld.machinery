// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { getReleases, type StudioRelease } from '../../../api/studio'
import { ReleaseHistory } from './ReleaseHistory'

vi.mock('../../../api/studio', () => ({
  getReleases: vi.fn(),
  retainRelease: vi.fn(),
  releaseArchiveUrl: vi.fn(() => '/retained.zip'),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
const release = {
  id: 'current-package',
  revision: 12,
  created: '2026-10-20T10:00:00Z',
  actor: 'owner',
  archive_sha256: 'abc',
  tests: [
    {
      id: 'run',
      status: 'partial',
      started: '2026-10-20T10:00:00Z',
      result: {
        revision: 12,
        passed: true,
        ran: 50,
        passed_count: 43,
        skipped_count: 7,
        cases: [],
        output_tail: '',
        seconds: 1,
      },
    },
  ],
} as StudioRelease

it('restores tests only for the exact compiled package, not a different generation of the same revision', async () => {
  vi.mocked(getReleases).mockResolvedValue([release])
  const restore = vi.fn()
  const props = {
    projectId: 'project',
    revision: 12,
    canGenerate: true,
    changed: 0,
    onRestoreTests: restore,
  }
  const view = render(<ReleaseHistory {...props} packageHash="different-package" />)
  await screen.findByText(/Revision 12/)
  expect(restore).not.toHaveBeenCalled()
  view.rerender(<ReleaseHistory {...props} packageHash="current-package" />)
  await waitFor(() => expect(restore).toHaveBeenCalledWith(release.tests[0].result))
  expect(
    screen.getByRole('link', { name: 'Download saved release', hidden: true }).getAttribute('href'),
  ).toBe('/retained.zip')
})


