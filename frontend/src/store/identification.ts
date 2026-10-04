import { useCallback, useSyncExternalStore } from 'react'

/**
 * Identification the user has asked for or supplied, kept in this browser like the cart.
 * It records what the user said; it never changes a part's catalogue status. Only verified data can do that.
 */
export interface IdentificationRecord {
  /** Unverified parts: the user asked Noordveld to identify the part */
  requestedAt?: string
  /** Identification required / ambiguous parts: what the user entered */
  machine?: string
  serialOrVariant?: string
  submittedAt?: string
}

type Records = Record<string, IdentificationRecord>

const KEY = 'noordveld-identification-v1'
const listeners = new Set<() => void>()
let cachedRaw: string | null = null
let cached: Records = {}

const snapshot = (): Records => {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(KEY)
  } catch {
    /* storage unavailable */
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw
    try {
      const parsed = JSON.parse(raw ?? '{}') as unknown
      cached = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Records) : {}
    } catch {
      cached = {}
    }
  }
  return cached
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  const onStorage = (e: StorageEvent) => e.key === KEY && listener()
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

const save = (partNumber: string, patch: IdentificationRecord) => {
  const next = { ...snapshot(), [partNumber]: { ...snapshot()[partNumber], ...patch } }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable: kept for this visit only */
    cachedRaw = JSON.stringify(next)
    cached = next
  }
  listeners.forEach((l) => l())
}

export function useIdentification(partNumber: string) {
  const records = useSyncExternalStore(subscribe, snapshot, () => cached)
  const request = useCallback(() => save(partNumber, { requestedAt: new Date().toISOString() }), [partNumber])
  const submit = useCallback(
    (machine: string, serialOrVariant: string) => save(partNumber, { machine: machine.trim(), serialOrVariant: serialOrVariant.trim(), submittedAt: new Date().toISOString() }),
    [partNumber],
  )
  return { record: records[partNumber] ?? null, request, submit }
}

export const formatDate = (iso: string | undefined): string => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '')
