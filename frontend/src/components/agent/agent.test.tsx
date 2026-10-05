// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentResponse } from '../../api/agent'
import type { PartSummary } from '../../api'
import AgenticShoppingPage from '../../pages/AgenticShoppingPage'

const part = (id: string, no: string, status: string, orderable: boolean, amount: number, state = 'IN_STOCK'): PartSummary => ({
  part_id: id, part_number: no, name: `Part ${no}`, category: 'Hydraulics', subcategory: 'Hose', fitment: [{ model_code: 'M-1', fitment_status: 'CONFIRMED' }],
  price: { amount, currency: 'EUR', data_status: 'SYNTHETIC_DEMO' }, availability: { state, orderable, part_status: status, total_available: 5, data_status: 'SYNTHETIC_DEMO' },
})
const KEYS = ['request', 'understand', 'machine', 'part', 'fitment', 'availability', 'fulfilment', 'compare', 'recommend'] as const
const steps = (blockedAt = -1): AgentResponse['steps'] =>
  KEYS.map((key, i) => ({ key, label: `Label ${key}`, message: `msg ${key}`, status: i === blockedAt ? 'blocked' : blockedAt >= 0 && i > blockedAt ? 'skipped' : 'done' }))
const base: Omit<AgentResponse, 'state' | 'steps'> = {
  request: 'r', interpretation: { machine: 'M-1', part_type: 'Hose', preference: 'cheapest', delivery_place: null, quantity: null, budget_max: 800, budget_currency: 'EUR', availability: 'none' }, question: null, options: [], candidates: [],
  recommended: null, reason: null, evidence: [], comparison: null, excluded: [], delivery: null, notes: [], disclaimer: 'Demo data disclaimer.',
  decision: null, why: [], how_we_know: [],
}
const fields = {
  fitment_label: 'Confirmed fit', stock_locations: [], suppliers: [], price_basis: 'ex VAT', order_action: 'add_to_cart' as const, order_note: null,
}
const recommendation: AgentResponse = {
  ...base, state: 'recommendation', steps: steps(), recommended: 'AB-1',
  candidates: [
    { ...fields, part: part('P1', 'AB-1', 'VERIFIED', true, 10), recommended: true, availability_label: 'In stock', fitment_status: 'CONFIRMED', inventory: '5 units across 2 warehouses',
      stock_locations: [{ warehouse: 'North depot', city: 'Northtown', available: 3 }, { warehouse: 'South depot', city: 'Southtown', available: 2 }],
      fulfilment: 'Available from connected stock (2 warehouses)', delivery: 'Estimate not recorded', supplier_label: 'Supplier One (demo)', suppliers: [{ name: 'Supplier One (demo)', lead_time_days: 7, primary: true }],
      supplier: 'Supplier One (demo)', supplier_lead_days: 7, fulfilment_days: null, within_budget: true, tradeoffs: [], can_add_to_cart: true },
    { ...fields, part: part('P2', 'AB-2', 'VERIFIED', true, 20, 'BACKORDER'), recommended: false, availability_label: 'Backorder', fitment_status: 'CONFIRMED', inventory: '0 units in stock',
      fulfilment: 'Supplier lead time · 10 days', delivery: 'Estimate not recorded', supplier_label: 'Supplier Two (demo) · lead time 10 days', order_note: 'Backorder: supplied after the supplier lead time (10 days)',
      supplier: 'Supplier Two (demo)', supplier_lead_days: 10, fulfilment_days: 10, within_budget: true, tradeoffs: ['Higher price', 'Lower availability'], can_add_to_cart: true }],
  decision: { requirements: ['Confirmed fit for the M-1', 'Verified part', 'Within your €800 budget'], priorities: ['Lowest price', 'Availability'], summary: 'AB-1 ranked first because it is confirmed compatible and it is currently in stock.' },
  why: [{ title: 'Confirmed compatibility', detail: 'Fits the M-1 (catalogue fitment).' }, { title: 'Lower price', detail: '€10 compared with €20 (AB-2).' }, { title: 'Your priority', detail: 'You asked for the cheapest option, so the lowest valid price came first.' }],
  how_we_know: [{ label: 'Fitment', value: 'Noordveld catalogue · confirmed fit' }, { label: 'Inventory', value: 'Synthetic demo inventory' }],
  reason: 'Recommended because it is recorded as fitting the M-1.', comparison: 'Compared with AB-2.',
  evidence: [{ key: 'fit', ok: true, label: 'Fits the M-1', detail: 'Catalogue fitment', data_class: 'SOURCE_DERIVED' }, { key: 'supplier', ok: false, label: 'No supplier relationship', detail: 'None recorded', data_class: null }],
  excluded: [{ part_number: 'AB-9', name: 'x', status_label: 'Identification required' }],
}
const SUGGESTIONS = [{ request: 'I need a hose for my M-1, preferably in stock.', need: 'Hose', context: 'M-1', action: 'Prefer in stock' }]

function mount(response: ((request: string) => AgentResponse) | { status: number; code: string }, q: string | null = 'I need a hose') {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/agent/suggestions')) return new Response(JSON.stringify(SUGGESTIONS))
    if (url.endsWith('/cart/quote')) return new Response(JSON.stringify({ lines: [], rejected: [], unknown_part_ids: [], subtotal: null, unpriced_part_ids: [], order_placement_available: false, note: '' }))
    const body = JSON.parse(String(init?.body)) as { request: string }
    calls.push(body.request)
    if (typeof response !== 'function') return new Response(JSON.stringify({ error: { code: response.code, message: 'internal detail' } }), { status: response.status })
    return new Response(JSON.stringify({ ...response(body.request), request: body.request })) // the API echoes the request
  }))
  render(<MemoryRouter initialEntries={[q ? `/agentic-shopping?q=${encodeURIComponent(q)}` : '/agentic-shopping']}><AgenticShoppingPage /></MemoryRouter>)
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

  it('starts as a request to an agent, with example requests from the API, not a search box', async () => {
    mount(() => recommendation, null)
    expect(screen.getByRole('heading', { name: 'What do you need?' })).toBeTruthy()
    expect(screen.getByText(/checks the right part against your requirements/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Find the right part' })).toBeTruthy()
    expect(screen.queryByPlaceholderText(/search parts/i)).toBeNull()
    expect(await screen.findByRole('button', { name: 'I need a hose for my M-1, preferably in stock.' })).toBeTruthy()
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
    const best = (await screen.findByRole('heading', { level: 3, name: 'AB-1' })).closest('.reco-card')!
    const text = best.textContent ?? ''
    for (const v of ['Confirmed fit', 'In stock', '5 units across 2 warehouses', 'Available from connected stock (2 warehouses)', 'Estimate not recorded', 'Supplier One (demo)', 'ex VAT', 'Northtown · 3'])
      expect(text).toContain(v)
    expect(text).not.toMatch(/—|undefined|null|N\/A/)
    expect(document.querySelector('.ag-res')?.textContent).not.toMatch(/—|undefined|\bnull\b/)
  })

  it('shows what the decision was made on and why this part, tied to the stated priority', async () => {
    mount(() => recommendation)
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    const decision = (await screen.findByRole('heading', { name: 'Decision' })).closest('section')!
    expect(decision.textContent).toMatch(/Within your €800 budget/)
    expect(decision.textContent).toMatch(/01 Lowest price.*02 Availability/)
    expect(decision.textContent).toMatch(/AB-1 ranked first because/)
    const why = screen.getByRole('heading', { name: 'Why AB-1?' }).closest('section')!
    expect(why.textContent).toMatch(/01Confirmed compatibility/)
    expect(why.textContent).toMatch(/You asked for the cheapest option/)
    const how = screen.getByRole('heading', { name: 'How we know' }).closest('section')!
    expect(how.textContent).toMatch(/InventorySynthetic demo inventory/)
  })

  it('lists only the alternatives, with explicit fulfilment, never the recommended part again', async () => {
    mount(() => recommendation)
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    const table = await screen.findByRole('table')
    expect([...table.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual(['Part', 'Price', 'Fitment', 'Availability', 'Fulfilment', 'Supplier', 'Reason', 'Action'])
    expect(table.textContent).not.toMatch(/AB-1/)
    expect(table.textContent).toMatch(/AB-2.*€20\.00 · ex VAT.*Confirmed fit.*Backorder.*Supplier lead time · 10 days.*Supplier Two \(demo\) · lead time 10 days.*Higher price · Lower availability/)
    cleanup()
    mount(() => ({ ...recommendation, candidates: [recommendation.candidates[0]] }))
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    expect(await screen.findByText('No other verified compatible options were found.')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('shows the steps the API reported, then the recommendation with its evidence; Add to cart leads to Review order, never a payment', async () => {
    mount(() => recommendation)
    await screen.findByText('msg recommend')
    expect(document.querySelectorAll('.ag-rail__step.is-done')).toHaveLength(9)
    fireEvent.click(screen.getByRole('button', { name: /view recommendation/i }))
    await screen.findByText('AB-1 ranked first because it is confirmed compatible and it is currently in stock.')
    expect(screen.getByText('Recommended', { selector: '.reco-best-badge' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /View evidence in Parts Intelligence/ }).getAttribute('href')).toBe('/parts-intelligence?part=AB-1')
    expect(screen.getByRole('link', { name: 'AB-9' }).getAttribute('href')).toBe('/parts-intelligence?part=AB-9')
    fireEvent.click(screen.getAllByRole('button', { name: /add to cart/i })[0])
    await waitFor(() => expect(JSON.parse(localStorage.getItem('noordveld-parts-cart-v2') ?? '[]')).toEqual([{ partId: 'P1', qty: 1, machine: null }]))
    expect(screen.getByRole('link', { name: /Review order/ }).getAttribute('href')).toBe('/parts-store/checkout')
    expect(document.body.textContent).not.toMatch(/payment successful|order confirmed|visa|paypal/i)
  })

  it('never offers Add to cart for a part that is not verified', async () => {
    mount(() => ({ ...recommendation, candidates: [{ ...recommendation.candidates[0], order_action: 'identify', can_add_to_cart: false, part: part('P3', 'AB-3', 'UNVERIFIED', false, 5) }] }))
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    await screen.findAllByText('AB-3')
    expect(screen.queryByRole('button', { name: /add to cart/i })).toBeNull()
    expect(screen.getByRole('link', { name: 'Identification required' }).getAttribute('href')).toBe('/parts-intelligence?part=AB-3&tab=store')
  })

  it('never offers Add to cart when the backend says the part lacks verified fitment or commerce data', async () => {
    mount(() => ({ ...recommendation, candidates: [{ ...recommendation.candidates[0], can_add_to_cart: false, order_action: 'unavailable' }] }))
    fireEvent.click(await screen.findByRole('button', { name: /view recommendation/i }))
    await screen.findAllByText('AB-1')
    expect(screen.queryByRole('button', { name: /add to cart/i })).toBeNull()
  })

  it('says plainly when nothing meets the budget, without showing a part', async () => {
    mount(() => ({ ...base, state: 'no_match', steps: steps(7), question: 'I found 1 compatible verified cooling fan for the M-1, but none currently meets your €500 budget.' }))
    await screen.findByText(/none currently meets your €500 budget/)
    expect(document.querySelectorAll('.reco-card, .ag-table')).toHaveLength(0)
  })

  it('asks for the missing detail right away and re-runs the request with the chosen option', async () => {
    const calls = mount((request) => request.includes('for my M-2')
      ? recommendation
      : { ...base, state: 'choose_machine', steps: steps(1), question: 'Which loader is it?', options: [{ label: 'M-2 Wheel Loader', refine: 'for my M-2' }] })
    fireEvent.click(await screen.findByRole('button', { name: 'M-2 Wheel Loader' }))
    await screen.findByText('msg recommend')
    expect(calls).toEqual(['I need a hose', 'I need a hose for my M-2'])
  })

  it('shows a compact service state without provider or transport details', async () => {
    mount({ status: 503, code: 'llm_unavailable' })
    const state = await screen.findByText('Agent temporarily unavailable')
    const box = state.closest('.ag-service')?.textContent ?? ''
    expect(box).toMatch(/Please try again/)
    expect(box).not.toMatch(/Gemini|API|quota|HTTP|503|internal detail/i)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })

  it('keeps out-of-scope requests out of the shopping flow and points to Parts Intelligence', async () => {
    mount(() => ({ ...base, state: 'out_of_scope', steps: steps(0), question: 'I find and help order Noordveld machine parts.' }), 'tell me a joke')
    await screen.findByText('I find and help order Noordveld machine parts.')
    expect(document.querySelector('.ag-note a')?.getAttribute('href')).toBe('/parts-intelligence')
    expect(document.querySelectorAll('.reco-card')).toHaveLength(0)
  })
})
