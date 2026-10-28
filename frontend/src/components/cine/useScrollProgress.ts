import { useEffect, useState, type RefObject } from 'react'

/**
 * How far an element has travelled through the viewport: 0 when its top reaches the bottom of the screen, 1 when its bottom leaves the top.
 * One passive listener per element; browsers deliver scroll events once per frame, so it measures directly. Under reduced motion it reports a fixed value so nothing moves.
 */
export function useScrollProgress(ref: RefObject<HTMLElement | null>, still = 0.5): number {
  const [progress, setProgress] = useState(still)
  useEffect(() => {
    const node = ref.current
    if (!node || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const measure = () => {
      const box = node.getBoundingClientRect()
      const span = box.height + window.innerHeight
      setProgress(Math.min(1, Math.max(0, (window.innerHeight - box.top) / span)))
    }
    measure()
    window.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [ref])
  return progress
}

/** Progress through a tall "sticky" track: 0 when the track's top reaches the top of the screen, 1 when its bottom reaches the bottom. */
export function useStickyProgress(ref: RefObject<HTMLElement | null>): number {
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const measure = () => {
      const box = node.getBoundingClientRect()
      const span = box.height - window.innerHeight
      setProgress(span > 0 ? Math.min(1, Math.max(0, -box.top / span)) : 0)
    }
    measure()
    window.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [ref])
  return progress
}
