// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentResponse } from '../../api/agent'
import type { PartSummary } from '../../api/index'
import AgenticShoppingPage from '../../pages/AgenticShoppingPage'
import { SessionProvider } from '../../store/session'

const part = (
  id: string,
  no: string,
  status: string,
  orderable: boolean,
  amount: number,
  state = 'IN_STOCK',
): PartSummary => ({
  part_id: id,
  part_number: no,
  name: `Part ${no}`,
  category: 'Hydraulics',
  subcategory: 'Hose',
  fitment: [{ model_code: 'M-1', fitment_status: 'CONFIRMED' }],
  price: { amount, currency: 'EUR', data_status: 'SYNTHETIC_DEMO' },
  availability: {
    state,
    orderable,
    part_status: status,
    total_available: 5,
    data_status: 'SYNTHETIC_DEMO',
  },
})
const KEYS = [
  'request',
  'understand',
  'machine',
  'part',
  'fitment',
  'availability',
  'fulfilment',
  'compare',
  'recommend',
] as const
const steps = (blockedAt = -1): AgentResponse['steps'] =>
  KEYS.map((key, i) => ({
    key,
    label: `Label ${key}`,
    message: `msg ${key}`,
    status: i === blockedAt ? 'blocked' : blockedAt >= 0 && i > blockedAt ? 'skipped' : 'done',
  }))
const base: Omit<AgentResponse, 'state' | 'steps'> = {
  request: 'r',
  commerce_domains: [],
  interpretation: {
    machine: 'M-1',
    part_type: 'Hose',
    preference: 'cheapest',
    delivery_place: null,
    quantity: null,
    budget_max: 800,
    budget_currency: 'EUR',
    availability: 'none',
  },
  question: null,
  options: [],
  candidates: [],
  recommended: null,
  reason: null,
  evidence: [],
  comparison: null,
  excluded: [],
  delivery: null,
  notes: [],
  disclaimer: 'Demo data disclaimer.',
  decision: null,
  why: [],
  how_we_know: [],
}
const fields = {
  fitment_label: 'Confirmed fit',
  stock_locations: [],
  suppliers: [],
  price_basis: 'ex VAT',
  order_action: 'add_to_cart' as const,
  order_note: null,
}
const recommendation: AgentResponse = {
  ...base,
  state: 'recommendation',
  steps: steps(),
  recommended: 'AB-1',
  candidates: [
    {
      ...fields,
      part: part('P1', 'AB-1', 'VERIFIED', true, 10),
      recommended: true,
      availability_label: 'In stock',
      fitment_status: 'CONFIRMED',
      inventory: '5 units across 2 warehouses',
      stock_locations: [
        { warehouse: 'North depot', city: 'Northtown', available: 3 },
        { warehouse: 'South depot', city: 'Southtown', available: 2 },
      ],
      fulfilment: 'Available from connected stock (2 warehouses)',
      delivery: 'Estimate not recorded',
      supplier_label: 'Supplier One (demo)',
      suppliers: [{ name: 'Supplier One (demo)', lead_time_days: 7, primary: true }],
      supplier: 'Supplier One (demo)',
      supplier_lead_days: 7,
      fulfilment_days: null,
      within_budget: true,
      tradeoffs: [],
      can_add_to_cart: true,
    },
    {
      ...fields,
      part: part('P2', 'AB-2', 'VERIFIED', true, 20, 'BACKORDER'),
      recommended: false,
      availability_label: 'On order',
      fitment_status: 'CONFIRMED',
      inventory: '0 units in stock',
      fulfilment: 'Supplier lead time · 10 days',
      delivery: 'Estimate not recorded',
      supplier_label: 'Supplier Two (demo) · lead time 10 days',
      order_note: 'On order: supplied after the supplier lead time (10 days)',
      supplier: 'Supplier Two (demo)',
      supplier_lead_days: 10,
      fulfilment_days: 10,
      within_budget: true,
      tradeoffs: ['Higher price', 'Lower availability'],
      can_add_to_cart: true,
    },
  ],
  decision: {
    requirements: ['Confirmed fit for the M-1', 'Verified part', 'Within your €800 budget'],
    priorities: ['Lowest price', 'Availability'],
    summary: 'AB-1 ranked first because it is confirmed compatible and it is currently in stock.',
  },
  why: [
    { title: 'Confirmed compatibility', detail: 'Fits the M-1 (catalogue fitment).' },
    { title: 'Lower price', detail: '€10 compared with €20 (AB-2).' },
    {
      title: 'Your priority',
      detail: 'You asked for the cheapest option, so the lowest valid price came first.',
    },
  ],
  how_we_know: [
    { label: 'Fitment', value: 'Noordveld catalogue · confirmed fit' },
    { label: 'Inventory', value: 'Synthetic demo inventory' },
  ],
  reason: 'Recommended because it is recorded as fitting the M-1.',
  comparison: 'Compared with AB-2.',
  evidence: [
    {
      key: 'fit',
      ok: true,
      label: 'Fits the M-1',
      detail: 'Catalogue fitment',
      data_class: 'SOURCE_DERIVED',
    },
    {
      key: 'supplier',
      ok: false,
      label: 'No supplier relationship',
      detail: 'None recorded',
      data_class: null,
    },
  ],
  excluded: [{ part_number: 'AB-9', name: 'x', status_label: 'Identification required' }],
}
const SUGGESTIONS = [
  {
    request: 'I need a hose for my M-1, preferably in stock.',
    need: 'Hose',
    context: 'M-1',
    action: 'Prefer in stock',
  },
]
const CATALOG = [
  { category: 'Find a part', note: null, questions: ['I need a hose for my M-1.'] },
  { category: 'Orders', note: 'Sign in for these.', questions: ['Where is my order?'] },
]

// the commerce assistant's answer for the same request, as the Commerce Agent API returns it (only what the panel reads)
const commerceAnswer = (domain: 'LOGISTICS' | 'WARRANTY', headline: string) => ({
  intent: domain,
  status: 'ANSWERED',
  steps: [],
  clarification: null,
  evidence: [],
  evidence_paths: {},
  source_records: [],
  data_status: 'SYNTHETIC_DEMO',
  confidence: {},
  visibility: {},
  warnings: [],
  missing: [],
  state: {},
  understanding: {
    intent: domain,
    domains: [domain],
    source: 'RULES',
    focus: [],
    references: {},
    reasons: [],
  },
  contexts: {},
  answer: {
    text: `Part answer. ${headline}`,
    lead: `Part answer. ${headline}`,
    synthetic_notice: null,
    grounding: { mode: 'TEMPLATE', validated: true },
    sections: [
      {
        domain: 'DISCOVERY',
        title: 'Part discovery',
        status: 'SUCCESS',
        decision: 'RECOMMEND',
        headline: 'Part answer.',
        lines: [],
        notes: [],
      },
      { domain, title: domain, status: 'SUCCESS', decision: 'X', headline, lines: [], notes: [] },
    ],
  },
})

let commerceCalls: string[] = []
function mount(
  response: ((request: string) => AgentResponse) | { status: number; code: string },
  q: string | null = 'I need a hose',
  session: { signedIn?: boolean; commerce?: unknown } = {},
) {
  const calls: string[] = []
  commerceCalls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/me'))
        return session.signedIn
          ? new Response(
              JSON.stringify({
                id: 'U1',
                name: 'U',
                email: 'u@x',
                role: 'END_USER',
                customer: 'C',
                permissions: [],
              }),
            )
          : new Response(JSON.stringify({ error: { code: 'not_signed_in', message: 'x' } }), {
              status: 401,
            })
      if (url.endsWith('/me/cart')) return new Response(JSON.stringify([]))
      if (url.endsWith('/commerce/agent')) {
        commerceCalls.push(JSON.parse(String(init?.body)).message)
        return new Response(JSON.stringify(session.commerce))
      }
      if (url.endsWith('/agent/suggestions')) return new Response(JSON.stringify(SUGGESTIONS))
      if (url.endsWith('/agent/catalog')) return new Response(JSON.stringify(CATALOG))
      if (url.endsWith('/cart/quote'))
        return new Response(
          JSON.stringify({
            lines: [],
            rejected: [],
            unknown_part_ids: [],
            subtotal: null,
            unpriced_part_ids: [],
            order_placement_available: false,
            note: '',
          }),
        )
      const body = JSON.parse(String(init?.body)) as { request: string }
      calls.push(body.request)
      if (typeof response !== 'function')
        return new Response(
          JSON.stringify({ error: { code: response.code, message: 'internal detail' } }),
          { status: response.status },
        )
      return new Response(JSON.stringify({ ...response(body.request), request: body.request })) // the API echoes the request
    }),
  )
  render(
    <MemoryRouter
      initialEntries={[q ? `/agentic-shopping?q=${encodeURIComponent(q)}` : '/agentic-shopping']}
    >
      <SessionProvider>
        <AgenticShoppingPage />
      </SessionProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('agentic shopping', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', () => ({ matches: true })) // reduced motion: the reported steps appear at once
    Element.prototype.scrollIntoView = () => {}
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('starts as a request to an agent, with the question catalog from the API, not a search box', async () => {
    mount(() => recommendation, null)
    expect(
      screen.getByRole('heading', { name: 'Your next part. A smarter way to find it.' }),
    ).toBeTruthy()
    expect(screen.getByText(/checks the right part against your requirements/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Find the right part' })).toBeTruthy()
    expect(screen.queryByPlaceholderText(/search parts/i)).toBeNull()
    expect(await screen.findByRole('heading', { name: 'Question catalog' })).toBeTruthy()
    expect(screen.getByRole('list', { name: 'Find a part questions' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Orders' }))
    expect(screen.getByText('Sign in for these.')).toBeTruthy()
    expect(document.querySelector('.ag-pills')).toBeNull() // the earlier example pills are replaced by the catalog
  })

  it('runs a catalog question directly when it is chosen', async () => {
    const calls = mount(() => recommendation, null)
    fireEvent.click(await screen.findByRole('button', { name: 'I need a hose for my M-1.' }))
    expect(await screen.findByText(/I need a hose for my M-1\./, { selector: 'h1' })).toBeTruthy()
    await waitFor(() => expect(calls).toEqual(['I need a hose for my M-1.']))
  })

  it('shows how the request was read, with only the fields that were understood', async () => {
    mount(() => recommendation)
    const panel = await screen.findByRole('region', { name: 'Your request' })
    expect(panel.textContent).toMatch(/MachineM-1/)
    expect(panel.textContent).toMatch(/Budget/)
    expect(panel.textContent).toMatch(/800/)
    expect(panel.textContent).toMatch(/PriorityLowest price/)
    expect(panel.textContent).not.toMatch(/Location|Quantity/)
  })

  it('presents a complete recommendation: every decision field has a value or an explicit state, never a dash', async () => {
    mount(() => recommendation)
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    const best = (await screen.findByRole('heading', { level: 3, name: 'AB-1' })).closest(
      '.reco-card',
    )!
    const text = best.textContent ?? ''
    for (const v of [
      'Confirmed fit',
      'In stock',
      '5 units across 2 warehouses',
      'Available from connected stock (2 warehouses)',
      'Estimate not recorded',
      'Supplier One (demo)',
      'ex VAT',
      'Northtown · 3',
    ])
      expect(text).toContain(v)
    expect(text).not.toMatch(/—|undefined|null|N\/A/)
    expect(document.querySelector('.ag-res')?.textContent).not.toMatch(/—|undefined|\bnull\b/)
  })

  it('never offers Add to cart for a part that is not verified', async () => {
    mount(() => ({
      ...recommendation,
      candidates: [
        {
          ...recommendation.candidates[0],
          order_action: 'identify',
          can_add_to_cart: false,
          part: part('P3', 'AB-3', 'UNVERIFIED', false, 5),
        },
      ],
    }))
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    await screen.findAllByText('AB-3')
    expect(screen.queryByRole('button', { name: /add to cart/i })).toBeNull()
    expect(screen.getByRole('link', { name: 'Identification required' }).getAttribute('href')).toBe(
      '/spark/chat?part=AB-3&tab=store',
    )
  })

  it('says plainly when nothing meets the budget, without showing a part', async () => {
    mount(() => ({
      ...base,
      state: 'no_match',
      steps: steps(7),
      question:
        'I found 1 compatible verified cooling fan for the M-1, but none currently meets your €500 budget.',
    }))
    await screen.findByText(/none currently meets your €500 budget/)
    expect(document.querySelectorAll('.reco-card, .ag-table')).toHaveLength(0)
  })

  it('asks for the missing detail right away and re-runs the request with the chosen option', async () => {
    const calls = mount((request) =>
      request.includes('for my M-2')
        ? recommendation
        : {
            ...base,
            state: 'choose_machine',
            steps: steps(1),
            question: 'Which loader is it?',
            options: [{ label: 'M-2 Wheel Loader', refine: 'for my M-2' }],
          },
    )
    fireEvent.click(await screen.findByRole('button', { name: 'M-2 Wheel Loader' }))
    await screen.findByText('msg recommend')
    expect(calls).toEqual(['I need a hose', 'I need a hose for my M-2'])
  })

  it('asks for the destination when the fastest option needs one, then re-runs with the chosen recorded place', async () => {
    const calls = mount((request) =>
      request.includes('delivered to Hamburg')
        ? recommendation
        : {
            ...base,
            state: 'need_detail',
            steps: steps(6),
            question: 'Fastest depends on where the part is going. Where should it be delivered?',
            options: [{ label: 'Hamburg', refine: 'delivered to Hamburg' }],
          },
    )
    expect(await screen.findByText(/Where should it be delivered/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Hamburg' }))
    await screen.findByText('msg recommend')
    expect(calls).toEqual(['I need a hose', 'I need a hose delivered to Hamburg'])
  })

  it('shows the recorded route, the transport option and dealer service as labelled evidence, and on-order stock as its own state', async () => {
    const withRoute: AgentResponse = {
      ...recommendation,
      interpretation: { ...base.interpretation, delivery_place: 'Hamburg', availability: 'future' },
      evidence: [
        {
          key: 'transport',
          ok: true,
          label: 'Premium Road · road',
          detail:
            'Route R-1, 400 km; freight context 120 EUR (synthetic demo estimate, not a price)',
          data_class: 'SYNTHETIC_DEMO',
        },
        {
          key: 'dealer',
          ok: true,
          label: 'Dealers in DE that install this part',
          detail: 'Dealer One (Hamburg). Service evidence only.',
          data_class: 'SYNTHETIC_DEMO',
        },
      ],
    }
    mount(() => withRoute)
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    const ev = (await screen.findByText('Premium Road · road')).closest('ul')!
    expect(ev.textContent).toMatch(/not a price/)
    expect(ev.textContent).toMatch(/Dealers in DE that install this part/)
    expect(document.querySelector('.ag-req')?.textContent).toMatch(/Accepts on-order stock/)
  })

  it('shows a compact service state without provider or transport details', async () => {
    mount({ status: 503, code: 'llm_unavailable' })
    const state = await screen.findByText('Agent temporarily unavailable')
    const box = state.closest('.ag-service')?.textContent ?? ''
    expect(box).toMatch(/Please try again/)
    expect(box).not.toMatch(/Gemini|API|quota|HTTP|503|internal detail/i)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })

  it('keeps a request that is neither a part nor an order, shipment or warranty question out of the shopping flow and points to Parts Intelligence', async () => {
    mount(
      () => ({
        ...base,
        state: 'out_of_scope',
        steps: steps(0),
        question: 'I find and help order Noordveld machine parts.',
      }),
      'tell me a joke',
    )
    await screen.findByText('I find and help order Noordveld machine parts.')
    expect(document.querySelector('.ag-note a')?.getAttribute('href')).toBe('/spark/chat')
    expect(document.querySelectorAll('.reco-card')).toHaveLength(0)
  })

  it('answers an order or shipment question on the same screen through the commerce assistant, with no second input box', async () => {
    mount(
      () => ({
        ...base,
        state: 'out_of_scope',
        steps: steps(0),
        question: 'not a part',
        commerce_domains: ['LOGISTICS'],
      }),
      'Where is my shipment?',
      { signedIn: true, commerce: commerceAnswer('LOGISTICS', 'Shipment S-1 is in transit.') },
    )
    expect((await screen.findAllByText('Shipment S-1 is in transit.')).length).toBeGreaterThan(0)
    expect(commerceCalls).toEqual(['Where is my shipment?'])
    expect(screen.queryByText('Part answer.')).toBeNull() // only the journeys the request asked about
    expect(screen.queryByRole('textbox', { name: 'What can I help you with?' })).toBeNull()
  })

  it('asks a signed-out visitor to sign in for order, shipment and warranty answers and comes back to the same request', async () => {
    mount(
      () => ({
        ...base,
        state: 'out_of_scope',
        steps: steps(0),
        question: 'not a part',
        commerce_domains: ['WARRANTY'],
      }),
      'Is this failed part covered by warranty?',
    )
    const link = await screen.findByRole('link', { name: 'Sign in' })
    expect(link.getAttribute('href')).toBe(
      `/sign-in?${new URLSearchParams({ next: `/agentic-shopping?q=${encodeURIComponent('Is this failed part covered by warranty?')}` })}`,
    )
    expect(commerceCalls).toEqual([]) // nothing is asked for a visitor
  })

  it('shows the warranty answer of a combined request under the part recommendation', async () => {
    mount(
      () => ({ ...recommendation, commerce_domains: ['WARRANTY'] }),
      'I need a hose. Is the failed one covered?',
      { signedIn: true, commerce: commerceAnswer('WARRANTY', 'Claim C-1 is eligible.') },
    )
    fireEvent.click(await screen.findByRole('button', { name: /View recommendation/ }))
    expect((await screen.findAllByText('Claim C-1 is eligible.')).length).toBeGreaterThan(0)
    expect(screen.getByText(/Also in your request · Warranty/)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /Add to cart/ }).length).toBeGreaterThan(0) // the shopping recommendation and its cart action are unchanged
  })
})
