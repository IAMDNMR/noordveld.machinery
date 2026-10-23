// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { emptyDefinition } from '../model/applicationDefinition'
import { GeneratedFrontendView } from './GeneratedFrontendView'
import {
  generateFrontend,
  getFrontendPreview,
  getFrontendProgress,
} from '../../../api/studioFrontend'
import { ApiError } from '../../../api/client'

vi.mock('../../../api/studioFrontend', () => ({
  generateFrontend: vi.fn(),
  getFrontendPreview: vi.fn().mockResolvedValue({
    html: '<h1>Draft</h1>',
    current: true,
    revision: 4,
    checks: [],
    kind: 'baseline',
  }),
  getFrontendProgress: vi.fn().mockResolvedValue({ progress: null }),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('shows recovery guidance with compiler diagnostics collapsed separately', async () => {
  vi.mocked(generateFrontend).mockRejectedValue(
    new ApiError(
      422,
      'frontend_build_failed',
      'The interface did not pass its code or browser checks.',
      { diagnostics: 'src/ui.tsx: invalid JSX on line 615' },
    ),
  )
  render(
    <GeneratedFrontendView
      definition={{ ...emptyDefinition(), frontend_required: true, revision: 4 }}
      refresh={vi.fn()}
    />,
  )
  fireEvent.click(await screen.findByRole('button', { name: 'Create tailored interface' }))
  expect(await screen.findByRole('alert')).toHaveProperty(
    'textContent',
    'The interface did not pass its code or browser checks.',
  )
  const summary = screen.getByText('Technical details')
  expect(summary.closest('details')?.open).toBe(false)
  expect(screen.getByText('src/ui.tsx: invalid JSX on line 615')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Retry generation' }).hasAttribute('disabled')).toBe(
    false,
  )
})

function project() {
  return {
    ...emptyDefinition(),
    revision: 4,
    generated_frontend: {
      version: 1,
      design_summary: 'An application written for this project',
      pages: [
        {
          id: 'orders',
          title: 'Purchasing',
          purpose: 'Manage orders',
          step_ids: [],
          entity_ids: [],
        },
      ],
      files: { 'src/App.tsx': 'export default function App(){return <h1>Purchasing</h1>}' },
      input_sha256: 'a'.repeat(64),
      source_sha256: 'b'.repeat(64),
      provider: 'test',
      generated_at: '2026-10-21',
      bundle_js: 'compiled code',
      bundle_css: 'body{}',
      checks: ['TypeScript strict check passes'],
    },
  }
}

it('isolates actual generated code and exposes source as text', async () => {
  vi.mocked(getFrontendPreview).mockResolvedValue({
    html: '<h1>Actual bundle preview</h1>',
    kind: 'generated',
    current: true,
    revision: 4,
    checks: [],
  })
  render(
    <GeneratedFrontendView
      definition={project()}
      refresh={vi.fn()}
      fullScreenHref="/api/v1/design-studio/projects/p/live-demo"
    />,
  )
  const iframe = await screen.findByTitle('Untitled application generated application')
  // "Full screen" is a link that opens the application in its own tab, rebuilt from the saved design at every load.
  const full = screen.getByRole('link', { name: /Full screen/ })
  expect(full.getAttribute('href')).toBe('/api/v1/design-studio/projects/p/live-demo')
  expect(full.getAttribute('target')).toBe('_blank')
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.queryByText('Design your application')).toBeNull()
  expect(generateFrontend).not.toHaveBeenCalled()
  expect(iframe.getAttribute('sandbox')).toBe('allow-scripts')
  expect(decodeURIComponent(iframe.getAttribute('src') ?? '')).toContain('Actual bundle preview')
  fireEvent.click(screen.getByRole('button', { name: 'View source' }))
  expect(screen.getByText(project().generated_frontend.files['src/App.tsx'])).toBeTruthy()
})

it('never starts a model job on entering Screens and retries only when requested after failure', async () => {
  vi.mocked(generateFrontend).mockRejectedValue(new Error('Build failed; draft retained.'))
  const definition = { ...emptyDefinition(), revision: 4, frontend_required: true }
  const refresh = vi.fn()
  const view = render(<GeneratedFrontendView definition={definition} refresh={refresh} />)
  await screen.findByTitle('Untitled application generated application')
  expect(generateFrontend).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Create tailored interface' }))
  await screen.findByText('Build failed; draft retained.')
  expect(generateFrontend).toHaveBeenCalledTimes(1)
  view.rerender(<GeneratedFrontendView definition={definition} refresh={vi.fn()} />)
  expect(generateFrontend).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('textbox')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry generation' }))
  await waitFor(() => expect(generateFrontend).toHaveBeenCalledTimes(2))
})

it('does not automatically retry a failed server job after reopening the project', async () => {
  vi.mocked(getFrontendProgress).mockResolvedValueOnce({
    progress: null,
    result: { status: 'failed', revision: 4, message: 'Plan incomplete; draft saved.' },
  })
  render(
    <GeneratedFrontendView
      definition={{ ...emptyDefinition(), revision: 4, frontend_required: true }}
      refresh={vi.fn()}
    />,
  )
  await screen.findByText('Plan incomplete; draft saved.')
  expect(generateFrontend).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Retry generation' })).toBeTruthy()
})

it('never starts generation for a viewer or a preview dialog', async () => {
  const definition = { ...emptyDefinition(), revision: 4, frontend_required: true }
  const view = render(
    <GeneratedFrontendView definition={definition} refresh={vi.fn()} canGenerate={false} />,
  )
  await screen.findByTitle('Untitled application generated application')
  view.rerender(<GeneratedFrontendView definition={definition} refresh={vi.fn()} previewOnly />)
  expect(generateFrontend).not.toHaveBeenCalled()
})

it('uses conversational design instructions once and keeps them scoped to their project', async () => {
  vi.mocked(generateFrontend).mockResolvedValue({ definition: project(), checks: [] })
  const handled = vi.fn()
  const refresh = vi.fn()
  const view = render(
    <GeneratedFrontendView
      definition={project()}
      refresh={refresh}
      designRequest={{ id: 1, projectId: 'another_project', brief: 'Navy theme' }}
      onDesignRequestHandled={handled}
    />,
  )
  await screen.findByTitle('Untitled application generated application')
  expect(generateFrontend).not.toHaveBeenCalled()
  view.rerender(
    <GeneratedFrontendView
      definition={project()}
      refresh={refresh}
      designRequest={{ id: 2, projectId: 'app_pixels', brief: 'Navy theme' }}
      onDesignRequestHandled={handled}
    />,
  )
  await waitFor(() => expect(generateFrontend).toHaveBeenCalledWith('app_pixels', 4, 'Navy theme'))
  expect(handled).toHaveBeenCalledTimes(1)
  view.rerender(
    <GeneratedFrontendView
      definition={project()}
      refresh={refresh}
      designRequest={null}
      onDesignRequestHandled={handled}
    />,
  )
  expect(generateFrontend).toHaveBeenCalledTimes(1)
})

it('keeps the saved interface visible when regeneration fails', async () => {
  vi.mocked(getFrontendPreview).mockResolvedValue({
    html: '<h1>Saved</h1>',
    kind: 'generated',
    current: true,
    revision: 4,
    checks: [],
  })
  vi.mocked(generateFrontend).mockRejectedValue(new Error('Generated source failed its build.'))
  const refresh = vi.fn()
  render(<GeneratedFrontendView definition={project()} refresh={refresh} />)
  await screen.findByTitle('Untitled application generated application')
  fireEvent.click(screen.getByRole('button', { name: 'Rebuild interface' }))
  expect(await screen.findByRole('alert')).toHaveProperty(
    'textContent',
    'Generated source failed its build.',
  )
  expect(screen.getByTitle('Untitled application generated application')).toBeTruthy()
  expect(refresh).not.toHaveBeenCalled()
  expect(generateFrontend).toHaveBeenCalledWith('app_pixels', 4, '')
})

it('marks stale source and refreshes after a successful generation', async () => {
  vi.mocked(getFrontendPreview).mockResolvedValue({
    html: '<h1>Saved</h1>',
    kind: 'generated',
    current: false,
    revision: 4,
    checks: [],
  })
  vi.mocked(generateFrontend).mockResolvedValue({ definition: project(), checks: [] })
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<GeneratedFrontendView definition={project()} refresh={refresh} />)
  await screen.findByText(/process or data model has changed/)
  expect(screen.queryByTitle('Untitled application generated application')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Update application' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
})
