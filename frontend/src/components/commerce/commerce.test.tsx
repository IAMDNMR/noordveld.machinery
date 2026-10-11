// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentResponse, AgentSection, CommerceContext, Domain } from '../../api/commerce'
import CommercePage from '../../pages/CommercePage'
import { SessionProvider } from '../../store/session'

// Every value below is a fixture standing in for the backend's response; the tests prove the page shows what the API returns and decides nothing itself.
const ME = (role: 'END_USER' | 'ORDER_PROCESSOR') => ({ id: 'U1', name: 'Test User', email: 't@x', role, customer: role === 'END_USER' ? 'Test Customer' : null, permissions: ['commerce.context'] })
const base = (type: Domain, decision: string, summary: string, extra: Partial<CommerceContext> = {}): CommerceContext => ({
  context_id: 'CTX-1', context_type: type, generated_at: '2026-10-07T00:00:00Z', data_status: 'SYNTHETIC_DEMO',
  source_records: [{ entity: 'Part', id: 'PRT-1', data_status: 'SYNTHETIC_DEMO' }], evidence: [{ fact: 'fact one', entity: 'Part', id: 'PRT-1', data_status: 'SYNTHETIC_DEMO' }],
  confidence: { level: 'COMPLETE', data_status: 'SYNTHETIC_DEMO', fact_verified: true, real_world_verified: false, basis: 'b' }, missing: [], warnings: [],
  decision: { status: decision === 'RECOMMEND' || decision === 'ELIGIBLE' ? 'SUCCESS' : 'NOT_FOUND', decision, summary, facts: {}, reasons: [], evidence: [], source_records: [], missing: [], warnings: [], recommended_next_action: null },
  evidence_path: [{ step: 1, entity: 'Part', id: 'PRT-1', relation_to_next: 'FITS', data_status: 'SYNTHETIC_DEMO' }, { step: 2, entity: 'Fitment', id: 'F-1', relation_to_next: null, data_status: 'SYNTHETIC_DEMO' }],
  visibility: { role: 'END_CUSTOMER', hidden_fields: [] }, ...extra,
})
const section = (domain: Domain, decision: string, headline: string, lines: string[] = []): AgentSection => ({ domain, title: domain, status: 'SUCCESS', decision, headline, lines, notes: [] })
const response = (over: Partial<AgentResponse> & Pick<AgentResponse, 'intent' | 'contexts' | 'answer'>): AgentResponse => ({
  status: 'ANSWERED', steps: [], clarification: null, evidence: [], evidence_paths: {}, source_records: [], data_status: 'SYNTHETIC_DEMO', confidence: {}, visibility: {}, warnings: [], missing: [],
  state: {}, understanding: { intent: over.intent, domains: [], source: 'RULES', focus: [], references: {}, reasons: [] }, ...over,
})
const answer = (text: string, sections: AgentSection[], notice: string | null = 'This is demonstration data: the records are synthetic demo data, not real operational data.'): AgentResponse['answer'] =>
  ({ text, lead: text, sections, synthetic_notice: notice, grounding: { mode: 'TEMPLATE', validated: true } })

const discovery = response({
  intent: 'DISCOVERY', answer: answer('Gear pump (NVM-X) fits the machine and is available.', [section('DISCOVERY', 'RECOMMEND', 'Gear pump (NVM-X) fits the machine and is available.', ['Part: Gear pump'])]),
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
  intent: 'LOGISTICS', answer: answer('Shipment SHP-1 is recorded as IN_TRANSIT.', [section('LOGISTICS', 'ROUTE_NOT_DETERMINABLE', 'Shipment SHP-1 is recorded as IN_TRANSIT.')]), state: { shipment_id: 'SHP-1' },
  contexts: { LOGISTICS: logisticsCtx(over) as never },
})

const warranty = response({
  intent: 'WARRANTY', answer: answer('Every applicable warranty condition holds.', [section('WARRANTY', 'ELIGIBLE', 'Every applicable warranty condition holds.')]),
  contexts: { WARRANTY: { ...base('WARRANTY', 'ELIGIBLE', 'Every applicable warranty condition holds.'), machine: { machine_instance_id: 'MI-1' }, current_part: { part_id: 'P1', part_number: 'NVM-A', name: 'Piston pump' },
    installation: { installation_id: 'INS-1', installation_date: '2026-04-12', validation_status: 'VALID', validation_issues: [] }, dealer: { dealer_id: 'D1', name: 'Dealer One (demo)', authorized_status: 'AUTHORISED' },
    technician: { technician_id: 'T1', certification: 'L3', specialization: 'Hydraulics' }, work_order: { work_order_id: 'WO-1', service_type: 'INSTALLATION', service_date: '2026-04-12' },
    coverage_start: '2026-04-12', coverage_end: '2027-04-12', replacement_history: [{ replacement_id: 'REP-1', replacement_date: '2026-05-01' }], prior_claims: [], claim: { claim_id: 'CLM-1', status: 'SUBMITTED' },
    decision_factors: [{ code: 'APPROVED_PART', label: 'The part is a verified catalogue part', status: 'PASS', detail: 'ok' }, { code: 'X', label: 'Evidence', status: 'UNKNOWN', detail: 'missing record' }],
    visibility: { role: 'END_CUSTOMER', hidden_fields: ['technician.name'] } } },
})

interface Call { url: string; body: Record<string, unknown> | null }
let calls: Call[]
let replies: { status?: number; body: unknown }[]
const mount = (role: 'END_USER' | 'ORDER_PROCESSOR' | null = 'END_USER') => {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace('/api/v1', '')
    if (path === '/me') return role ? new Response(JSON.stringify(ME(role)), { status: 200 }) : new Response(JSON.stringify({ error: { code: 'not_signed_in', message: 'Sign in' } }), { status: 401 })
    calls.push({ url: path, body: init?.body ? JSON.parse(String(init.body)) : null })
    const next = replies.shift() ?? { status: 500, body: { error: { code: 'x', message: 'no reply queued' } } }
    return new Response(JSON.stringify(next.body), { status: next.status ?? 200 })
  }))
  return render(<MemoryRouter><SessionProvider><CommercePage /></SessionProvider></MemoryRouter>)
}
const ask = async (text: string) => {
  fireEvent.change(await screen.findByLabelText('Your request'), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

beforeEach(() => { replies = [] })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Commerce workspace', () => {
  it('asks the user to sign in and shows no commerce data when signed out', async () => {
    mount(null)
    expect(await screen.findByRole('heading', { name: /Sign in to use the commerce assistant/ })).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(calls).toEqual([])
  })

  it('has the five areas and shows no business data before anything is asked', async () => {
    mount()
    expect(await screen.findByRole('region', { name: 'Commerce Assistant' })).toBeTruthy()
    expect(screen.getAllByRole('tab').map((t) => t.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Part Discovery', 'Shipment / Logistics', 'Warranty / Traceability', 'Evidence / Context'])
    expect(document.body.textContent).not.toMatch(/NVM-|CLM-|MI-|EUR/) // no part, claim, machine or price on the page: the example prompts are words, the data comes from the API
    expect(screen.queryByRole('region', { name: /result/ })).toBeNull()
    expect(calls).toEqual([])
  })

  it('sends the message to the Commerce Agent API and shows the discovery result, evidence and disclosure from the response', async () => {
    replies = [{ body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    expect(await screen.findByRole('region', { name: 'Part discovery result' })).toBeTruthy()
    expect(calls[0]).toEqual({ url: '/commerce/agent', body: { message: 'Find a hydraulic pump for M-1', state: {} } })
    const view = within(screen.getByRole('region', { name: 'Part discovery result' }))
    expect(view.getByRole('article', { name: 'Recommended part' })).toBeTruthy()
    expect(view.getAllByText(/NVM-X/).length).toBeGreaterThan(0)
    expect(view.getByText(/100\.00 EUR \(demo price\)/)).toBeTruthy()
    expect(view.getByText(/Matched only through alias text/)).toBeTruthy() // a rejected canonical type mismatch is shown as rejected, with the backend's reason
    expect(screen.getAllByText(/demonstration data/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Written directly from the records/)).toBeTruthy()
  })

  it('returns the identifiers of the last answer with the next message and never a decision', async () => {
    replies = [{ body: discovery }, { body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    await screen.findByRole('region', { name: 'Part discovery result' })
    await waitFor(() => expect((screen.getByRole('button', { name: 'Ask' }) as HTMLButtonElement).disabled).toBe(true))
    await ask('Do you have this part available?')
    await waitFor(() => expect(calls.length).toBe(2))
    expect(calls[1].body).toEqual({ message: 'Do you have this part available?', state: { part_number: 'NVM-X', machine_model: 'M-1', last_domains: ['DISCOVERY'] } })
    expect(JSON.stringify(calls[1].body)).not.toMatch(/RECOMMEND|ELIGIBLE/)
  })

  it('shows every order line and part of a multi-line shipment and never picks one', async () => {
    replies = [{ body: logistics() }]
    mount()
    await ask('Where is SHP-1 and what parts are in it?')
    const view = within(await screen.findByRole('region', { name: 'Shipment result' }))
    expect(view.getByText('2 order lines')).toBeTruthy()
    const table = within(view.getByRole('table', { name: 'Order lines in this shipment' }))
    expect(table.getByText('NVM-A')).toBeTruthy()
    expect(table.getByText('NVM-B')).toBeTruthy()
    expect(table.getAllByRole('row')).toHaveLength(3)
    expect(view.queryByText(/split into/)).toBeNull()
  })

  it('keeps a split order and a multi-line shipment apart', async () => {
    replies = [{ body: logistics({ shipment_kind: 'SINGLE_LINE', shipment_lines: [{ order_line_id: 'OL-9', part_id: 'P1', part_number: 'NVM-A', name: 'Hose', quantity: 3 }], parts: [{ part_id: 'P1', part_number: 'NVM-A', name: 'Hose' }], part: { part_id: 'P1', part_number: 'NVM-A', name: 'Hose' }, order_split: true, order_shipments: ['SHP-1', 'SHP-2'] }) }]
    mount()
    await ask('Where is SHP-1?')
    const view = within(await screen.findByRole('region', { name: 'Shipment result' }))
    expect(view.getByText('one order line')).toBeTruthy()
    expect(view.getByText(/split into 2 separate shipments: SHP-1 \(this one\), SHP-2/)).toBeTruthy()
    expect(view.queryByText(/order lines$/)).toBeNull()
  })

  it('shows the warranty decision, every check, the installation and a hidden technician name', async () => {
    replies = [{ body: warranty }]
    mount()
    await ask('Is this failed part covered by warranty?')
    const view = within(await screen.findByRole('region', { name: 'Warranty result' }))
    expect(view.getByText('Every applicable warranty condition holds.')).toBeTruthy()
    expect(view.getByText('The part is a verified catalogue part')).toBeTruthy()
    expect(view.getByText('missing record')).toBeTruthy()
    expect(view.getByText(/Dealer One \(demo\) · authorised/)).toBeTruthy()
    expect(view.getByText(/\(name not shown to your role\)/)).toBeTruthy()
    expect(view.getByText(/REP-1/)).toBeTruthy()
  })

  it('shows the evidence path, confidence and source records in the evidence area', async () => {
    replies = [{ body: warranty }]
    mount()
    await ask('Is this failed part covered by warranty?')
    await screen.findByRole('region', { name: 'Warranty result' })
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/ }))
    const view = within(await screen.findByRole('region', { name: 'Evidence and provenance' }))
    expect(view.getByRole('list', { name: 'Evidence path' }).textContent).toMatch(/Part.*PRT-1.*FITS.*Fitment.*F-1/)
    expect(view.getByText(/not real-world verified/)).toBeTruthy()
    expect(view.getByText(/Hidden for the end customer view: technician.name/)).toBeTruthy()
    expect(view.getByText(/1 source records/)).toBeTruthy()
  })

  it('answers a clarification option by asking the same question again with the chosen reference', async () => {
    const clar = response({
      intent: 'WARRANTY', status: 'REQUIRES_CLARIFICATION', answer: answer('Which machine do you mean?', [{ ...section('WARRANTY', 'REQUIRES_CLARIFICATION', 'Which machine do you mean?'), status: 'REQUIRES_CLARIFICATION' }]),
      clarification: { domain: 'WARRANTY', question: 'Which machine do you mean?', options: [{ machine_instance_id: 'MI-1', serial_number: 'S-1' }, { machine_instance_id: 'MI-2', serial_number: 'S-2' }] },
      contexts: {},
    })
    replies = [{ body: clar }, { body: warranty }]
    mount()
    await ask('Is this part under warranty?')
    const options = await screen.findAllByRole('button', { name: 'Use this' })
    expect(options).toHaveLength(2)
    fireEvent.click(options[1])
    await screen.findByRole('region', { name: 'Warranty result' })
    expect(calls[1].body).toEqual({ message: 'Is this part under warranty?', state: { machine_instance_id: 'MI-2' } })
  })

  it('says plainly when access is refused and shows nothing from the record', async () => {
    replies = [{ status: 403, body: { error: { code: 'forbidden', message: 'You do not have access to this record.' } } }]
    mount()
    await ask('Where is SHP-9?')
    expect((await screen.findByRole('alert')).textContent).toBe('You do not have access to that record.')
    expect(screen.queryByRole('region', { name: 'Shipment result' })).toBeNull()
  })

  it('lets an order processor view as a dealer and sends the dealer id with the request', async () => {
    replies = [{ body: logistics() }]
    mount('ORDER_PROCESSOR')
    fireEvent.change(await screen.findByRole('combobox', { name: /View as/ }), { target: { value: 'DEALER' } })
    fireEvent.change(screen.getByLabelText('Dealer id'), { target: { value: 'DLR-004' } })
    await ask('Where is SHP-1?')
    await screen.findByRole('region', { name: 'Shipment result' })
    expect(calls[0].body).toMatchObject({ user_role: 'DEALER', dealer_id: 'DLR-004' })
  })

  it('never sends a role for a customer', async () => {
    replies = [{ body: discovery }]
    mount()
    await ask('Find a hydraulic pump for M-1')
    await screen.findByRole('region', { name: 'Part discovery result' })
    expect(Object.keys(calls[0].body ?? {})).not.toContain('user_role')
  })

  it('runs the direct journeys through the same APIs', async () => {
    replies = [{ body: logisticsCtx() }]
    mount()
    fireEvent.click(await screen.findByRole('tab', { name: /Shipment/ }))
    fireEvent.change(screen.getByLabelText('Shipment or order number'), { target: { value: 'ord-net-0001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Track' }))
    await screen.findByRole('region', { name: 'Shipment result' })
    expect(calls[0]).toEqual({ url: '/commerce/logistics/context', body: { order_id: 'ORD-NET-0001' } })
  })
})
