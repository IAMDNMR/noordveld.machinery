import { apiPost } from './client'
import type { Quote } from './types'

/** A cart line: a part, how many, and the machine it was chosen for (null when none was chosen). The same part for two machines is two lines. */
export interface CartLine {
  partId: string
  qty: number
  machine?: string | null
}

export const lineKey = (l: Pick<CartLine, 'partId' | 'machine'>): string => `${l.partId}|${l.machine ?? ''}`

/** Prices a cart from the graph. Stateless: nothing is stored and no order is placed. */
export const quoteCart = (lines: readonly CartLine[], signal?: AbortSignal): Promise<Quote> =>
  apiPost<Quote>('/cart/quote', { items: lines.map((l) => ({ part_id: l.partId, quantity: l.qty })) }, signal)
