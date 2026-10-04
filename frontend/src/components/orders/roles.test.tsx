// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Me, OrderDetail, OrderRow } from '../../api/orders'
import { Nav } from '../Nav'
import OrderDetailPage from '../../pages/OrderDetailPage'
import OrdersPage from '../../pages/OrdersPage'
import { SessionProvider } from '../../store/session'

const anna: Me = { id: 'U-ANNA', name: 'Anna (demo)', email: 'a@x.example', role: 'END_USER', customer: 'Customer One', permissions: ['orders.read_own'] }
const jane: Me = { id: 'U-JANE', name: 'Jane (demo)', email: 'j@x.example', role: 'ORDER_PROCESSOR', customer: null, permissions: ['orders.read', 'orders.update_status'] }
const row = (id: string, status: OrderRow['status'], queue?: OrderRow['queue'], customer?: string): OrderRow => ({
  order_id: id, order_date: '2026-10-01', status, status_label: { NEW: 'Pending review', CONFIRMED: 'Confirmed', PROCESSING: 'Processing', ALLOCATED: 'Allocated', SHIPPED: 'Shipped', DELIVERED: 'Delivered' }[status],
  parts: ['AB-1 × 1'], fits: ['M-1'], total: 50, currency: 'EUR', fulfilment: 'In stock', data_status: 'SYNTHETIC_DEMO', ...(queue ? { queue, customer } : {}),
})
const detail = (processor: boolean, status: OrderDetail['status'] = 'NEW'): OrderDetail => ({
  order_id: 'O-1', order_date: '2026-10-01', status, status_label: status === 'NEW' ? 'Pending review' : 'Confirmed', channel: 'X', currency: 'EUR', data_status: 'SYNTHETIC_DEMO',
  totals: { subtotal_ex_vat: 50, shipping_ex_vat: null, vat_amount: null, total_incl_vat: null, note: null },
  lines: [{ line_no: 1, part_id: 'P1', part_number: 'AB-1', name: 'Part', quantity: 1, unit_price_eur: 50, line_total_eur: 50, fitment: [{ model_code: 'M-1', name: 'Loader', status: 'CONFIRMED' }],
            availability_state: 'IN_STOCK', in_stock_units: 10, fulfilment: 'Available from stock', allocation_status: 'NOT_YET_ALLOCATED',
            ...(processor ? { part_status: 'VERIFIED', orderable: true, price: { list_price_ex_vat: 50, currency: 'EUR', data_status: 'SYNTHETIC_DEMO' },
              warehouses: [{ warehouse_id: 'W1', name: 'Assen', city: 'Assen', available: 10, data_status: 'SYNTHETIC_DEMO' }], suppliers: [{ name: 'Supplier (demo)', lead_time_days: 10, primary: true, data_status: 'SYNTHETIC_DEMO' }],
              evidence: { fitment: 'Noordveld catalogue (FITS relationship)', inventory: 'SYNTHETIC_DEMO', price: 'SYNTHETIC_DEMO', line: 'SYNTHETIC_DEMO' } } : {}) }],
  shipments: [], history: [{ sequence: 1, status: 'NEW', status_label: 'Pending review', previous_status: null, action: null, occurred_at: null, by: null, role: null, recorded: 'SYNTHETIC_DEMO' }],
  payment: 'Order placement and payment are not connected in this demo. No payment has been taken.',
  ...(processor ? { customer: { customer_id: 'C-1', name: 'Customer One', city: 'Zwolle', country_code: 'NL' }, delivery_address: null,
                    next: status === 'NEW' ? { status: 'CONFIRMED' as const, label: 'Confirmed', allowed: true, reason: null } : { status: 'PROCESSING' as const, label: 'Processing', allowed: false, reason: 'Blocked by the graph.' } } : {}),
})

function mount(path: string, me: Me | null, routes: Record<string, (url: string, init?: RequestInit) => Response>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/me')) return me ? new Response(JSON.stringify(me)) : new Response(JSON.stringify({ error: { code: 'not_signed_in', message: 'Sign in' } }), { status: 401 })
    const hit = Object.keys(routes).find((k) => url.endsWith(k))
    return hit ? routes[hit](url, init) : new Response('{}', { status: 404 })
  }))
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Nav />
        <Routes>
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )
}

const navLabels = () => [...document.querySelectorAll('.nav__links a')].map((a) => a.textContent)

describe('roles', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows the End User navigation and a subtle role label', async () => {
    mount('/orders', anna, { '/orders': () => new Response(JSON.stringify([row('O-1', 'NEW')])) })
    await waitFor(() => expect(navLabels()).toEqual(['Machines', 'Parts Store', 'Parts Intelligence', 'Agentic Shopping', 'My Orders']))
    expect(document.querySelector('.nav__bar .nav__role')?.textContent).toBe('End User')
  })

  it('shows the Order Processor navigation', async () => {
    mount('/orders', jane, { '/orders': () => new Response(JSON.stringify([])) })
    await waitFor(() => expect(navLabels()).toEqual(['Orders', 'Parts Intelligence', 'Parts Store', 'Fulfilment', 'Shipments']))
    expect(document.querySelector('.nav__bar .nav__role')?.textContent).toBe('Order Processor')
  })

  it('asks a signed-out visitor to sign in instead of showing orders', async () => {
    mount('/orders', null, {})
    expect(await screen.findByText('Sign in to continue')).toBeTruthy()
    expect(document.querySelector('.ord-restricted a')?.getAttribute('href')).toBe('/sign-in?next=%2Forders')
    expect(navLabels()).toContain('Agentic E-Commerce') // the public navigation
  })

  it('lists the End User’s own orders without customer or queue columns', async () => {
    mount('/orders', anna, { '/orders': () => new Response(JSON.stringify([row('O-1', 'NEW'), row('O-4', 'DELIVERED')])) })
    expect(await screen.findByRole('heading', { name: 'My requests & orders' })).toBeTruthy()
    await screen.findByRole('link', { name: 'O-1' })
    const head = [...document.querySelectorAll('thead th')].map((t) => t.textContent)
    expect(head).not.toContain('Customer')
    expect(screen.getByRole('link', { name: 'O-1' }).getAttribute('href')).toBe('/orders/O-1')
    expect(document.querySelector('.ord-queues')).toBeNull()
  })

  it('gives the Order Processor a queue in sections', async () => {
    mount('/orders?queue=shipped', jane, { '/orders': () => new Response(JSON.stringify([row('O-1', 'NEW', 'pending_review', 'C1'), row('O-9', 'SHIPPED', 'shipped', 'C2')])) })
    expect(await screen.findByRole('heading', { name: 'Order processing' })).toBeTruthy()
    expect((await screen.findByRole('button', { name: /Shipped 1/ })).getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('link', { name: 'O-1' })).toBeNull()
    expect(screen.getByRole('link', { name: 'O-9' })).toBeTruthy()
  })

  it('shows the End User their order without processor controls or internal stock and supplier data', async () => {
    mount('/orders/O-1', anna, { '/orders/O-1': () => new Response(JSON.stringify(detail(false))) })
    expect(await screen.findByRole('heading', { level: 1, name: 'O-1' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Next step' })).toBeNull()
    expect(screen.queryByText(/Supplier \(demo\)/)).toBeNull()
    expect(screen.getByText(/No payment has been taken/)).toBeTruthy()
    expect(screen.getByText(/M-1 · Confirmed fit/)).toBeTruthy()
  })

  it('shows a 403 from the server as "not available for your role"', async () => {
    mount('/orders/O-2', anna, { '/orders/O-2': () => new Response(JSON.stringify({ error: { code: 'forbidden', message: 'Another customer' } }), { status: 403 }) })
    expect(await screen.findByText('Not available for your role')).toBeTruthy()
  })

  it('lets the Order Processor inspect the order and move it one valid step', async () => {
    const posts: unknown[] = []
    mount('/orders/O-1', jane, {
      '/orders/O-1': () => new Response(JSON.stringify(detail(true))),
      '/orders/O-1/status': (_u, init) => {
        posts.push(JSON.parse(String(init?.body)))
        return new Response(JSON.stringify(detail(true, 'CONFIRMED')))
      },
    })
    expect(await screen.findByText(/Supplier \(demo\) · primary · lead time 10 days/)).toBeTruthy()
    expect(screen.getByText(/Assen · 10/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Mark as confirmed' }))
    await waitFor(() => expect(posts).toEqual([{ status: 'CONFIRMED', expected_status: 'NEW' }]))
    expect(await screen.findByText('Blocked by the graph.')).toBeTruthy() // the next step is shown as blocked, with the reason
    expect((screen.getByRole('button', { name: 'Mark as processing' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a rejected transition as the server explains it', async () => {
    mount('/orders/O-1', jane, {
      '/orders/O-1': () => new Response(JSON.stringify(detail(true))),
      '/orders/O-1/status': () => new Response(JSON.stringify({ error: { code: 'invalid_transition', message: 'Pending review cannot move to Delivered.' } }), { status: 409 }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Mark as confirmed' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Pending review cannot move to Delivered.')
  })
})
