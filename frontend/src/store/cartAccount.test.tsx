// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { CartProvider, useCart } from './CartContext'
import { SessionProvider, useSession } from './session'

const KEY = 'noordveld-parts-cart-v2'
const ME = {
  'USR-EU-001': { id: 'USR-EU-001', name: 'Anna', email: 'a@x', role: 'END_USER', customer: 'C1', permissions: [] },
  'USR-OP-001': { id: 'USR-OP-001', name: 'Jane', email: 'j@x', role: 'ORDER_PROCESSOR', customer: null, permissions: [] },
} as const
const holder: { cart: ReturnType<typeof useCart> | null; session: ReturnType<typeof useSession> | null } = {
  cart: null,
  session: null,
}

function Grab() {
  const cart = useCart()
  const session = useSession()
  useEffect(() => {
    holder.cart = cart
    holder.session = session
  })
  return <output data-testid="count">{cart.count}</output>
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/login')) {
        const id = JSON.parse(String(init?.body)).user_id as keyof typeof ME
        return new Response(JSON.stringify(ME[id]), { status: 200 })
      }
      if (url.endsWith('/me/cart')) return new Response('[]', { status: 200 })
      return new Response('{}', { status: 401 })
    }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it("switching account on this browser never shows or saves the previous person's cart", async () => {
  render(
    <SessionProvider>
      <CartProvider>
        <Grab />
      </CartProvider>
    </SessionProvider>,
  )
  await act(async () => void (await holder.session!.signIn('USR-EU-001')))
  act(() => holder.cart!.add('PRT-059'))
  await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'))

  await act(async () => void (await holder.session!.signIn('USR-OP-001'))) // Anna -> Jane without signing out
  await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('0'))
  expect(JSON.parse(localStorage.getItem(KEY) ?? '[]')).toEqual([])
})
