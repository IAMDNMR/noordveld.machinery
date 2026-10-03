import type { Money } from '../api'

/** `IN_STOCK` → "In stock". Labels for API enumerations come from the API's own values, never from a local list. */
export const humanize = (value: string): string => {
  const text = value.replace(/_/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const formatMoney = (money: Pick<Money, 'amount' | 'currency'>): string =>
  new Intl.NumberFormat('en-NL', { style: 'currency', currency: money.currency }).format(money.amount)

export type Tone = 'ok' | 'warn' | 'late'

/** Visual tone for an availability state: available is quiet, limited is amber, anything else needs attention. */
export const availabilityTone = (state: string): Tone => (state === 'IN_STOCK' ? 'ok' : state === 'LIMITED' ? 'warn' : 'late')

export const NOT_AVAILABLE = 'Not available'
