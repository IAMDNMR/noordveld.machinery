import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { partById, type StorePart } from '../data/store'

interface Line {
  id: string
  qty: number
}

export interface CartItem {
  part: StorePart
  qty: number
  total: number
}

interface CartValue {
  items: readonly CartItem[]
  count: number
  subtotal: number
  open: boolean
  /** Part last added, shown briefly as feedback */
  justAdded: string | null
  setOpen: (open: boolean) => void
  add: (part: StorePart, qty?: number) => void
  setQty: (id: string, qty: number) => void
  remove: (id: string) => void
  clear: () => void
}

const KEY = 'noordveld-parts-cart-v1'
const MAX_QTY = 99
const Cart = createContext<CartValue | null>(null)

const read = (): Line[] => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]') as Line[]
    return raw.filter((l) => partById(l.id) && l.qty > 0).map((l) => ({ id: l.id, qty: Math.min(MAX_QTY, Math.floor(l.qty)) }))
  } catch {
    return []
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<Line[]>(read)
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

  const add = useCallback((part: StorePart, qty = 1) => {
    setLines((cur) => {
      const found = cur.find((l) => l.id === part.id)
      return found ? cur.map((l) => (l.id === part.id ? { ...l, qty: Math.min(MAX_QTY, l.qty + qty) } : l)) : [...cur, { id: part.id, qty: Math.min(MAX_QTY, qty) }]
    })
    setJustAdded(part.id)
  }, [])
  const setQty = useCallback((id: string, qty: number) => setLines((cur) => (qty <= 0 ? cur.filter((l) => l.id !== id) : cur.map((l) => (l.id === id ? { ...l, qty: Math.min(MAX_QTY, qty) } : l)))), [])
  const remove = useCallback((id: string) => setLines((cur) => cur.filter((l) => l.id !== id)), [])
  const clear = useCallback(() => setLines([]), [])

  const value = useMemo<CartValue>(() => {
    const items = lines.flatMap((l) => {
      const part = partById(l.id)
      return part ? [{ part, qty: l.qty, total: Math.round(part.price * l.qty * 100) / 100 }] : []
    })
    return { items, count: items.reduce((n, i) => n + i.qty, 0), subtotal: Math.round(items.reduce((n, i) => n + i.total, 0) * 100) / 100, open, justAdded, setOpen, add, setQty, remove, clear }
  }, [lines, open, justAdded, add, setQty, remove, clear])

  return <Cart.Provider value={value}>{children}</Cart.Provider>
}

export function useCart(): CartValue {
  const value = useContext(Cart)
  if (!value) throw new Error('useCart must be used inside the store layout')
  return value
}
