import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { CartLine } from '../api'

interface CartValue {
  /** Part ids and quantities only. Names and prices are never stored: the API supplies them when the cart is shown. */
  lines: readonly CartLine[]
  count: number
  open: boolean
  /** Part last added, shown briefly as feedback */
  justAdded: string | null
  setOpen: (open: boolean) => void
  add: (partId: string, qty?: number) => void
  setQty: (partId: string, qty: number) => void
  remove: (partId: string) => void
  clear: () => void
}

const KEY = 'noordveld-parts-cart-v2'
const MAX_QTY = 99
const Cart = createContext<CartValue | null>(null)

const read = (): CartLine[] => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]') as Partial<CartLine>[]
    return raw.filter((l): l is CartLine => typeof l.partId === 'string' && Number.isInteger(l.qty) && (l.qty ?? 0) > 0).map((l) => ({ partId: l.partId, qty: Math.min(MAX_QTY, l.qty) }))
  } catch {
    return []
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>(read)
  const [open, setOpen] = useState(false)
  const [justAdded, setJustAdded] = useState<string | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(lines))
    } catch {
      /* storage unavailable: the cart simply lives for this visit */
    }
  }, [lines])

  useEffect(() => {
    if (!justAdded) return
    const t = window.setTimeout(() => setJustAdded(null), 1800)
    return () => window.clearTimeout(t)
  }, [justAdded])

  const add = useCallback((partId: string, qty = 1) => {
    setLines((cur) =>
      cur.some((l) => l.partId === partId) ? cur.map((l) => (l.partId === partId ? { ...l, qty: Math.min(MAX_QTY, l.qty + qty) } : l)) : [...cur, { partId, qty: Math.min(MAX_QTY, qty) }],
    )
    setJustAdded(partId)
  }, [])
  const setQty = useCallback((partId: string, qty: number) => setLines((cur) => (qty <= 0 ? cur.filter((l) => l.partId !== partId) : cur.map((l) => (l.partId === partId ? { ...l, qty: Math.min(MAX_QTY, qty) } : l)))), [])
  const remove = useCallback((partId: string) => setLines((cur) => cur.filter((l) => l.partId !== partId)), [])
  const clear = useCallback(() => setLines([]), [])

  const value = useMemo<CartValue>(
    () => ({ lines, count: lines.reduce((n, l) => n + l.qty, 0), open, justAdded, setOpen, add, setQty, remove, clear }),
    [lines, open, justAdded, add, setQty, remove, clear],
  )
  return <Cart.Provider value={value}>{children}</Cart.Provider>
}

export function useCart(): CartValue {
  const value = useContext(Cart)
  if (!value) throw new Error('useCart must be used inside the store layout')
  return value
}
