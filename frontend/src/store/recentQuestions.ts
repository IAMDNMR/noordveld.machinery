import { useSyncExternalStore } from 'react'

/**
 * Questions asked in this browser, newest first, with when and what kind. Kept in the browser like the cart and the
 * identification requests: there are no accounts, so there is nobody to keep a server-side history for.
 */
export interface RecentQuestion {
  question: string
  /** Epoch milliseconds */
  at: number
  /** What the question was understood as (the answer's intent label); absent until it has been answered */
  label?: string
}

const KEY = 'noordveld-pi-history-v1'
const MAX = 20
const listeners = new Set<() => void>()
let cachedRaw: string | null = null
let cached: RecentQuestion[] = []

const snapshot = (): RecentQuestion[] => {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(KEY)
  } catch {
    /* storage unavailable */
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw
    try {
      const parsed = JSON.parse(raw ?? '[]') as unknown
      cached = Array.isArray(parsed)
        ? parsed.filter((q): q is RecentQuestion => !!q && typeof q.question === 'string' && typeof q.at === 'number').slice(0, MAX)
        : []
    } catch {
      cached = []
    }
  }
  return cached
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

const save = (next: RecentQuestion[]) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    cachedRaw = JSON.stringify(next)
    cached = next
  }
  listeners.forEach((l) => l())
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

export function rememberQuestion(question: string): void {
  const q = question.trim()
  if (!q) return
  const earlier = snapshot().find((x) => same(x.question, q))
  save([{ question: q, at: Date.now(), label: earlier?.label }, ...snapshot().filter((x) => !same(x.question, q))].slice(0, MAX))
}

/** Records what an answered question was understood as. */
export function labelQuestion(question: string, label: string): void {
  const current = snapshot()
  if (!current.some((x) => same(x.question, question) && x.label !== label)) return
  save(current.map((x) => (same(x.question, question) ? { ...x, label } : x)))
}

export const useRecentQuestions = (): RecentQuestion[] => useSyncExternalStore(subscribe, snapshot, () => cached)

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "Today, 10:24" · "Yesterday, 16:12" · "28 Sep, 09:05" */
export function whenAsked(at: number, now = new Date()): string {
  const d = new Date(at)
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((day(now) - day(d)) / 86_400_000)
  if (days === 0) return `Today, ${time}`
  if (days === 1) return `Yesterday, ${time}`
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${time}`
}
