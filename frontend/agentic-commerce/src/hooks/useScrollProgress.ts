import { useEffect, useState, type RefObject } from 'react'
import { clamp01 } from '../lib/math'

/**
 * Progress (0–1) through a tall section whose child is `position: sticky`.
 * 0 when the section top meets the viewport top, 1 when its bottom meets the viewport bottom.
 * Listens only while the section is near the viewport and throttles to animation frames.
 */
export function useScrollProgress(ref: RefObject<HTMLElement | null>, enabled = true): number {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el || !enabled) return
    let frame = 0
    let listening = false

    const measure = () => {
      frame = 0
      const rect = el.getBoundingClientRect()
      const travel = rect.height - window.innerHeight
      const next = travel > 0 ? clamp01(-rect.top / travel) : 0
      setProgress((prev) => (Math.abs(prev - next) < 0.0004 ? prev : next))
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure)
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !listening) {
          listening = true
          window.addEventListener('scroll', schedule, { passive: true })
          window.addEventListener('resize', schedule)
          schedule()
        } else if (!entry.isIntersecting) {
          if (listening) {
            listening = false
            window.removeEventListener('scroll', schedule)
            window.removeEventListener('resize', schedule)
          }
          schedule()
        }
      },
      { rootMargin: '25% 0px' },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      if (frame) cancelAnimationFrame(frame)
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [ref, enabled])

  return progress
}
