import { useEffect, useState, type RefObject } from 'react'

interface Options {
  once?: boolean
  threshold?: number
  rootMargin?: string
}

export function useInView<T extends Element>(ref: RefObject<T | null>, { once = false, threshold = 0.15, rootMargin = '0px' }: Options = {}): boolean {
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          if (once) io.disconnect()
        } else if (!once) setInView(false)
      },
      { threshold, rootMargin },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [ref, once, threshold, rootMargin])
  return inView
}
