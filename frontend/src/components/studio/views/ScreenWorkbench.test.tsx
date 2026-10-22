// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScreenWorkbench } from './ScreenWorkbench'

// The real preview is a sandboxed page; the workbench only needs its frame and the messages it posts.
vi.mock('./GeneratedFrontendView', async () => {
  const { createElement } = await import('react')
  return {
    GeneratedFrontendView: ({ frameRef }: { frameRef?: React.Ref<HTMLIFrameElement> }) =>
      createElement('iframe', { ref: frameRef, title: 'preview', sandbox: 'allow-scripts' }),
  }
})

const definition = {
  business: {
    roles: [
      { id: 'role_packer', name: 'Packer' },
      { id: 'role_picker', name: 'Picker' },
      { id: 'role_idle', name: 'Idle clerk' },
    ],
    entities: [],
  },
  workflow_definitions: [
    {
      id: 'wf_pack',
      name: 'Pack picked items',
      states: [
        { id: 'st_a', role_id: 'role_packer' },
        { id: 'st_b', role_id: 'role_picker' },
      ],
    },
  ],
} as never

const state = (role: string, page: string, id: string | null, label: string) => ({
  type: 'studio:state',
  role,
  roleName: role === 'role_packer' ? 'Packer' : 'Picker',
  route: { page, id },
  title: label,
  menu: [
    {
      section: '',
      label: 'Control tower',
      target: { page: 'home' },
      count: 0,
      active: page === 'home',
    },
    {
      section: 'Fulfilment',
      label: label || 'Pack picked items',
      target: { page: 'workflow', id: 'wf_pack' },
      count: 2,
      active: page === 'workflow',
    },
  ],
})

function mount(recent: string[] = []) {
  const ask = vi.fn()
  render(<ScreenWorkbench definition={definition} canGenerate recent={new Set(recent)} ask={ask} />)
  const frame = screen.getByTitle('preview') as HTMLIFrameElement
  const post = vi.spyOn(frame.contentWindow!, 'postMessage')
  const report = (data: unknown, source: Window = frame.contentWindow!) =>
    act(() => {
      fireEvent(window, new MessageEvent('message', { data, source }))
    })
  return { ask, frame, post, report }
}

afterEach(cleanup)

describe('ScreenWorkbench', () => {
  it('lists what the preview reports, drives it, and ignores anything else', () => {
    const { ask, post, report } = mount(['st_a'])
    report({ type: 'something-else' })
    report(state('role_packer', 'workflow', 'wf_pack', 'Pack picked items'), window)
    expect(screen.getByText('Loading the screens…')).toBeTruthy()

    report(state('role_packer', 'workflow', 'wf_pack', 'Pack picked items'))
    expect(post).toHaveBeenCalledWith({ type: 'studio:layout', embedded: true }, '*')
    // A step of this process changed in the last assistant turn: the entry says so instead of showing a count.
    expect(screen.getByRole('button', { name: /Pack picked items\s*Updated/ })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Idle clerk (no steps yet)' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Control tower' }))
    expect(post).toHaveBeenCalledWith({ type: 'studio:go', route: { page: 'home' } }, '*')
    fireEvent.change(screen.getByLabelText('View the application as'), {
      target: { value: 'role_picker' },
    })
    expect(post).toHaveBeenCalledWith(
      { type: 'studio:go', role: 'role_picker', route: { page: 'home' } },
      '*',
    )
    fireEvent.click(screen.getByRole('button', { name: /Ask the assistant/ }))
    expect(ask).toHaveBeenCalledWith('Change the “Pack picked items” screen for Packer: ')
  })

  it('returns a reloaded preview to the role and screen the person was on', () => {
    const { frame, post, report } = mount()
    report(state('role_packer', 'home', null, 'Control tower'))
    report(state('role_picker', 'workflow', 'wf_pack', 'Pack picked items'))
    post.mockClear()
    // The design changed: the preview is a new document that starts on the default role and its home screen.
    const next = { postMessage: vi.fn() } as unknown as Window
    Object.defineProperty(frame, 'contentWindow', { configurable: true, value: next })
    report(state('role_packer', 'home', null, 'Control tower'), next)
    expect(next.postMessage).toHaveBeenCalledWith(
      { type: 'studio:go', role: 'role_picker', route: { page: 'workflow', id: 'wf_pack' } },
      '*',
    )
  })
})
