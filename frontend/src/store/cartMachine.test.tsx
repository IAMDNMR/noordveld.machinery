// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CartProvider, useCart } from './CartContext'
import { SessionProvider } from './session'

const KEY = 'noordveld-parts-cart-v2'
type Cart = ReturnType<typeof useCart>
const holder: { current: Cart | null } = { current: null }
const api = (): Cart => holder.current as Cart

function Grab() {
  const cart = useCart()
  useEffect(() => {
    holder.current = cart // read by the tests after render, never assigned during it
  })
  return <output data-testid="lines">{JSON.stringify(cart.lines)}</output>
}
const lines = () =>
  JSON.parse(screen.getByTestId('lines').textContent ?? '[]') as {
    partId: string
    qty: number
    machine: string | null
  }[]

const mount = () =>
  render(
    <SessionProvider>
      <CartProvider>
        <Grab />
      </CartProvider>
    </SessionProvider>,
  )

describe('cart lines carry the machine they were chosen for', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 401 })),
    )
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('keeps part, quantity and machine together, and the same part for two machines as two lines', async () => {
    mount()
    act(() => api().add('P1', 2, 'NV-3200'))
    act(() => api().add('P1', 1, 'NV-4500'))
    act(() => api().add('P1', 3, 'NV-3200')) // same part + machine: the quantities merge
    act(() => api().add('P1')) // no machine: its own line
    expect(lines()).toEqual([
      { partId: 'P1', qty: 5, machine: 'NV-3200' },
      { partId: 'P1', qty: 1, machine: 'NV-4500' },
      { partId: 'P1', qty: 1, machine: null },
    ])
    expect(api().count).toBe(7)
    await waitFor(() => expect(JSON.parse(localStorage.getItem(KEY) ?? '[]')).toEqual(lines())) // persisted as it is, machine included
  })
})
