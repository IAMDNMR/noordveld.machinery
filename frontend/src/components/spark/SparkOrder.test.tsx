// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { SparkHome } from './SparkHome'
import type { OrderResponse } from '../../api/sparkOrder'

const STAGES = [
  'part',
  'quantity',
  'delivery',
  'fulfilment',
  'dealer',
  'details',
  'review',
  'placed',
]
const step = (stage: string, over: Partial<OrderResponse> = {}): OrderResponse => ({
  stage,
  message: `Message for ${stage}`,
  blocked: false,
  handled: true,
  stages: STAGES.map((id, i) => ({
    id,
    label: id,
    state: i < STAGES.indexOf(stage) ? 'done' : id === stage ? 'current' : 'todo',
  })),
  part: {
    part_number: 'AB-1',
    name: 'Hydraulic hose',
    category: null,
    price: { amount: 25, currency: 'EUR' },
    part_status: 'VERIFIED',
    availability_state: 'IN_STOCK',
    depot_stock_total: 20,
    fits: [],
    supplier: null,
  },
  ask: null,
  options: null,
  hidden_options: 0,
  explanation: null,
  alternatives: [],
  reasons: [],
  summary: null,
  order: null,
  warnings: [],
  prefilled: [],
  profile_offer: null,
  slots: { part_id: 'P-AB-1' },
  ...over,
})
const summary = {
  part: { part_number: 'AB-1', name: 'Hydraulic hose' },
  quantity: 2,
  machine: null,
  destination: {
    city: 'Hamburg',
    street: 'Kai 1',
    postal_code: '20457',
    country_code: 'DE',
    receiving_hours: null,
  },
  depot: { name: 'Depot B', city: 'Lingen' },
  transport: { name: 'Standard', estimated_days: 2, arrives_by: '2026-11-02' },
  dealer: { name: 'Dealer One', city: 'Hamburg' },
  dealer_installation: false,
  contact: { name: 'Anna', email: 'anna@example.com' },
  cost: { part_cost: 50, transport_cost: 12.5, total: 62.5 },
  total: 62.5,
  cost_note: 'Demo estimate.',
  checks: { needed_by: null, timing: 'As soon as possible' },
}

const mount = (
  replies: (body: Record<string, unknown>, calls: Record<string, unknown>[]) => Response,
  chat: (body: Record<string, unknown>) => Response = () => json({}, 404),
) => {
  const calls: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/spark/voice/status'))
        return new Response(JSON.stringify({ enabled: false, reason: 'off' }))
      if (url.endsWith('/spark/order')) {
        const body = JSON.parse(String(init?.body))
        calls.push(body)
        return replies(body, calls)
      }
      if (url.endsWith('/spark/conversation')) {
        const body = JSON.parse(String(init?.body))
        calls.push({ chat: body })
        return chat(body)
      }
      return new Response('{}', { status: 404 })
    }),
  )
  render(
    <MemoryRouter initialEntries={['/spark/chat?order=P-AB-1&qty=2']}>
      <SparkHome />
    </MemoryRouter>,
  )
  return calls
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })

beforeEach(() => {
  sessionStorage.clear()
  Element.prototype.scrollTo = vi.fn()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('"Order this part" starts the journey with the part and quantity, shows progress, and places the order only after explicit confirmation', async () => {
  const calls = mount((body, seen) => {
    if (body.confirm && seen.filter((call) => call.confirm).length === 1)
      return json(
        { error: { code: 'availability', message: 'The chosen depot cannot supply this order.' } },
        409,
      )
    if (body.confirm)
      return json(
        step('placed', {
          profile_offer: { preferred_machine: 'M-1', ship_to_id: 'SHT-1' },
          message: 'Your order NM-ORD001 is placed.',
          order: { order_id: 'NM-ORD001', status_label: 'New', cost: summary.cost },
        }),
      )
    if (body.patch && (body.patch as Record<string, unknown>).dealer_id)
      return json(
        step('review', {
          summary,
          ask: {
            field: null,
            kind: 'confirm',
            question: 'Please check the summary.',
            choices: [
              { label: 'Place order', patch: {}, detail: null, recommended: false, confirm: true },
            ],
            fields: [],
          },
        }),
      )
    return json(
      step('dealer', {
        ask: {
          field: null,
          kind: 'choice',
          question: 'Which dealer?',
          choices: [
            {
              label: 'Dealer One — Hamburg',
              patch: { dealer_id: 'DLR-1' },
              detail: null,
              recommended: true,
              confirm: false,
            },
          ],
          fields: [],
        },
        slots: { part_id: 'P-AB-1', quantity: 2 },
      }),
    )
  })
  await screen.findByText('Message for dealer')
  expect(calls[0]).toMatchObject({ slots: { part_id: 'P-AB-1' }, patch: { quantity: 2 } })
  expect(screen.getByRole('list', { name: 'Order progress' })).toBeTruthy()
  expect(screen.getByText('Hydraulic hose', { exact: false })).toBeTruthy()
  expect(screen.queryByText(/is placed/)).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: /Dealer One — Hamburg/ }))
  await screen.findByRole('region', { name: 'Order summary' })
  expect(screen.queryByText(/is placed/)).toBeNull() // reviewing is not ordering
  expect(calls).toHaveLength(2)

  fireEvent.click(screen.getByRole('button', { name: /Place order/ }))
  // a failed attempt says nothing was ordered and shows no order; the retry reuses the same idempotency key
  await screen.findByRole('alert')
  expect(screen.queryByText(/is placed/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Place order/ }))
  await screen.findByRole('heading', { name: 'Order NM-ORD001 is placed' })
  expect(calls[3].idempotency_key).toBe(calls[2].idempotency_key)
  const confirm = calls[3]
  expect(confirm).toMatchObject({ confirm: true, reviewed_total: 62.5 })
  expect(String(confirm.idempotency_key).length).toBeGreaterThanOrEqual(8)
  expect(screen.getByRole('link', { name: 'View order' }).getAttribute('href')).toBe(
    '/orders/NM-ORD001',
  )
  // saving to the profile is offered, never automatic
  expect(screen.getByRole('button', { name: /save to my profile/i })).toBeTruthy()
  expect(calls).toHaveLength(4)
}, 15_000) // four rendered steps: allow for a busy machine

it('a question Spark answers mid-order keeps the order open: same slots, same step, and "order it" continues instead of restarting', async () => {
  const quantityAsk = {
    field: 'quantity',
    kind: 'number' as const,
    question: 'How many of AB-1 do you need?',
    choices: [],
    fields: [],
  }
  const slots = { part_id: 'P-AB-1', machine: 'M-1', needed_by: '2026-10-30' }
  const calls = mount(
    (body) =>
      body.message === 'Who supplies it?'
        ? json(step('quantity', { handled: false, slots }))
        : json(step('quantity', { ask: quantityAsk, slots })),
    () =>
      json({
        message: 'Example Supply is the recorded supplier.',
        context: 'ctx-1',
        view: 'answer',
        intelligence: null,
        shopping: null,
        account: null,
        sign_in_required: false,
        warnings: [],
        steps: [],
        order_part: { part_id: 'P-AB-1', label: 'AB-1', patch: {} },
      }),
  )
  await screen.findByText(/Needed by/)
  expect(screen.getByRole('status', { name: 'Current order' }).textContent).toContain('AB-1')
  expect(screen.getByText('Fits M-1')).toBeTruthy() // the order card shows what is already chosen
  const box = screen.getByRole('textbox', { name: 'Message Spark' })
  fireEvent.change(box, { target: { value: 'Who supplies it?' } })
  fireEvent.submit(box.closest('form')!)
  await screen.findByText('Example Supply is the recorded supplier.')
  // Spark was told which part is being ordered, so 'it' means that part
  expect(calls.find((call) => call.chat)).toMatchObject({
    chat: { order_part: { part_id: 'P-AB-1', label: 'AB-1' } },
  })
  // the same part: the order continues with its slots, at its current step
  await vi.waitFor(() => expect(calls.at(-1)).toEqual({ slots }))
  expect(screen.getByRole('status', { name: 'Current order' }).textContent).toContain('Next: Quantity')
  // the quantity is asked once, on the order card, with a stepper
  fireEvent.click(screen.getByRole('button', { name: 'One more' }))
  fireEvent.click(screen.getByRole('button', { name: /Continue to delivery/ }))
  await vi.waitFor(() => expect(calls.at(-1)).toMatchObject({ slots, patch: { quantity: 2 } }))
})
