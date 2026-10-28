// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

const Where = () => {
  const { pathname, search } = useLocation()
  return <output aria-label="location">{pathname + search}</output>
}
const open = async (entry: string) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/spark/voice/status')
        ? new Response(JSON.stringify({ enabled: false, reason: '' }))
        : new Response('{}', { status: 401 }),
    ),
  )
  render(
    <MemoryRouter initialEntries={[entry]}>
      <App />
      <Where />
    </MemoryRouter>,
  )
}
beforeEach(() => {
  Element.prototype.scrollTo = vi.fn()
  window.scrollTo = vi.fn()
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('keeps every earlier Spark address working', async () => {
  for (const [from, to] of [
    ['/agentic-shopping?q=find%20a%20filter', '/spark/chat?q=find%20a%20filter'],
    ['/parts-intelligence?part=NVM-1020-FL&tab=graph', '/spark/chat?part=NVM-1020-FL&tab=graph'],
    ['/spark?q=who%20supplies%20it', '/spark/chat?q=who+supplies+it'],
    ['/agentic-commerce/?q=compare%20these', '/spark/chat?q=compare+these'],
    ['/agentic-commerce/', '/spark'],
  ]) {
    await open(from)
    await waitFor(() => expect(screen.getByLabelText('location').textContent).toBe(to))
    cleanup()
  }
})

it('opens the conversation with the question asked on the introduction page', async () => {
  await open('/spark')
  fireEvent.change(await screen.findByLabelText('Your question for Spark'), {
    target: { value: 'Which machines does it fit?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Ask Spark' }))
  await waitFor(() =>
    expect(screen.getByLabelText('location').textContent).toBe(
      '/spark/chat?q=Which+machines+does+it+fit%3F',
    ),
  )
})
