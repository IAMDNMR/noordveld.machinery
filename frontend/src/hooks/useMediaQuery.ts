import { useSyncExternalStore } from 'react'
import { queries } from '../lib/breakpoints'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', notify)
      return () => mql.removeEventListener('change', notify)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

export const useReducedMotion = (): boolean => useMediaQuery(queries.reducedMotion)
