// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Me, OrderDetail } from '../../api/orders'
import OrderDetailPage from '../../pages/OrderDetailPage'
import { SessionProvider } from '../../store/session'

const jane: Me = {
  id: 'U-JANE',
  name: 'Jane (demo)',
  email: 'j@x.example',
  role: 'ORDER_PROCESSOR',
  customer: null,
  permissions: ['orders.read', 'orders.update_status'],
}

const STAGES = [
  'Order',
  'Allocation',
  'Fulfilment',
  'Shipment',
  'Tracking',
  'Dealer Service',
  'Completed',
]
const stages = (states: string[]) =>
  STAGES.map((stage, i) => ({ stage, state: states[i] as 'done' }))

const direct = (over: Partial<OrderDetail> = {}): OrderDetail => ({
  order_id: 'HCME-ORD-000007',
  order_date: '2026-10-05',
  status: 'ALLOCATED',
  status_label: 'Stock allocated',
  channel: 'DIRECT_ORDER',
  currency: 'EUR',
  data_status: 'USER_PROVIDED',
  totals: {
    subtotal_ex_vat: null,
    shipping_ex_vat: null,
    vat_amount: null,
    total_incl_vat: null,
    note: null,
  },
  lines: [
    {
      line_no: 1,
      part_id: 'P1',
      part_number: 'AB-1',
      name: 'Part AB-1',
      quantity: 2,
      machine: 'M-1',
      unit_price_eur: null,
      line_total_eur: null,
      fitment: [],
      availability_state: 'IN_STOCK',
      in_stock_units: 18,
      fulfilment: 'Allocated from Depot B (demo)',
      allocation_status: 'RESERVED',
      reserved_quantity: 2,
      warehouses: [
        {
          warehouse_id: 'WH-B',
          name: 'Depot B (demo)',
          city: 'Lingen',
          available: 18,
          stock_status: 'IN_STOCK',
          data_status: 'SYNTHETIC_DEMO',
        },
      ],
    },
  ],
  shipments: [],
  payment: 'No payment is taken in this demo store and none has been taken.',
  history: [
    {
      sequence: 1,
      status: 'NEW',
      status_label: 'Order placed',
      previous_status: 'NEW',
      action: 'order_placed',
      occurred_at: '2026-10-05T09:00:00+00:00',
      by: 'Anna (demo)',
      role: 'END_USER',
      recorded: 'USER_PROVIDED',
    },
    {
      sequence: 2,
      status: 'ALLOCATED',
      status_label: 'Stock allocated',
      previous_status: 'NEW',
      action: 'allocate',
      occurred_at: '2026-10-05T09:00:01+00:00',
      by: 'System',
      role: 'SYSTEM',
      recorded: 'USER_PROVIDED',
    },
  ],
  requester: {
    name: 'Sam Buyer',
    email: 'sam@buyer.example',
    phone: '+31 20 555 0100',
    company: 'Buyer Company B.V.',
  },
  delivery: {
    ship_to_id: 'SHT-1',
    street: 'Hafenstrasse 1',
    city: 'Hamburg',
    postal_code: '20457',
    country_code: 'DE',
  },
  receiver: { name: 'Rita Receiver', phone: '+49 40 555 0199' },
  dealer: {
    dealer_id: 'DLR-1',
    name: 'Dealer One (demo)',
    city: 'Hamburg',
    country_code: 'DE',
    dealer_type: 'AUTHORISED_DEALER',
  },
  dealer_service_required: true,
  fulfilment: {
    depot: { warehouse_id: 'WH-B', name: 'Depot B (demo)', city: 'Lingen', country_code: 'DE' },
    allocation_status: 'RESERVED',
    allocation_updated_at: '2026-10-05T09:00:01+00:00',
    lines: [
      {
        part_number: 'AB-1',
        quantity: 2,
        reserved_quantity: 2,
        allocation_status: 'RESERVED',
        machine: 'M-1',
      },
    ],
  },
  transport: {
    route_id: 'R-STD',
    option_code: 'STANDARD_ROAD_EU',
    mode: 'ROAD',
    distance_km: 100,
    estimated_days: 2,
    estimate_basis: 'ESTIMATED',
    data_status: 'SYNTHETIC_DEMO',
    freight_estimate: {
      amount: 12.5,
      currency: 'EUR',
      data_status: 'SYNTHETIC_DEMO_ESTIMATE',
      label: 'Synthetic demo freight estimate, not a price',
    },
  },
  cost: {
    part_cost: null,
    transport_cost: null,
    total: null,
    currency: 'EUR',
    status: 'NOT_AVAILABLE',
    note: 'Part cost and transportation cost are not available.',
  },
  service: null,
  provenance: {
    order: 'USER_PROVIDED',
    transport: 'SYNTHETIC_DEMO',
    tracking: 'SYNTHETIC_DEMO',
    inventory: 'SYNTHETIC_DEMO',
  },
  stages: stages(['done', 'done', 'current', 'pending', 'pending', 'pending', 'pending']),
  actions: [
    {
      action: 'start_fulfilment',
      label: 'Start fulfilment',
      allowed: true,
      reason: null,
      to_status: 'FULFILMENT_PENDING',
      note: null,
    },
    {
      action: 'release_allocation',
      label: 'Release allocation',
      allowed: true,
      reason: null,
      to_status: 'ALLOCATION_RELEASED',
      note: null,
    },
    {
      action: 'cancel',
      label: 'Cancel order',
      allowed: true,
      reason: null,
      to_status: 'CANCELLED',
      note: null,
    },
  ],
  ...over,
})

let posted: { url: string; body: Record<string, string> }[] = []

function mount(
  me: Me,
  order: OrderDetail,
  path = '/orders/HCME-ORD-000007',
  afterAction?: OrderDetail,
) {
  posted = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/me')) return new Response(JSON.stringify(me))
      if (url.endsWith('/actions')) {
        posted.push({ url, body: JSON.parse(init!.body as string) })
        return new Response(JSON.stringify(afterAction ?? order))
      }
      if (url.includes('/orders/')) return new Response(JSON.stringify(order))
      return new Response('{}', { status: 404 })
    }),
  )
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )
}

describe('direct order lifecycle screen', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows the lifecycle as the server recorded it, with every stage and the order details', async () => {
    mount(jane, direct())
    expect(await screen.findByRole('heading', { name: 'HCME-ORD-000007' })).toBeTruthy()
    const stageList = within(screen.getByRole('region', { name: 'Order progress' }))
    expect(stageList.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Orderdone',
      'Allocationdone',
      'Fulfilmentin progress',
      'Shipmentto do',
      'Trackingto do',
      'Dealer Serviceto do',
      'Completedto do',
    ])
    expect(screen.getByText('Sam Buyer')).toBeTruthy()
    expect(screen.getAllByText('Buyer Company B.V.').length).toBeGreaterThan(0)
    expect(screen.getByText(/Hafenstrasse 1, 20457 Hamburg, DE/)).toBeTruthy()
    expect(screen.getByText('Rita Receiver')).toBeTruthy()
    expect(screen.getByText('Dealer One (demo)')).toBeTruthy() // ship-to, receiver, dealer and depot are four different things
    expect(screen.getAllByText(/Depot B \(demo\)/).length).toBeGreaterThan(0)
    expect(screen.getByText(/M-1/)).toBeTruthy()
    expect(screen.getByText('2 reserved')).toBeTruthy()
    const cost = within(screen.getByRole('heading', { name: 'Cost' }).closest('section')!)
    expect(cost.getAllByText('Not available').length).toBe(3)
    expect(screen.getAllByText('Synthetic demo data').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toMatch(/purchase request|quote request/i)
    cleanup() // once the line has shipped, its stock is no longer described as reserved
    mount(jane, direct({ lines: [{ ...direct().lines[0], allocation_status: 'SHIPPED' }] }))
    expect(await screen.findByRole('heading', { name: 'HCME-ORD-000007' })).toBeTruthy()
    expect(screen.queryByText('2 reserved')).toBeNull()
  })

  it('offers only the actions the server says are valid, and sends the action with the status the user saw', async () => {
    const after = direct({
      status: 'FULFILMENT_PENDING',
      status_label: 'Fulfilment pending',
      actions: [
        {
          action: 'begin_fulfilling',
          label: 'Begin picking and packing',
          allowed: true,
          reason: null,
          to_status: 'FULFILLING',
          note: null,
        },
      ],
    })
    mount(jane, direct(), undefined, after)
    await screen.findByRole('heading', { name: 'HCME-ORD-000007' })
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(
      expect.arrayContaining(['Start fulfilment', 'Release allocation', 'Cancel order']),
    )
    expect(screen.queryByRole('button', { name: 'Mark delivered' })).toBeNull() // not offered: not a valid next step
    fireEvent.click(screen.getByRole('button', { name: 'Start fulfilment' }))
    await waitFor(() => expect(posted.length).toBe(1))
    expect(posted[0].url).toContain('/orders/HCME-ORD-000007/actions')
    expect(posted[0].body).toEqual({ action: 'start_fulfilment', expected_status: 'ALLOCATED' })
    expect(await screen.findByRole('button', { name: 'Begin picking and packing' })).toBeTruthy() // the screen now shows what the server returned
    expect(screen.queryByRole('button', { name: 'Start fulfilment' })).toBeNull()
  })
})
