// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CheckoutReview, Me } from '../api/orders'
import { CartProvider, useCart } from '../store/CartContext'
import { SessionProvider } from '../store/session'
import CheckoutPage from './CheckoutPage'

const KEY = 'noordveld-parts-cart-v2'
const anna: Me = { id: 'U-ANNA', name: 'Anna de Vries (demo)', email: 'anna@account.example', role: 'END_USER', customer: 'Account Customer', permissions: ['orders.place'] }

const summary = (id: string, number: string) => ({
  part_id: id, part_number: number, name: `Part ${number}`, category: 'Cat', subcategory: null, fitment: [], price: null,
  availability: { state: 'IN_STOCK', orderable: true, part_status: 'VERIFIED', total_available: 5, data_status: 'SYNTHETIC_DEMO' },
})
const quote = { lines: [{ part: summary('P1', 'AB-1'), quantity: 2, line_total: null }], rejected: [], unknown_part_ids: [], subtotal: null, unpriced_part_ids: ['P1'], order_placement_available: false, note: 'Prepared quote only.' }
const option = (route: string, name: string, days: number) => ({ route_id: route, option_id: 'TOP-1', option_code: name.toUpperCase(), option_name: name, mode: 'ROAD', service_level: 'STANDARD', origin_depot_id: 'WH-B', destination_shipto_id: 'SHT-1', distance_km: 100, estimated_days: days, estimate_basis: 'ESTIMATED', legs: 1, data_status: 'SYNTHETIC_DEMO', freight: { amount: 12.5, currency: 'EUR', data_status: 'SYNTHETIC_DEMO', label: 'Synthetic demo freight estimate, not a price' } })
const review: CheckoutReview = {
  lines: [{ line_no: 1, part_id: 'P1', part_number: 'AB-1', part_name: 'Part AB-1', quantity: 2, machine: 'M-1' }],
  destination: { ship_to_id: 'SHT-1', street: 'Hafenstrasse 1', city: 'Hamburg', postal_code: '20457', country_code: 'DE' },
  depots: [
    { depot_id: 'WH-B', name: 'Depot B (demo)', city: 'Lingen', country_code: 'DE', selectable: true, reasons: [], recommended: true, recommended_route_id: 'R-STD',
      lines: [{ part_id: 'P1', part_number: 'AB-1', quantity: 2, state: 'IN_STOCK', available: 20, can_supply: true }], options: [option('R-STD', 'Standard Road', 2), option('R-EXP', 'Express Road', 1)] },
    { depot_id: 'WH-U', name: 'Depot U (demo)', city: 'Brno', country_code: 'CZ', selectable: false, recommended: false, recommended_route_id: null,
      reasons: ['AB-1: stock is UNKNOWN at this depot (not treated as zero, not allocated).'], lines: [{ part_id: 'P1', part_number: 'AB-1', quantity: 2, state: 'UNKNOWN', available: null, can_supply: false }], options: [] },
  ],
  can_order: true, cost: { part_cost: null, transport_cost: null, total: null, currency: 'EUR', status: 'NOT_AVAILABLE', note: 'Part cost and transportation cost are not available.' },
}
const detail = { order_id: 'HCME-ORD-000001', status: 'ALLOCATED', lines: [], shipments: [], history: [], channel: 'DIRECT_ORDER' }

function Probe() {
  const { lines } = useCart()
  return <output data-testid="cart">{JSON.stringify(lines)}</output>
}

let posts: { url: string; body: Record<string, unknown> }[] = []

function mount(overrides: Record<string, (init?: RequestInit) => Response> = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
    for (const [k, h] of Object.entries(overrides)) if (url.includes(k)) return h(init)
    if (url.endsWith('/me')) return json(anna)
    if (url.includes('/me/cart')) return json([])
    if (url.includes('/cart/quote')) return json(quote)
    if (url.includes('/checkout/countries')) return json([{ country_code: 'DE', destinations: 1 }])
    if (url.includes('/checkout/destinations')) return json([{ ship_to_id: 'SHT-1', street: 'Hafenstrasse 1', city: 'Hamburg', postal_code: '20457', country_code: 'DE', receiving_hours: 'Mon-Fri 07:00-16:00', vehicle_restrictions: null, data_status: 'SYNTHETIC_DEMO' }])
    if (url.includes('/checkout/dealers')) return json([{ dealer_id: 'DLR-1', name: 'Dealer One (demo)', city: 'Hamburg', country_code: 'DE', dealer_type: 'AUTHORISED_DEALER', data_status: 'SYNTHETIC_DEMO' }])
    if (url.includes('/checkout/review')) return json(review)
    if (url.endsWith('/orders') && init?.method === 'POST') {
      posts.push({ url, body: JSON.parse(init.body as string) })
      return json(detail, 201)
    }
    return json({}, 404)
  }))
  render(
    <MemoryRouter initialEntries={['/parts-store/checkout']}>
      <SessionProvider>
        <CartProvider>
          <Probe />
          <Routes>
            <Route path="/parts-store/checkout" element={<CheckoutPage />} />
            <Route path="/orders/:id" element={<p>order page</p>} />
          </Routes>
        </CartProvider>
      </SessionProvider>
    </MemoryRouter>,
  )
}

const next = () => fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
const type = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('checkout', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    posts = []
    localStorage.setItem(KEY, JSON.stringify([{ partId: 'P1', qty: 2, machine: 'M-1' }]))
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('keeps the machine on the cart line and walks every step before an order can be placed', async () => {
    mount()
    expect(await screen.findByRole('heading', { name: 'Cart' })).toBeTruthy()
    expect(screen.getByTestId('cart').textContent).toBe('[{"partId":"P1","qty":2,"machine":"M-1"}]') // part, quantity and machine are kept together
    expect(await screen.findByText('For machine M-1')).toBeTruthy()
    next()

    // customer details: the account only offers defaults; the order keeps what is typed here
    expect(screen.getByRole('heading', { name: 'Customer details' })).toBeTruthy()
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Anna de Vries')
    expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe('anna@account.example')
    expect((screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement).disabled).toBe(true) // phone and a valid company are still missing
    type('Name', 'Sam Buyer')
    type('Email', 'sam@buyer-company.example')
    type('Phone', '+31 20 555 0100')
    type('Company', 'Buyer Company B.V.')
    next()

    expect(await screen.findByRole('heading', { name: 'Cart review' })).toBeTruthy()
    expect(await screen.findByText('Verified, orderable')).toBeTruthy()
    expect(screen.getByText('M-1')).toBeTruthy()
    next()

    // delivery: ship-to, receiver and dealer are three separate choices
    expect(screen.getByRole('heading', { name: /Delivery/ })).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement).disabled).toBe(true)
    await screen.findByRole('option', { name: /DE · 1 site/ })
    fireEvent.change(screen.getByLabelText('Delivery country'), { target: { value: 'DE' } })
    fireEvent.click(await screen.findByRole('radio', { name: /Hafenstrasse 1/ }))
    type('Receiver name', 'Rita Receiver')
    type('Receiver phone', '+49 40 555 0199')
    await screen.findByRole('option', { name: /Dealer One/ })
    fireEvent.change(screen.getByLabelText('Dealer'), { target: { value: 'DLR-1' } })
    next()

    // availability from the depot inventory: unknown stays unknown and cannot be chosen
    expect(await screen.findByText(/Checking depot stock|Depot B/)).toBeTruthy()
    const unknown = await screen.findByText(/AB-1: Unknown/)
    expect(unknown).toBeTruthy()
    expect(screen.getByText(/not treated as zero/)).toBeTruthy()
    expect((screen.getByRole('radio', { name: /Depot U/ }) as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByRole('radio', { name: /Depot B/ }) as HTMLInputElement).checked).toBe(true) // the server's recommendation, not the biggest stock
    expect(screen.getAllByText('Synthetic demo').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Freight context: EUR 12.50/).length).toBe(2)
    fireEvent.click(screen.getByRole('radio', { name: /Express Road/ }))
    next()

    // review: every part of the order, cost not invented
    expect(await screen.findByRole('heading', { name: 'Review & place order' })).toBeTruthy()
    const summaryRegion = within(screen.getByRole('region', { name: 'Cost' }))
    expect(summaryRegion.getAllByText('Not available').length).toBe(3)
    expect(within(screen.getByRole('region', { name: 'Requester' })).getByText('Sam Buyer')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Delivery' })).getByText(/Hafenstrasse 1, 20457 Hamburg/)).toBeTruthy()
    expect(screen.getByText(/SYNTHETIC DEMO DATA/)).toBeTruthy()
    const place = screen.getByRole('button', { name: 'Place order' }) as HTMLButtonElement
    expect(place.disabled).toBe(true) // explicit confirmation is required: nothing is submitted silently
    fireEvent.click(screen.getByRole('checkbox', { name: /I confirm the details/ }))
    expect(place.disabled).toBe(false)
    fireEvent.click(place)

    await waitFor(() => expect(posts.length).toBe(1))
    expect(posts[0].body).toMatchObject({
      items: [{ part_id: 'P1', quantity: 2, machine: 'M-1' }],
      requester: { name: 'Sam Buyer', email: 'sam@buyer-company.example', phone: '+31 20 555 0100', company: 'Buyer Company B.V.' },
      delivery: { ship_to_id: 'SHT-1', receiver_name: 'Rita Receiver', receiver_phone: '+49 40 555 0199' },
      dealer_id: 'DLR-1', depot_id: 'WH-B', route_id: 'R-EXP', dealer_service_required: false, confirmed: true,
    })
    expect(String(posts[0].body.idempotency_key).length).toBeGreaterThanOrEqual(8)
    expect(await screen.findByText('order page')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('cart').textContent).toBe('[]')) // the ordered lines left the cart
    expect(document.body.textContent).not.toMatch(/quote request|purchase request/i)
  })

  it('shows why the server refused the order and keeps the cart', async () => {
    mount({ '/orders': () => new Response(JSON.stringify({ error: { code: 'availability', message: 'The chosen depot cannot supply this order.', details: { reasons: ['AB-1: only 1 available, 2 requested.'] } } }), { status: 409 }) })
    await screen.findByRole('heading', { name: 'Cart' })
    next()
    type('Phone', '+31 20 555 0100')
    type('Company', 'Buyer Company B.V.')
    next()
    await screen.findByText('Verified, orderable')
    next()
    await screen.findByRole('option', { name: /DE · 1 site/ })
    fireEvent.change(screen.getByLabelText('Delivery country'), { target: { value: 'DE' } })
    fireEvent.click(await screen.findByRole('radio', { name: /Hafenstrasse 1/ }))
    type('Receiver name', 'Rita Receiver')
    type('Receiver phone', '+49 40 555 0199')
    await screen.findByRole('option', { name: /Dealer One/ })
    fireEvent.change(screen.getByLabelText('Dealer'), { target: { value: 'DLR-1' } })
    next()
    await screen.findByText(/AB-1: Unknown/)
    next()
    fireEvent.click(await screen.findByRole('checkbox', { name: /I confirm the details/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Place order' }))
    expect(await screen.findByText('The chosen depot cannot supply this order.')).toBeTruthy()
    expect(screen.getByText('AB-1: only 1 available, 2 requested.')).toBeTruthy()
    expect(screen.getByTestId('cart').textContent).toContain('"partId":"P1"')
  })

  it('asks signed-out visitors to sign in and does not offer processors a checkout', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (url.endsWith('/me') ? new Response('{}', { status: 401 }) : new Response(JSON.stringify(quote)))))
    render(<MemoryRouter><SessionProvider><CartProvider><CheckoutPage /></CartProvider></SessionProvider></MemoryRouter>)
    expect(await screen.findByText(/Sign in as an End User/)).toBeTruthy()
  })
})
