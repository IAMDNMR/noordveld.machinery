// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PartSummary, Quote } from '../../api'
import { CartProvider } from '../../store/CartContext'
import { CartContents } from './CartContents'

const KEY = 'noordveld-parts-cart-v2'

const summary = (id: string, number: string, status: string): PartSummary => ({
  part_id: id, part_number: number, name: `Part ${number}`, category: 'Cat', subcategory: null, fitment: [], price: null,
  availability: { state: 'IN_STOCK', orderable: false, part_status: status, total_available: 5, data_status: 'SYNTHETIC_DEMO' },
})

// What the server returns for a cart whose three lines are all non-verified: nothing priced, every line rejected with its status.
const quote: Quote = {
  lines: [],
  rejected: [
    ['P1', 'ID-REQ-1', 'IDENTIFICATION_REQUIRED', 'Identification required'],
    ['P2', 'AMBIG-2', 'AMBIGUOUS', 'Ambiguous'],
    ['P3', 'UNVER-3', 'UNVERIFIED', 'Unverified'],
  ].map(([id, number, status, label]) => ({ part: summary(id, number, status), quantity: 2, status, status_label: label, reason: 'It must be identified before ordering.' })),
  unknown_part_ids: [], subtotal: null, unpriced_part_ids: [], order_placement_available: false, note: 'Prepared quote only.',
}

describe('cart restored from browser storage (QA fix 1)', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('re-validates a hand-edited cart on load and shows no price for non-verified parts', async () => {
    localStorage.setItem(KEY, JSON.stringify([{ partId: 'P1', qty: 2 }, { partId: 'P2', qty: 2 }, { partId: 'P3', qty: 2 }]))
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(quote), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<MemoryRouter><CartProvider><CartContents /></CartProvider></MemoryRouter>)
    await waitFor(() => expect(screen.getAllByText(/Cannot be ordered/).length).toBe(3))

    // the stored lines were sent to the server for validation, not trusted
    expect(JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string).items.map((i: { part_id: string }) => i.part_id)).toEqual(['P1', 'P2', 'P3'])
    expect(screen.getByText(/Cannot be ordered: Identification required/)).toBeTruthy()
    expect(screen.getByText(/Cannot be ordered: Ambiguous/)).toBeTruthy()
    expect(screen.getByText(/Cannot be ordered: Unverified/)).toBeTruthy()
    expect(container.textContent).not.toMatch(/€|EUR|\d+\.\d{2}/) // no price anywhere
    expect(container.querySelector('.cart__grand')?.textContent).toBe('SubtotalNot available')
    expect(container.querySelectorAll('.cline__total').length).toBe(0)
  })
})
