// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { SparkHome } from './SparkHome'
import { conversationDateGroup } from './ChatSidebar'
import type { SparkResponse } from '../../api/spark'

const response = (message: string, context = 'signed-context'): SparkResponse => ({
  message,
  context,
  view: 'answer',
  intelligence: null,
  shopping: null,
  account: null,
  sign_in_required: false,
  warnings: [],
  steps: [{ label: 'Understood your request', status: 'completed', ms: 3 }],
})
function CurrentLocation() {
  const location = useLocation()
  return (
    <output hidden data-testid="current-location">
      {location.pathname}
      {location.search}
    </output>
  )
}
const mount = (
  answer: (body: Record<string, unknown>) => Response | Promise<Response>,
  entry = '/spark/chat',
  voiceEnabled = false,
  voiceMode?: 'hands_free' | 'dictate',
) => {
  const calls: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/spark/voice/status'))
        return new Response(
          JSON.stringify({ enabled: voiceEnabled, reason: 'Voice unavailable', mode: voiceMode }),
        )
      if (url.endsWith('/spark/voice/speak')) return new Response(new Blob(['mp3']))
      if (url.endsWith('/spark/voice/transcribe'))
        return new Response(JSON.stringify({ text: 'Find an air filter', confidence: 0.96 }))
      if (url.endsWith('/spark/conversation')) {
        const body = JSON.parse(String(init?.body))
        calls.push(body)
        return answer(body)
      }
      return new Response('{}', { status: 404 })
    }),
  )
  render(
    <MemoryRouter initialEntries={[entry]}>
      <SparkHome />
      <CurrentLocation />
    </MemoryRouter>,
  )
  return calls
}
const send = (text: string) => {
  fireEvent.change(screen.getByRole('textbox', { name: 'Message Spark' }), {
    target: { value: text },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
}
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  Element.prototype.scrollTo = vi.fn()
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function () {
    this.open = false
  }
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('uses one natural-language conversation and carries a clarification answer into the same task', async () => {
  let reply: (value: Response) => void = () => {}
  const secondReply = new Promise<Response>((resolve) => {
    reply = resolve
  })
  let attempt = 0
  const calls = mount(() =>
    ++attempt === 1
      ? new Response(JSON.stringify(response('Which machine do you mean?')))
      : attempt === 2
        ? secondReply
        : new Response(JSON.stringify(response('Another answer.'))),
  )
  const today = new Date(2026, 9, 27, 12).getTime()
  expect(conversationDateGroup(today, today)).toBe('Today')
  expect(conversationDateGroup(new Date(2026, 9, 26, 22).getTime(), today)).toBe('Yesterday')
  expect(conversationDateGroup(new Date(2026, 9, 23).getTime(), today)).toBe('Previous 7 days')
  expect(conversationDateGroup(new Date(2026, 9, 1).getTime(), today)).toBe('Earlier')
  expect(screen.queryByRole('radio')).toBeNull()
  expect(screen.queryByText('Find buying options')).toBeNull()
  send('supllies for that part pls')
  expect(await screen.findByText('Which machine do you mean?')).toBeTruthy()
  send('The loader we discussed')
  await waitFor(() => expect(calls).toHaveLength(2))
  expect(screen.getByRole('heading', { name: 'The loader we discussed' })).toBeTruthy()
  expect(screen.getByText('Spark is working on your request…').getAttribute('role')).toBe('status')
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('')
  reply(new Response(JSON.stringify(response('I found the loader.'))))
  expect(await screen.findByText('I found the loader.')).toBeTruthy()
  expect(screen.getAllByRole('heading', { name: 'The loader we discussed' })).toHaveLength(1)
  expect(calls[0]).toMatchObject({ message: 'supllies for that part pls', context: null })
  expect(calls[1]).toMatchObject({ message: 'The loader we discussed', context: 'signed-context' })
  expect(screen.getByRole('heading', { name: 'supllies for that part pls' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'About Spark' }).getAttribute('href')).toBe('/spark')
  const copy = vi.fn(async () => {})
  vi.stubGlobal('navigator', { clipboard: { writeText: copy } })
  fireEvent.click(screen.getAllByRole('button', { name: 'Copy answer' }).at(-1)!)
  await waitFor(() => expect(copy).toHaveBeenCalledWith('I found the loader.'))
  fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
  expect(screen.queryByText('I found the loader.')).toBeNull()
  send('Another topic')
  await screen.findByText('Another answer.')
  fireEvent.change(screen.getByRole('textbox', { name: 'Message Spark' }), {
    target: { value: 'An unsent draft' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'supllies for that part pls' }))
  expect(screen.getByText('Which machine do you mean?')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Rename supllies for that part pls' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Chat title' }), {
    target: { value: 'Loader supplies' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save name' }))
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search conversations' }), {
    target: { value: 'Another topic' },
  })
  expect(screen.queryByRole('button', { name: 'Loader supplies' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Another topic' }))
  expect(
    (screen.getByRole('textbox', { name: 'Message Spark' }) as HTMLTextAreaElement).value,
  ).toBe('An unsent draft')
  fireEvent.click(screen.getByRole('button', { name: 'Delete Another topic' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete chat' }))
  expect(screen.queryByRole('button', { name: 'Another topic' })).toBeNull()
})

it('keeps evidence graphs and shopping process results together in the conversation', async () => {
  const result = response('')
  result.view = 'graph'
  result.intelligence = {
    question: 'What fits?',
    intent: 'PART_TO_MACHINE',
    intent_label: 'Machine fitment',
    understood_by: 'llm',
    entities: [],
    answer: {
      summary: 'This part fits the recorded machine.',
      grounded: true,
      source: 'template',
      demo: false,
    },
    results: [],
    total: 0,
    evidence: [
      {
        entity: 'Part A',
        entity_kind: 'PART',
        relationship: 'FITS',
        target: 'Machine A',
        target_kind: 'MACHINE',
        data_class: 'REAL',
      },
    ],
    provenance: [],
    graph_path: [],
    warnings: [],
    actions: [],
    clarification: null,
    scope: 'IN_SCOPE',
    stages: [],
    elapsed_ms: 4,
  }
  result.shopping = {
    request: 'find a replacement',
    state: 'need_machine',
    interpretation: {
      machine: null,
      part_type: null,
      preference: 'none',
      delivery_place: null,
      quantity: null,
      budget_max: null,
      budget_currency: null,
      availability: 'none',
    },
    steps: [
      {
        key: 'fitment',
        label: 'Checking fitment',
        status: 'done',
        message: 'Checked the recorded fitment.',
      },
    ],
    question: 'Which machine do you need the replacement for?',
    options: [],
    candidates: [],
    recommended: null,
    reason: null,
    evidence: [],
    comparison: null,
    excluded: [],
    delivery: null,
    decision: null,
    why: [],
    how_we_know: [],
    notes: [],
    commerce_domains: [],
    disclaimer: 'Demo data.',
  }
  mount(() => new Response(JSON.stringify(result)))
  send('show connections and find replacement')
  expect(await screen.findByText('This part fits the recorded machine.')).toBeTruthy()
  expect(screen.getByText('Which machine do you need the replacement for?')).toBeTruthy()
  const graph = document.querySelector('details.gx-answer') as HTMLDetailsElement
  expect(graph.open).toBe(true)
  expect(screen.getByText(/Checked the recorded fitment/)).toBeTruthy()
  expect(screen.queryByText('Understood as')).toBeNull()
  await waitFor(() =>
    expect(
      JSON.parse(sessionStorage.getItem('noordveld-spark-session:anonymous') ?? '[]')[0]?.response
        ?.shopping,
    ).toBeTruthy(),
  )
  const saved = sessionStorage.getItem('noordveld-spark-session:anonymous')
  cleanup()
  sessionStorage.setItem('noordveld-spark-session:anonymous', saved!)
  const replay = mount(() => new Response(JSON.stringify(response('should not rerun'))))
  expect(screen.getByText('This part fits the recorded machine.')).toBeTruthy()
  expect((document.querySelector('details.gx-answer') as HTMLDetailsElement).open).toBe(true)
  expect(screen.getByText('Which machine do you need the replacement for?')).toBeTruthy()
  expect(replay).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Open full screen graph' }))
  expect(screen.getByRole('dialog', { name: 'Full screen relationships' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Close full screen graph' }))
  const thread = screen.getByRole('region', { name: 'Conversation with Spark' })
  Object.defineProperties(thread, {
    scrollHeight: { value: 2400, configurable: true },
    clientHeight: { value: 500, configurable: true },
    scrollTop: { value: 0, configurable: true, writable: true },
  })
  fireEvent.scroll(thread)
  expect(screen.getByRole('button', { name: 'Latest messages' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Latest messages' }))
  expect(screen.queryByRole('button', { name: 'Latest messages' })).toBeNull()
})

it('keeps a failed request editable, retries honestly and never requests microphone access automatically', async () => {
  let attempt = 0
  const calls = mount(() =>
    ++attempt === 1
      ? new Response(
          JSON.stringify({
            error: { code: 'llm_unavailable', message: 'Language service unavailable' },
          }),
          { status: 503 },
        )
      : new Response(JSON.stringify(response('Which part?'))),
  )
  send('show suppliers')
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'show suppliers' })).toBeTruthy()
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('show suppliers')
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Which part?')).toBeTruthy()
  expect(calls).toHaveLength(2)
  expect(calls[0].context).toBe(calls[1].context)
  expect(
    (screen.getByRole('button', { name: 'Speak to Spark' }) as HTMLButtonElement).disabled,
  ).toBe(true)
  expect(document.querySelector('video')).toBeNull()
})

it('does not ask a bookmarked question again when the conversation was restored', async () => {
  sessionStorage.setItem(
    'noordveld-spark-session:anonymous',
    JSON.stringify([
      { id: 1, question: 'Who supplies NVM-1090-HY', summary: 'Two suppliers', context: 'c1' },
      { id: 2, question: 'show that in a graph', summary: 'A graph', context: 'c2' },
    ]),
  )
  const calls = mount(
    () => new Response(JSON.stringify(response('asked again'))),
    '/spark/chat?q=who%20supplies%20nvm-1090-hy',
  )
  expect(await screen.findByText('Two suppliers')).toBeTruthy()
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(calls).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
  expect(screen.getByTestId('current-location').textContent).toBe('/spark/chat')
  expect(sessionStorage.getItem('noordveld-spark-session:anonymous')).not.toBeNull()
  expect(screen.queryByText('Two suppliers')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Who supplies NVM-1090-HY' }))
  expect(screen.getByText('Two suppliers')).toBeTruthy()
})

it('keeps the allowed answer visible and explains restricted feature access without asking for sign-in', async () => {
  const result = response('Your permitted answer remains available.')
  result.message +=
    '\n\n| Part | Units |\n| --- | --- |\n| Filter | 8 |\n\n**Recorded stock**\n\n```text\nNo invented figures\n```'
  result.steps.push({ label: 'Shopping access required', status: 'access_denied', ms: 0 })
  result.warnings.push('Shopping: Ask your organization administrator for access.')
  mount(() => new Response(JSON.stringify(result)))
  send('Explain this part and compare buying options')
  expect(await screen.findByText('Your permitted answer remains available.')).toBeTruthy()
  expect(screen.getByRole('table', { name: 'Answer table' })).toBeTruthy()
  expect(screen.getByRole('columnheader', { name: 'Units' })).toBeTruthy()
  expect(screen.getByText('Recorded stock').tagName).toBe('STRONG')
  expect(screen.getByText('No invented figures').tagName).toBe('CODE')
  expect(screen.getByText(/Shopping access required.*Access needed/)).toBeTruthy()
  expect(screen.getByText('Shopping: Ask your organization administrator for access.')).toBeTruthy()
  expect(screen.queryByText('Sign in needed')).toBeNull()
})

it('preserves the unsent question when restarting an expired conversation', async () => {
  mount(
    () =>
      new Response(
        JSON.stringify({
          error: { code: 'spark_context_expired', message: 'Conversation expired' },
        }),
        { status: 409 },
      ),
  )
  send('nvm 1010 at ki dealers evaru?')
  fireEvent.click(await screen.findByRole('button', { name: 'Start a new conversation' }))
  expect(
    (screen.getByRole('textbox', { name: 'Message Spark' }) as HTMLTextAreaElement).value,
  ).toBe('nvm 1010 at ki dealers evaru?')
  expect(screen.queryByRole('alert')).toBeNull()
  cleanup()
  const stopTrack = vi.fn()
  vi.stubGlobal('navigator', {
    mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) },
  })
  vi.stubGlobal(
    'MediaRecorder',
    class {
      static isTypeSupported() {
        return true
      }
      state = 'inactive'
      mimeType = 'audio/webm'
      ondataavailable: ((event: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      start() {
        this.state = 'recording'
      }
      stop() {
        this.state = 'inactive'
        this.ondataavailable?.({ data: new Blob(['x'.repeat(1200)]) })
        this.onstop?.()
      }
    },
  )
  vi.stubGlobal(
    'AudioContext',
    class {
      state = 'running'
      close = async () => {}
      createAnalyser = () => ({
        fftSize: 1024,
        getByteTimeDomainData: (data: Uint8Array) => data.fill(160),
      })
      createMediaStreamSource = () => ({ connect: () => {} })
    },
  )
  const calls = mount(
    () => new Response(JSON.stringify(response('Recorded question answered.'))),
    '/spark/chat',
    true,
  )
  await waitFor(() =>
    expect(
      (screen.getByRole('button', { name: 'Speak to Spark' }) as HTMLButtonElement).disabled,
    ).toBe(false),
  )
  expect(
    screen.getByRole('button', { name: 'Read replies aloud' }).getAttribute('aria-pressed'),
  ).toBe('false')
  fireEvent.click(screen.getByRole('button', { name: 'Speak to Spark' }))
  await screen.findByRole('button', { name: 'Stop recording' })
  await new Promise((resolve) => setTimeout(resolve, 100))
  fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
  await screen.findByText('Question recorded. Review it, then press Send.')
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Find an air filter')
  expect(calls).toHaveLength(0)
  expect(stopTrack).toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  await screen.findByText('Recorded question answered.')
  expect(
    vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/spark/voice/speak')),
  ).toBe(false)

  // hands-free (the default server mode): speaking sends the message into the same conversation and the reply is spoken;
  // a typed message in that conversation stays silent
  cleanup()
  sessionStorage.clear()
  const spokenCalls = mount(
    (body) => new Response(JSON.stringify(response(`Answer to ${String(body.message)}`))),
    '/spark/chat',
    true,
    'hands_free',
  )
  const spoke = () =>
    vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/spark/voice/speak')).length
  await waitFor(() =>
    expect(
      (screen.getByRole('button', { name: 'Speak to Spark' }) as HTMLButtonElement).disabled,
    ).toBe(false),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Speak to Spark' }))
  await screen.findByRole('button', { name: 'Stop recording' })
  await new Promise((resolve) => setTimeout(resolve, 100))
  fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
  await screen.findByText('Answer to Find an air filter') // no Send press needed
  expect(screen.getByLabelText('Spoken')).toBeTruthy()
  await waitFor(() => expect(spoke()).toBe(1))
  send('And the price?')
  await screen.findByText('Answer to And the price?')
  expect(spokenCalls.map((call) => call.message)).toEqual(['Find an air filter', 'And the price?'])
  expect(spokenCalls[1].context).toBe('signed-context') // one conversation: the typed turn continues the spoken one
  expect(spoke()).toBe(1)
}, 15_000)

it('shows text by default and a table or chart only when the server chose one, falling back to text', async () => {
  const records = ['Depot One', 'Depot Two', 'Depot Three'].map((title, n) => ({
    kind: 'warehouse',
    key: title,
    title,
    subtitle: null,
    part_number: null,
    relationship: null,
    data_class: 'DEMO',
    facts: [{ label: 'Units recorded', value: String(n + 1) }],
    groups: [],
  }))
  const intelligence = {
    question: 'q',
    intent: 'PART_TO_LOCATION',
    intent_label: 'Where',
    understood_by: 'llm',
    entities: [],
    subject: null,
    answer: { summary: 'Three depots hold it.', grounded: true, source: 'template', demo: false },
    results: records,
    total: 3,
    evidence: [],
    provenance: [],
    graph_path: [],
    warnings: [],
    actions: [],
    clarification: null,
  }
  const table = {
    columns: ['Location', 'Units recorded'],
    rows: records.map((r, n) => ({
      key: r.key,
      title: r.title,
      part_number: null,
      cells: [String(n + 1)],
    })),
  }
  const shown = (presentation: Record<string, unknown> | undefined) =>
    new Response(
      JSON.stringify({
        ...response(''),
        intelligence,
        presentation: presentation && {
          shopping: null,
          account: null,
          note: null,
          chart: null,
          table: null,
          ...presentation,
        },
      }),
    )
  const replies = [
    shown({ intelligence: 'text', table }),
    shown({ intelligence: 'table', table }),
    shown({
      intelligence: 'chart',
      chart: {
        metric: 'Units recorded',
        rows: [
          { name: 'Depot One', value: 1 },
          { name: 'Depot Two', value: 2 },
        ],
      },
    }),
    shown({ intelligence: 'table', table: { columns: ['Location'], rows: 'broken' } }),
  ]
  mount(() => replies.shift()!)
  send('Where is it?')
  const disclosure = (await screen.findByText('Show the 3 records')).closest('details')!
  expect(disclosure.open).toBe(false) // the sentence is the answer; the records stay one click away
  expect(screen.queryByRole('region', { name: 'Answer records' })?.closest('details')).toBe(
    disclosure,
  )
  send('Compare them')
  await waitFor(() => expect(screen.getAllByText('Three depots hold it.')).toHaveLength(2))
  const tables = screen.getAllByRole('region', { name: 'Answer records' })
  expect(tables.at(-1)!.closest('details')).toBeNull()
  expect(tables.at(-1)!.querySelectorAll('tbody tr')).toHaveLength(3)
  send('Chart the stock')
  expect(await screen.findByText('Units recorded', { selector: 'figcaption' })).toBeTruthy()
  send('Again')
  await waitFor(() => expect(screen.getAllByText('Three depots hold it.')).toHaveLength(4))
  // a malformed table becomes text with the records behind a disclosure, never a broken table
  expect(screen.getAllByText('Show the 3 records')).toHaveLength(3)
})
