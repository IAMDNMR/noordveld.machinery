// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { lineKey } from '../api'
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
const lines = () => JSON.parse(screen.getByTestId('lines').textContent ?? '[]') as { partId: string; qty: number; machine: string | null }[]

const mount = () => render(<SessionProvider><CartProvider><Grab /></CartProvider></SessionProvider>)

describe('cart lines carry the machine they were chosen for', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
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
    expect(lines()).toEqual([{ partId: 'P1', qty: 5, machine: 'NV-3200' }, { partId: 'P1', qty: 1, machine: 'NV-4500' }, { partId: 'P1', qty: 1, machine: null }])
    expect(api().count).toBe(7)
    await waitFor(() => expect(JSON.parse(localStorage.getItem(KEY) ?? '[]')).toEqual(lines())) // persisted as it is, machine included
  })

  it('changes and removes one line without touching the same part for another machine', () => {
    mount()
    act(() => api().add('P1', 2, 'NV-3200'))
    act(() => api().add('P1', 2, 'NV-4500'))
    act(() => api().setQty(lineKey({ partId: 'P1', machine: 'NV-3200' }), 7))
    expect(lines().map((l) => [l.machine, l.qty])).toEqual([['NV-3200', 7], ['NV-4500', 2]])
    act(() => api().remove(lineKey({ partId: 'P1', machine: 'NV-4500' })))
    expect(lines()).toEqual([{ partId: 'P1', qty: 7, machine: 'NV-3200' }])
  })

  it('restores a saved cart with its machines and drops anything malformed', () => {
    localStorage.setItem(KEY, JSON.stringify([{ partId: 'P1', qty: 2, machine: 'NV-3200' }, { partId: 'P2', qty: 1 }, { partId: 3, qty: 1 }, { partId: 'P4', qty: 0 }, { partId: 'P5', qty: 500, machine: 42 }]))
    mount()
    expect(lines()).toEqual([{ partId: 'P1', qty: 2, machine: 'NV-3200' }, { partId: 'P2', qty: 1, machine: null }, { partId: 'P5', qty: 99, machine: null }])
  })

  it('merges the signed-in user’s server cart with local lines by part + machine', async () => {
    localStorage.setItem(KEY, JSON.stringify([{ partId: 'P1', qty: 1, machine: null }]))
    const puts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/me')) return new Response(JSON.stringify({ id: 'U1', name: 'Anna', email: 'a@x', role: 'END_USER', customer: null, permissions: [] }))
      if (url.includes('/me/cart') && init?.method === 'PUT') {
        puts.push(JSON.parse(init.body as string))
        return new Response('[]')
      }
      if (url.includes('/me/cart')) return new Response(JSON.stringify([{ partId: 'P1', partNumber: 'AB-1', partName: 'Part', qty: 4, machine: 'NV-3200' }]))
      return new Response('{}', { status: 404 })
    }))
    mount()
    await waitFor(() => expect(lines().map((l) => [l.partId, l.machine, l.qty])).toEqual(expect.arrayContaining([['P1', 'NV-3200', 4], ['P1', null, 1]])))
    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 2000 })
    expect((puts.at(-1) as { lines: { machine: string | null }[] }).lines.map((l) => l.machine ?? '').sort()).toEqual(['', 'NV-3200']) // the machine is saved to the server
  })
})
