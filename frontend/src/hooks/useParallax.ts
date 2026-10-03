import { useEffect, type RefObject } from 'react'
import { useReducedMotion } from './useMediaQuery'

/**
 * Writes `--parallax` (px) on the element as it moves through the viewport: slow, heavy drift.
 * `strength` is the total travel in px across the element's pass through the viewport.
 */
export function useParallax(ref: RefObject<HTMLElement | null>, strength = 80): void {
  const reduced = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el || reduced) return
    let frame = 0
    let visible = false
    const update = () => {
      frame = 0
      const rect = el.getBoundingClientRect()
      const centre = rect.top + rect.height / 2
      const t = (centre - window.innerHeight / 2) / (window.innerHeight / 2 + rect.height / 2)
      el.style.setProperty('--parallax', `${(-t * strength).toFixed(1)}px`)
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting
        if (visible) {
          window.addEventListener('scroll', schedule, { passive: true })
          schedule()
        } else window.removeEventListener('scroll', schedule)
      },
      { rootMargin: '10% 0px' },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      window.removeEventListener('scroll', schedule)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [ref, reduced, strength])
}
