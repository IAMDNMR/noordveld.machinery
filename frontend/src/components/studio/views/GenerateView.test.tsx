// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { StudioState, StudioAccess } from '../../../api/studio'
import { getRuntime, launchRuntime, retainRelease } from '../../../api/studio'
import { compileProject, compiledArchiveUrl, type Compilation } from '../../../api/domainKnowledge'
import { emptyDefinition } from '../model/applicationDefinition'
import { GenerateView } from './GenerateView'
import type { ViewProps } from './types'

vi.mock('../../../api/studio', () => ({
  getRuntime: vi.fn(),
  launchRuntime: vi.fn(),
  stopRuntime: vi.fn(),
  testRuntime: vi.fn(),
  getReleases: vi.fn(async () => []),
  retainRelease: vi.fn(),
  liveDemoUrl: (id: string) => `/api/v1/design-studio/projects/${id}/live-demo`,
  releaseArchiveUrl: vi.fn(() => '/saved-release.zip'),
}))
vi.mock('../../../api/studioFrontend', () => ({
  generateFrontend: vi.fn(),
  getFrontendPreview: vi.fn(async () => ({
    html: '<h1>Generated bundle</h1>',
    current: true,
    revision: 1,
    checks: [],
  })),
}))
vi.mock('../../../api/domainKnowledge', () => ({
  compileProject: vi.fn(),
  compiledArchiveUrl: vi.fn(),
  compiledFile: vi.fn(),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function readyProps(): ViewProps {
  const definition = emptyDefinition()
  definition.revision = 1
  definition.generated_frontend = {
    version: 1,
    design_summary: 'An interface written for this project',
    pages: [{ id: 'tasks', title: 'Tasks', purpose: 'Do the work', step_ids: [], entity_ids: [] }],
    files: { 'src/App.tsx': 'export default function App(){return <h1>Tasks</h1>}' },
    input_sha256: 'a'.repeat(64),
    source_sha256: 'b'.repeat(64),
    provider: 'test',
    generated_at: '2026-10-21',
    bundle_js: 'compiled code',
    bundle_css: 'body{}',
    checks: [],
  } as typeof definition.generated_frontend
  const studio = {
    definition,
    revision: 1,
    approval: { process: { state: 'valid' }, design: { state: 'valid' } },
  } as StudioState
  vi.mocked(compileProject).mockResolvedValue({
    status: 'generated',
    manifest: { project_revision: 1 },
    files: {},
    checks: [],
    plan: { reasons: [] },
  } as unknown as Compilation)
  vi.mocked(compiledArchiveUrl).mockReturnValue('/package.zip')
  return {
    studio,
    access: null,
    recent: new Set(),
    busy: false,
    ask: vi.fn(),
    answer: vi.fn(),
    say: vi.fn(),
    act: vi.fn(),
    go: vi.fn(),
    select: vi.fn(),
    selection: null,
    approve: vi.fn(),
    refresh: vi.fn(),
    userName: 'Reviewer',
  }
}

it('offers the saved approved package again when the Generate page is reopened', async () => {
  const props = readyProps()
  vi.mocked(getRuntime).mockResolvedValue({ running: false })
  render(<GenerateView {...props} />)
  expect(
    (await screen.findByRole('link', { name: /Download the application/ })).getAttribute('href'),
  ).toBe('/package.zip')
})

it('automatically retains code when the user generates an application', async () => {
  const props = readyProps()
  vi.mocked(getRuntime).mockResolvedValue({ running: false })
  render(<GenerateView {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Generate again' }))
  await waitFor(() => expect(retainRelease).toHaveBeenCalledWith(props.studio.definition.id, 1))
})

it('allows an authorized reviewer to launch without granting generation access', async () => {
  const props = readyProps()
  props.access = { can: { launch: true, generate: false }, denied: {} } as StudioAccess
  vi.mocked(getRuntime).mockResolvedValue({ running: false })
  vi.mocked(launchRuntime).mockResolvedValue({ running: true })
  render(<GenerateView {...props} />)
  await waitFor(() =>
    expect(
      (screen.getByRole('button', { name: 'Start application' }) as HTMLButtonElement).disabled,
    ).toBe(false),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Start application' }))
  await waitFor(() => expect(launchRuntime).toHaveBeenCalledOnce())
  expect(screen.queryByRole('link', { name: /Download the application/ })).toBeNull()
})

it('opens a browsable demo without a running server or worker service', async () => {
  const props = readyProps()
  vi.mocked(getRuntime).mockResolvedValue({
    running: false,
    available: false,
    reason: 'Separate hosting is required.',
  })
  render(<GenerateView {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'View demo' }))
  const app = await screen.findByTitle('Untitled application generated application')
  expect(decodeURIComponent(app.getAttribute('src') ?? '')).toContain('Generated bundle')
  expect(launchRuntime).not.toHaveBeenCalled()

  // The live demo is a plain link that opens its own tab and never replaces this page.
  const live = screen.getByRole('link', { name: /Open live demo/ })
  expect(live.getAttribute('target')).toBe('_blank')
  expect(live.getAttribute('href')).toContain(
    `/design-studio/projects/${props.studio.definition.id}/live-demo`,
  )
})
