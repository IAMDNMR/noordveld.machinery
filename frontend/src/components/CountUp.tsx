import { useEffect, useRef, useState } from 'react'
import { useInView } from '../hooks/useInView'
import { useReducedMotion } from '../hooks/useMediaQuery'

/** Counts from zero to a verified number once it scrolls into view. The final value is always the real one. */
export function CountUp({ value, duration = 1100 }: { value: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.6 })
  const reduced = useReducedMotion()
  const [shown, setShown] = useState<number | null>(null)
  useEffect(() => {
    if (!inView || reduced) return
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      setShown(Math.round(value * (1 - (1 - t) ** 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [inView, reduced, value, duration])
  return (
    <span ref={ref} aria-label={String(value)}>
      <span aria-hidden="true">{reduced || shown === null ? value : shown}</span>
    </span>
  )
}
