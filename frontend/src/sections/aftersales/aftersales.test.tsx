// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PartsServicesPage from '../../pages/PartsServicesPage'
import { SessionProvider } from '../../store/session'
import annotation from '../../assets/machines/nv-4500/hotspots.json'

// Fixtures stand in for the backend: the page must show what the API returns and invent nothing.
const MODEL = annotation.machine
const [confirmed, unconfirmed] = annotation.hotspots.map((h) => h.part)
const part = (no: string, fits: string[], category = 'Hydraulics') => ({ part_id: `P-${no}`, part_number: no, name: `Name of ${no}`, category, subcategory: 'Sub', fitment: fits.map((m) => ({ model_code: m, fitment_status: 'CONFIRMED' })), price: null, availability: null })
const PARTS = [part(confirmed, [MODEL]), part(unconfirmed, ['OTHER-1'], 'Filtration')]
const FILTERS = { categories: [{ category_id: 'C1', name: 'Hydraulics', part_count: 1 }, { category_id: 'C2', name: 'Filtration', part_count: 1 }, { category_id: 'C3', name: 'Empty', part_count: 0 }], machines: [{ machine_id: 'M1', model_code: MODEL, name: 'Loader', machine_type: 'Loader', origin_plant: null, country: null, part_count: 1 }], availability: [] }

let signedIn = false
beforeEach(() => {
  signedIn = false
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} unobserve() {} })
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }))
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.replace('/api/v1', '').split('?')[0]
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
    if (path === '/me') return signedIn ? json({ id: 'U1', name: 'U', email: 'u@x', role: 'END_USER', customer: 'C', permissions: [] }) : json({ error: { code: 'not_signed_in', message: 'x' } }, 401)
    if (path === '/parts') return json({ items: url.includes('q=') || url.includes('machine=') ? [PARTS[0]] : PARTS, total: url.includes('q=') || url.includes('machine=') ? 1 : 2, offset: 0, limit: 60 })
    if (path === '/catalogue/filters') return json(FILTERS)
    if (path === '/site/overview') return json({ machines: [{ model: MODEL, slug: MODEL.toLowerCase(), machine_id: 'M1', name: 'Loader', full_name: 'Loader', family: null, brand: 'Brand A', parts: [], attachments: [] }], plants: [], families: [], part_count: 2, part_categories: [] })
    if (path === '/intelligence/kpis') return json({ parts: 2, machines: 1, fitments: 2, suppliers: 1, dealers: 1, relationships: 10, nodes: 10, synthetic_nodes: 9 })
    if (path === '/orders') return json([{ order_id: 'O-1', order_date: '2026-10-01', status: 'ALLOCATED', status_label: 'Allocated', parts: [], fits: [], total: null, currency: 'EUR', fulfilment: 'Allocated from stock', data_status: 'SYNTHETIC_DEMO' }])
    return json({ error: { code: 'x', message: 'unexpected' } }, 500)
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const mount = () => render(<MemoryRouter><SessionProvider><PartsServicesPage /></SessionProvider></MemoryRouter>)

describe('Parts & Services page', () => {
  it('shows the headline and both actions at once, pointing at the Parts Portal and the machine finder', async () => {
    mount()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Every Machine Has a Story.')
    expect(screen.getByRole('link', { name: 'Explore Parts' }).getAttribute('href')).toBe('/parts-store')
    expect(screen.getByRole('link', { name: /Find the Right Part/ }).getAttribute('href')).toBe('#find-parts')
  })

  it('marks a component on the machine only when the catalogue confirms its fitment for that machine', async () => {
    const { container } = mount()
    await waitFor(() => expect(container.querySelectorAll('.as-spot').length).toBe(1))
    expect(container.querySelector('.as-ident')?.textContent).toContain(confirmed)
    expect([...container.querySelectorAll('.as-plate')].map((p) => p.textContent)).toEqual([confirmed])
  })

  it('every quick-access destination is a real route or a section on the page', async () => {
    mount()
    const quick = within(screen.getByRole('heading', { name: 'Everything aftermarket in one place.' }).closest('section') as HTMLElement)
    const hrefs = quick.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['/parts-store', '/parts-intelligence', '/parts-store?sort=name', '#find-parts', '#dealers', '#service'])
    for (const id of ['find-parts', 'dealers', 'service']) expect(document.getElementById(id)).not.toBeNull()
  })

  it('lists only categories the catalogue holds, linked to the filtered store view', async () => {
    mount()
    const cats = within(await screen.findByRole('heading', { name: 'Every system of the machine.' }).then((h) => h.closest('section') as HTMLElement))
    await waitFor(() => expect(cats.getAllByRole('link').length).toBe(2))
    expect(cats.queryByText('Empty')).toBeNull()
    expect(cats.getAllByRole('link')[0].getAttribute('href')).toBe('/parts-store?category=Hydraulics')
  })

  it('sends a question to Parts Intelligence instead of the part search', async () => {
    mount()
    fireEvent.change(screen.getByLabelText('Search parts'), { target: { value: 'Which machines use this?' } })
    expect(await screen.findByText(/That reads as a question/)).toBeTruthy()
  })

  it('keeps dealers and orders behind sign-in, and shows the recorded order status once signed in', async () => {
    const first = mount()
    expect(await screen.findByText(/Dealer records are available to signed-in users/)).toBeTruthy()
    expect(screen.getByText(/Your orders are visible only to you/)).toBeTruthy()
    first.unmount()
    signedIn = true
    mount()
    expect(await screen.findByText('Allocated')).toBeTruthy()
    expect(screen.getByText(/demo record/)).toBeTruthy()
  })

  it('labels the service steps that are not available', async () => {
    mount()
    expect(screen.getByText('Not available')).toBeTruthy()
    expect(screen.getByText(/Service booking and completion are not connected/)).toBeTruthy()
  })
})
