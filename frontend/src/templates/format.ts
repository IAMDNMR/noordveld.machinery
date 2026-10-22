import type { SampleRow } from '../api/appTemplates'

const MONEY = /price|amount|value|total|limit|cost/
const STATUS = new Set(['status', 'availability', 'stage', 'severity', 'priority', 'warranty'])
const GOOD =
  /deliver|approved|^ok$|won|done|in stock|paid|confirmed|completed|under warranty|next day/i
const BAD = /low|delay|overdue|reject|urgent|high|excess|failed|blocked/i
const WAIT =
  /wait|review|open|progress|planned|medium|on order|request|proposal|qualified|arriving|scheduled|shipped|transit|days?$/i

export const label = (field: string) => {
  const text = field.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const isStatus = (field: string) => STATUS.has(field)

export function tone(value: unknown): 'good' | 'bad' | 'wait' | 'neutral' {
  const text = String(value ?? '')
  if (BAD.test(text)) return 'bad'
  if (GOOD.test(text)) return 'good'
  if (WAIT.test(text)) return 'wait'
  return 'neutral'
}

export function show(field: string, value: SampleRow[string] | undefined): string {
  if (value === undefined || value === '') return '—'
  if (typeof value === 'number' && MONEY.test(field))
    return value.toLocaleString('en-GB', {
      style: 'currency',
      currency: 'EUR',
      maximumFractionDigits: value % 1 ? 2 : 0,
    })
  if (typeof value === 'number' && field === 'rating') return `${value} / 5`
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

/** The row's own name: its first text field that is not a status or picture. */
export function titleOf(row: SampleRow, fields: string[]): string {
  const field = fields.find(
    (item) => item !== 'image' && !isStatus(item) && typeof row[item] === 'string',
  )
  return field ? String(row[field]) : String(row.id ?? '')
}
