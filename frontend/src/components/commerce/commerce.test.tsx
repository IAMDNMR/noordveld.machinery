// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentResponse, AgentSection, CommerceContext, Domain } from '../../api/commerce'
import CommercePage from '../../pages/CommercePage'
import { SessionProvider } from '../../store/session'
import { optionText } from './CommerceWorkspace'

// Every value below is a fixture standing in for the backend's response; the tests prove the page shows what the API returns, in one place, and decides nothing itself.
const ME = (role: 'END_USER' | 'ORDER_PROCESSOR') => ({ id: 'U1', name: 'Test User', email: 't@x', role, customer: role === 'END_USER' ? 'Test Customer' : null, permissions: ['commerce.context'] })
const base = (type: Domain, decision: string, summary: string, extra: Partial<CommerceContext> = {}): CommerceContext => ({
  context_id: 'CTX-1', context_type: type, generated_at: '2026-10-07T00:00:00Z', data_status: 'SYNTHETIC_DEMO',
  source_records: [{ entity: 'Part', id: 'PRT-1', data_status: 'SYNTHETIC_DEMO' }], evidence: [{ fact: 'fact one', entity: 'Part', id: 'PRT-1', data_status: 'SYNTHETIC_DEMO' }],
  confidence: { level: 'COMPLETE', data_status: 'SYNTHETIC_DEMO', fact_verified: true, real_world_verified: false, basis: 'b' }, missing: [], warnings: [],
  decision: { status: decision === 'RECOMMEND' || decision === 'ELIGIBLE' ? 'SUCCESS' : 'NOT_FOUND', decision, summary, facts: {}, reasons: [], evidence: [], source_records: [], missing: [], warnings: [], recommended_next_action: 'INTERNAL AGENT INSTRUCTION' },
  evidence_path: [{ step: 1, entity: 'Part', id: 'PRT-1', relation_to_next: 'FITS', data_status: 'SYNTHETIC_DEMO' }, { step: 2, entity: 'Fitment', id: 'F-1', relation_to_next: null, data_status: 'SYNTHETIC_DEMO' }],
  visibility: { role: 'END_CUSTOMER', hidden_fields: [] }, ...extra,
})
const section = (domain: Domain, decision: string, headline: string, status = 'SUCCESS'): AgentSection => ({ domain, title: { DISCOVERY: 'Part discovery', LOGISTICS: 'Shipment and logistics', WARRANTY: 'Warranty and traceability' }[domain], status, decision, headline, lines: [], notes: [] })
const response = (over: Partial<AgentResponse> & Pick<AgentResponse, 'intent' | 'contexts' | 'answer'>): AgentResponse => ({
  status: 'ANSWERED', steps: [], clarification: null, evidence: [], evidence_paths: {}, source_records: [], data_status: 'SYNTHETIC_DEMO', confidence: {}, visibility: {}, warnings: [], missing: [],
  state: {}, understanding: { intent: over.intent, domains: [], source: 'RULES', focus: [], references: {}, reasons: [] }, ...over,
})
const NOTICE = 'This is demonstration data: the records are synthetic demo data, not real operational data.'
const answer = (text: string, sections: AgentSection[], notice: string | null = NOTICE): AgentResponse['answer'] => ({ text, lead: text, sections, synthetic_notice: notice, grounding: { mode: 'TEMPLATE', validated: true } })

const discovery = response({
  intent: 'DISCOVERY', answer: answer('Gear pump (NVM-X) fits the machine and is available.', [section('DISCOVERY', 'RECOMMEND', 'Gear pump (NVM-X) fits the machine and is available.')]),
  state: { part_number: 'NVM-X', machine_model: 'M-1', last_domains: ['DISCOVERY'] },
  contexts: { DISCOVERY: { ...base('DISCOVERY', 'RECOMMEND', 'Gear pump (NVM-X) fits the machine and is available.'), user_request: 'r', machine: { resolution: 'RESOLVED', model: 'M-1', name: 'Machine one' },
    candidate_parts: [{ part_id: 'PRT-1', part_number: 'NVM-X', name: 'Gear pump' }, { part_id: 'PRT-2', part_number: 'NVM-Y', name: 'Lube pump' }], availability: [{ part_id: 'PRT-1', state: 'AVAILABLE', total_available: 12 }],
    recommended_part: { part_id: 'PRT-1', part_number: 'NVM-X', name: 'Gear pump', product_match_status: 'CANONICAL_MATCH', fitment: 'APPROVED', approved_source: true, price: { state: 'AVAILABLE', unit_price: 100, currency: 'EUR', price_status: 'DEMO_PRICE' } },
    compatible_part: null, alternatives: [], ranking: [{ rank: 1, part_id: 'PRT-1', part_number: 'NVM-X', total_score: 0.97, components: {}, explanation: { lines: ['fitment = APPROVED'] } }],
    rejection_reasons: { 'PRT-2': [{ code: 'CANONICAL_TYPE_MISMATCH', detail: 'Matched only through alias text.' }] }, clarification: null } },
})
const logisticsCtx = (over: Record<string, unknown> = {}) => ({
  ...base('LOGISTICS', 'ROUTE_NOT_DETERMINABLE', 'Shipment SHP-1 is recorded as IN_TRANSIT.'), order: { order_id: 'ORD-1' }, shipment: { shipment_id: 'SHP-1', order_id: 'ORD-1', status: 'SHIPPED' },
  part: null, shipment_lines: [{ order_line_id: 'OL-1', part_id: 'P1', part_number: 'NVM-A', name: 'Hose', quantity: 1 }, { order_line_id: 'OL-2', part_id: 'P2', part_number: 'NVM-B', name: 'Joint', quantity: 2 }],
  parts: [{ part_id: 'P1', part_number: 'NVM-A', name: 'Hose' }, { part_id: 'P2', part_number: 'NVM-B', name: 'Joint' }], shipment_kind: 'MULTI_LINE', order_shipments: ['SHP-1'], order_split: false,
  current_status: 'IN_TRANSIT', route: null, route_legs: [], completed_legs: [], remaining_legs: [], planned_eta: null, transport_comparison: null, tracking_events: [], route_resolution_status: 'ROUTE_NOT_DETERMINABLE', requires_review: true, clarification: null, ...over,
})
const logistics = (over: Record<string, unknown> = {}) => response({
  intent: 'LOGISTICS', answer: answer('Shipment SHP-1 is recorded as IN_TRANSIT.', [section('LOGISTICS', 'ROUTE_NOT_DETERMINABLE', 'Shipment SHP-1 is recorded as IN_TRANSIT.')]), state: { shipment_id: 'SHP-1', last_domains: ['LOGISTICS'] },
  contexts: { LOGISTICS: logisticsCtx(over) as never },
})
const warranty = response({
  intent: 'WARRANTY', answer: answer('Every applicable warranty condition holds.', [section('WARRANTY', 'ELIGIBLE', 'Every applicable warranty condition holds.')]), state: { claim_id: 'CLM-1' },
  contexts: { WARRANTY: { ...base('WARRANTY', 'NOT_ELIGIBLE', 'Every applicable warranty condition holds.'), machine: { machine_instance_id: 'MI-1' }, current_part: { part_id: 'P1', part_number: 'NVM-A', name: 'Piston pump' },
    installation: { installation_id: 'INS-1', installation_date: '2026-04-12', validation_status: 'VALID', validation_issues: [] }, dealer: { dealer_id: 'D1', name: 'Dealer One (demo)', authorized_status: 'AUTHORISED' },
    technician: { technician_id: 'T1', certification: 'L3', specialization: 'Hydraulics' }, work_order: { work_order_id: 'WO-1', service_type: 'INSTALLATION', service_date: '2026-04-12' },
    coverage_start: '2026-04-12', coverage_end: '2027-04-12', replacement_history: [{ replacement_id: 'REP-1', replacement_date: '2026-05-01' }], prior_claims: [], claim: { claim_id: 'CLM-1', status: 'SUBMITTED' },
    decision_factors: [{ code: 'APPROVED_PART', label: 'The part is a verified catalogue part', status: 'PASS', detail: 'ok' }, { code: 'X', label: 'Evidence', status: 'UNKNOWN', detail: 'missing record' }],
    visibility: { role: 'END_CUSTOMER', hidden_fields: ['technician.name'] } } },
})
const lookup = response({
  intent: 'DISCOVERY', answer: answer('Gear pump (NVM-X) is approved for 2 machine model(s): M-1, M-2.', [section('DISCOVERY', 'PART_FITMENT', 'Gear pump (NVM-X) is approved for 2 machine model(s): M-1, M-2.')]),
  contexts: { DISCOVERY: { ...base('DISCOVERY', 'PART_FITMENT', 'Gear pump (NVM-X) is approved for 2 machine model(s): M-1, M-2.'), lookup: 'PART_FITMENT', part: { part_id: 'PRT-1', part_number: 'NVM-X', name: 'Gear pump' },
    machines: [{ machine_id: 'MCH-1', model: 'M-1', name: 'Machine one', fitment_id: 'F-1', fitment_rule: 'EXACT_MODEL' }, { machine_id: 'MCH-2', model: 'M-2', name: 'Machine two', fitment_id: 'F-2', fitment_rule: 'EXACT_MODEL' }],
    other_fitments: [], sources: [], catalogue: null } as never },
})
const routeOptions = response({
  intent: 'LOGISTICS', answer: answer('Recorded routes (potential, not assigned to any shipment): Place A: air 5 days, sea 31 days.', [section('LOGISTICS', 'ROUTE_OPTIONS', 'Recorded routes (potential, not assigned to any shipment): Place A: air 5 days, sea 31 days.')]),
  contexts: { LOGISTICS: { ...base('LOGISTICS', 'ROUTE_OPTIONS', 'Recorded routes'), lookup: 'ROUTE_OPTIONS', destinations: [{ location_id: 'L1', name: 'Dealer A', city: 'Place A', country: 'Country A', region: 'R', routes: [
    { route_id: 'RTE-AIR', transport_mode: 'AIR', service_level: 'EXPRESS', planned_transit_days: 5, estimated_cost: 6570, currency: 'EUR', origin: { name: 'Hub', location_id: 'H1' } },
    { route_id: 'RTE-SEA', transport_mode: 'SEA', service_level: 'STANDARD', planned_transit_days: 31, estimated_cost: 2530, currency: 'EUR', origin: { name: 'Hub', location_id: 'H1' } }] }] } as never },
})
const clarifying = (options: Record<string, unknown>[]) => response({
  intent: 'WARRANTY', status: 'REQUIRES_CLARIFICATION', answer: answer('Which machine do you mean?', [section('WARRANTY', 'REQUIRES_CLARIFICATION', 'Which machine do you mean?', 'REQUIRES_CLARIFICATION')]),
  clarification: { domain: 'WARRANTY', question: 'Which machine do you mean?', options }, contexts: {}, state: { pending_message: 'Is this part under warranty?', last_domains: ['WARRANTY'] },
})
const outOfScope = response({ intent: 'UNKNOWN', status: 'OUT_OF_SCOPE', answer: answer('I can find a part, track a shipment or check warranty.', [], null), contexts: {} })

interface Call { url: string; body: Record<string, unknown> | null }
let calls: Call[]
let cartCalls: Call[] = []
let replies: { status?: number; body: unknown; hold?: Promise<void> }[]
const mount = (role: 'END_USER' | 'ORDER_PROCESSOR' | null = 'END_USER') => {
  calls = []
  cartCalls = []
  localStorage.clear() // the cart lives in the browser too: every test starts with an empty one
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace('/api/v1', '')
    if (path === '/me') return role ? new Response(JSON.stringify(ME(role)), { status: 200 }) : new Response(JSON.stringify({ error: { code: 'not_signed_in', message: 'Sign in' } }), { status: 401 })
    if (path === '/me/cart') return (cartCalls.push({ url: path, body: init?.body ? JSON.parse(String(init.body)) : null }), new Response(JSON.stringify(init?.method === 'PUT' ? JSON.parse(String(init.body)).lines : []), { status: 200 })) // the existing Parts Store cart
    calls.push({ url: path, body: init?.body ? JSON.parse(String(init.body)) : null })
    const next = replies.shift() ?? { status: 500, body: { error: { code: 'x', message: 'no reply queued' } } }
    if (next.hold) await next.hold
    return new Response(JSON.stringify(next.body), { status: next.status ?? 200 })
  }))
  return render(<MemoryRouter><SessionProvider><CommercePage /></SessionProvider></MemoryRouter>)
}
const box = async () => (await screen.findByRole('textbox', { name: 'What can I help you with?' })) as HTMLInputElement
const ask = async (text: string) => {
  const input = await box()
  fireEvent.change(input, { target: { value: text } })
  fireEvent.submit(input.closest('form') as HTMLFormElement) // Enter in the box submits the form
}
const answerOf = async () => within(await screen.findByRole('article', { name: 'Answer' }))

beforeEach(() => { replies = [] })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Commerce Assistant: one input, one answer', () => {
  it('asks the user to sign in and shows no commerce data when signed out', async () => {
    mount(null)
    expect(await screen.findByRole('heading', { name: /Sign in to use the commerce assistant/ })).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(calls).toEqual([])
  })

  it('has exactly one input and one Ask button, no domain tabs and no data before anything is asked', async () => {
    mount()
    await box()
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Ask' })).toHaveLength(1)
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('tab')).toBeNull()
    expect(screen.queryByRole('button', { name: /Track|Find part|Check warranty/ })).toBeNull()
    expect(document.body.textContent).not.toMatch(/NVM-|CLM-|MI-|EUR/)
    expect(screen.queryByRole('article', { name: 'Answer' })).toBeNull()
    expect(calls).toEqual([])
  })

  it('shows the discovery answer beneath the input with only the relevant detail, and the evidence collapsed', async () => {
    replies = [{ body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    const a = await answerOf()
    expect(await screen.findByText('Gear pump (NVM-X) fits the machine and is available.', { selector: 'p.cw-lead' })).toBeTruthy()
    expect(calls[0]).toEqual({ url: '/commerce/agent', body: { message: 'Find a hydraulic pump for M-1', state: {} } })
    expect(a.getByRole('article', { name: 'Recommended part' })).toBeTruthy()
    expect(a.getByText(/100\.00 EUR \(demo price\)/)).toBeTruthy()
    expect(a.getByText(/Matched only through alias text/)).toBeTruthy()
    expect(a.queryByRole('region', { name: 'Shipment result' })).toBeNull()
    expect(a.queryByRole('region', { name: 'Warranty and traceability' })).toBeNull()
    expect(document.body.textContent).not.toMatch(/INTERNAL AGENT INSTRUCTION/) // the agent-facing next action is never shown to the user
    const evidence = document.querySelector('details.cw-evidence-box') as HTMLDetailsElement
    expect(evidence.open).toBe(false)
    expect(within(evidence).getByText(/Evidence and sources/)).toBeTruthy()
    expect(within(evidence).getByRole('list', { name: 'Evidence path' }).textContent).toMatch(/Part.*PRT-1.*FITS.*Fitment.*F-1/)
    expect(a.getAllByText(/demonstration data/i).length).toBeGreaterThan(0)
    expect(a.getByText(/Written directly from the records/)).toBeTruthy()
  })

  it('leads the answer from the first journey and shows every order line and part of a multi-line shipment, nothing else', async () => {
    replies = [{ body: logistics() }]
    mount()
    await ask('Where is SHP-1 and what parts are in it?')
    const a = await answerOf()
    const table = within(await a.findByRole('table', { name: 'Order lines in this shipment' }))
    expect(a.getByText('2 order lines')).toBeTruthy()
    expect(table.getByText('NVM-A')).toBeTruthy()
    expect(table.getByText('NVM-B')).toBeTruthy()
    expect(table.getAllByRole('row')).toHaveLength(3)
    expect(screen.queryByRole('region', { name: 'Part discovery' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Warranty and traceability' })).toBeNull()
  })

  it('shows an order that has no shipment yet with its lines, and offers no shipment follow-ups', async () => {
    replies = [{ body: logistics({ shipment: null, shipment_lines: [], parts: [], shipment_kind: null, current_status: null, order: { order_id: 'ORD-9', status: 'ALLOCATED', order_date: '2026-10-01' }, order_lines: [{ order_line_id: 'ORD-9-L1', part_number: 'NVM-A', name: 'Hose', quantity: 4 }] }) }]
    mount()
    await ask('Where is order ORD-9?')
    const a = await answerOf()
    const table = within(await a.findByRole('table', { name: 'Order lines' }))
    expect(table.getByText('NVM-A')).toBeTruthy()
    expect(a.getByText('none recorded yet')).toBeTruthy()
    expect(a.getByText('allocated')).toBeTruthy()
    expect(screen.queryByLabelText('What next')).toBeNull()
  })

  it('keeps a split order and a multi-line shipment apart', async () => {
    replies = [{ body: logistics({ shipment_kind: 'SINGLE_LINE', shipment_lines: [{ order_line_id: 'OL-9', part_id: 'P1', part_number: 'NVM-A', name: 'Hose', quantity: 3 }], parts: [{ part_id: 'P1', part_number: 'NVM-A', name: 'Hose' }], part: { part_id: 'P1', part_number: 'NVM-A', name: 'Hose' }, order_split: true, order_shipments: ['SHP-1', 'SHP-2'] }) }]
    mount()
    await ask('Where is SHP-1?')
    const a = await answerOf()
    expect(await a.findByText('one order line')).toBeTruthy()
    expect(a.getByText(/split into 2 separate shipments: SHP-1 \(this one\), SHP-2/)).toBeTruthy()
    expect(a.queryByText(/order lines$/)).toBeNull()
  })

  it('shows the warranty checks, the installation and a hidden technician name inside the same answer', async () => {
    replies = [{ body: warranty }]
    mount()
    await ask('Is this failed part covered by warranty?')
    const a = await answerOf()
    expect(await a.findByText('The part is a verified catalogue part')).toBeTruthy()
    expect(a.getByText('missing record')).toBeTruthy()
    expect(a.getByText(/Dealer One \(demo\) · authorised/)).toBeTruthy()
    expect(a.getByText(/\(name not shown to your role\)/)).toBeTruthy()
    expect(a.getByText(/REP-1/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Why is this claim not eligible?' })).toBeTruthy() // offered because the decision is not eligible
  })

  it('hands a recommended part to the existing Parts Store cart, with the machine, only when the user chooses to', async () => {
    replies = [{ body: discovery }]
    mount()
    await ask('Find a pump for the machine')
    const a = await answerOf()
    const add = await a.findByRole('button', { name: 'Add NVM-X to cart' })
    expect(cartCalls.some((c) => JSON.stringify(c.body ?? '').includes('PRT-1'))).toBe(false) // nothing is added before the user asks
    fireEvent.click(add)
    expect((await a.findByRole('link', { name: 'Added · Review order' })).getAttribute('href')).toBe('/parts-store/checkout')
    await waitFor(() => expect(cartCalls.filter((c) => c.body).at(-1)?.body).toEqual({ lines: [{ part_id: 'PRT-1', quantity: 1, machine: 'M-1' }] }))
    expect(a.getByRole('link', { name: 'Compare delivery and fulfilment options' }).getAttribute('href')).toContain('/agentic-shopping?q=')
  })

  it('offers no cart hand-off when nothing is recommended', async () => {
    replies = [{ body: lookup }]
    mount()
    await ask('Which machine uses this part?')
    const a = await answerOf()
    await a.findByRole('table', { name: 'Approved machines' })
    expect(a.queryByRole('button', { name: /to cart/ })).toBeNull()
  })

  it('shows machines a part is approved for and any other single-part answer in the same place', async () => {
    replies = [{ body: lookup }]
    mount()
    await ask('Which machine uses this part?')
    const a = await answerOf()
    const table = within(await a.findByRole('table', { name: 'Approved machines' }))
    expect(table.getByText('M-1')).toBeTruthy()
    expect(table.getByText('M-2')).toBeTruthy()
  })

  it('shows the recorded routes to a place with no shipment as potential routes, with no shipment follow-ups', async () => {
    replies = [{ body: routeOptions }]
    mount()
    await ask('How long to ship to Place A?')
    const a = await answerOf()
    const table = within(await a.findByRole('table', { name: 'Routes to Place A' }))
    expect(table.getByText('RTE-AIR')).toBeTruthy()
    expect(table.getByText('31 days')).toBeTruthy()
    expect(a.getByText(/none is assigned to a shipment/)).toBeTruthy()
    expect(a.queryByRole('button', { name: 'Can I get it faster?' })).toBeNull()
  })

  it('asks a clarification in the conversation, offers the records it has, and carries on with the same question when one is chosen', async () => {
    replies = [{ body: clarifying([{ machine_instance_id: 'MI-1', serial_number: 'S-1', model_year: 2025 }, { machine_instance_id: 'MI-2', serial_number: 'S-2', model_year: 2024 }]) }, { body: warranty }]
    mount()
    await ask('Is this part under warranty?')
    const group = within(await screen.findByRole('group', { name: 'Clarification' }))
    expect(group.getByText('Which machine do you mean?')).toBeTruthy()
    expect((await box()).placeholder).toBe('Which machine do you mean?')
    const options = group.getAllByRole('button')
    expect(options.map((o) => o.textContent)).toEqual(['MI-1 · serial S-1 · year 2025', 'MI-2 · serial S-2 · year 2024'])
    fireEvent.click(options[1])
    await screen.findByText('The part is a verified catalogue part') // the answer is replaced by the new one
    expect(calls[1].body).toEqual({ message: 'Is this part under warranty?', state: { pending_message: 'Is this part under warranty?', last_domains: ['WARRANTY'], machine_instance_id: 'MI-2' } })
    expect(screen.queryByRole('group', { name: 'Clarification' })).toBeNull()
    expect(screen.getByText(/Earlier in this conversation \(1\)/)).toBeTruthy() // the question stays part of one conversation
  })

  it('asks the question once and shows no evidence box for an answer that is only a question', async () => {
    replies = [{ body: { ...clarifying([]), contexts: { WARRANTY: { ...base('WARRANTY', 'REQUIRES_CLARIFICATION', 'x') } as never } } }]
    mount()
    await ask('Is this part under warranty?')
    await screen.findByRole('group', { name: 'Clarification' })
    expect(screen.getAllByText('Which machine do you mean?')).toHaveLength(1) // once, in the clarification box
    expect(document.querySelector('.cw-lead')).toBeNull()
    expect(document.querySelector('details.cw-evidence-box')).toBeNull()
    expect(screen.getByText(/Type your answer here\./)).toBeTruthy()
  })

  it('takes a typed answer to a clarification that has no options and keeps the waiting question in the state', async () => {
    replies = [{ body: clarifying([]) }, { body: discovery }]
    mount()
    await ask('I need a hydraulic pump')
    expect(await screen.findByText(/Type your answer in the box above/)).toBeTruthy()
    await ask('M-1')
    await screen.findByRole('article', { name: 'Recommended part' })
    expect(calls[1].body).toEqual({ message: 'M-1', state: { pending_message: 'Is this part under warranty?', last_domains: ['WARRANTY'] } })
  })

  it('returns the identifiers of the last answer with the next message and never a decision', async () => {
    replies = [{ body: discovery }, { body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    await screen.findByRole('article', { name: 'Recommended part' })
    await ask('Do you have this part available?')
    await waitFor(() => expect(calls.length).toBe(2))
    expect(calls[1].body).toEqual({ message: 'Do you have this part available?', state: { part_number: 'NVM-X', machine_model: 'M-1', last_domains: ['DISCOVERY'] } })
    expect(JSON.stringify(calls[1].body)).not.toMatch(/RECOMMEND|ELIGIBLE/)
  })

  it('offers follow-up questions that fit the answer and sends them like typed text', async () => {
    replies = [{ body: logistics() }, { body: logistics() }]
    mount()
    await ask('Where is SHP-1?')
    await screen.findByRole('table', { name: 'Order lines in this shipment' })
    const next = within(screen.getByLabelText('What next'))
    expect(next.getAllByRole('button').map((b) => b.textContent)).toEqual(['What parts are in this shipment?', 'Can I get it faster?', 'Why is it taking so long?'])
    fireEvent.click(next.getByRole('button', { name: 'Can I get it faster?' }))
    await waitFor(() => expect(calls.length).toBe(2))
    expect(calls[1].body).toMatchObject({ message: 'Can I get it faster?', state: { shipment_id: 'SHP-1' } })
  })

  it('declines an out-of-scope request politely and shows what can be asked, with no empty panels', async () => {
    replies = [{ body: outOfScope }]
    mount()
    await ask('write me a poem')
    const a = await answerOf()
    expect(await a.findByText('I can find a part, track a shipment or check warranty.')).toBeTruthy()
    expect(a.getAllByRole('button').length).toBeGreaterThan(0)
    expect(a.queryByRole('region')).toBeNull()
  })

  it('says plainly when access is refused and shows nothing from the record', async () => {
    replies = [{ status: 403, body: { error: { code: 'forbidden', message: 'You do not have access to this record.' } } }]
    mount()
    await ask('Where is SHP-9?')
    expect((await screen.findByRole('alert')).textContent).toContain('You do not have access to that record.')
    expect(screen.queryByRole('article', { name: 'Answer' })).toBeNull()
  })

  it('shows a loading state and recovers from a network error with a retry', async () => {
    let release!: () => void
    replies = [{ body: discovery, hold: new Promise<void>((r) => { release = r }) }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    expect((await screen.findByRole('status')).textContent).toMatch(/Checking the records/)
    release()
    await screen.findByRole('article', { name: 'Recommended part' })
    expect(screen.queryByRole('status')).toBeNull()
    cleanup()
    // a failed request offers a retry that sends the same question again
    vi.unstubAllGlobals()
    replies = []
    mount()
    const input = await box()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValue(new Response(JSON.stringify(discovery), { status: 200 })))
    fireEvent.change(input, { target: { value: 'Find a hydraulic pump for M-1' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    expect((await screen.findByRole('alert')).textContent).toMatch(/could not be reached/)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('article', { name: 'Recommended part' })
  })

  it('lets an order processor view as a dealer and sends the dealer id with the request', async () => {
    replies = [{ body: logistics() }]
    mount('ORDER_PROCESSOR')
    fireEvent.change(await screen.findByRole('combobox', { name: /View as/ }), { target: { value: 'DEALER' } })
    fireEvent.change(screen.getByLabelText('Dealer id'), { target: { value: 'DLR-004' } })
    await ask('Where is SHP-1?')
    await screen.findByRole('table', { name: 'Order lines in this shipment' })
    expect(calls[0].body).toMatchObject({ user_role: 'DEALER', dealer_id: 'DLR-004' })
  })

  it('never sends a role for a customer', async () => {
    replies = [{ body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    await screen.findByRole('article', { name: 'Recommended part' })
    expect(Object.keys(calls[0].body ?? {})).not.toContain('user_role')
  })

  it('starts over: the conversation and the remembered references are cleared', async () => {
    replies = [{ body: logistics() }]
    mount()
    await ask('Where is SHP-1?')
    await screen.findByRole('table', { name: 'Order lines in this shipment' })
    expect(screen.getByText(/Remembering shipment id SHP-1/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Start over' }))
    expect(screen.queryByRole('article', { name: 'Answer' })).toBeNull()
    expect(screen.queryByText(/Remembering/)).toBeNull()
  })
})

describe('optionText', () => {
  it('puts the identifier first and labels what tells similar options apart', () => {
    expect(optionText({ machine_instance_id: 'MI-1', serial_number: 'S-1', model_year: 2025 })).toBe('MI-1 · serial S-1 · year 2025')
    expect(optionText({ claim_id: 'C-1', claim_date: '2026-01-01', status: 'SUBMITTED', empty: null, list: [] })).toBe('C-1 · 2026-01-01 · SUBMITTED')
    expect(optionText({ machine_instance_id: 'MI-1', installed_part_ids: ['P1', 'P2'] })).toBe('MI-1 · P1, P2')
  })
})
