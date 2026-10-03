import { apiPost } from './client'
import type { Quote } from './types'

export interface CartLine {
  partId: string
  qty: number
}

/** Prices a cart from the graph. Stateless: nothing is stored and no order is placed. */
export const quoteCart = (lines: readonly CartLine[], signal?: AbortSignal): Promise<Quote> =>
  apiPost<Quote>('/cart/quote', { items: lines.map((l) => ({ part_id: l.partId, quantity: l.qty })) }, signal)
