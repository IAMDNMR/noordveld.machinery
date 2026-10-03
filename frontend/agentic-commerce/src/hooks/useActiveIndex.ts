import { useEffect, useState, type RefObject } from 'react'

/** Index of the child (matching `selector`) whose block crosses the viewport's centre band. */
export function useActiveIndex(containerRef: RefObject<HTMLElement | null>, selector: string): number {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const root = containerRef.current
    if (!root) return
    const items = Array.from(root.querySelectorAll(selector))
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(items.indexOf(entry.target))
        }
      },
      { rootMargin: '-45% 0px -45% 0px' },
    )
    items.forEach((item) => io.observe(item))
    return () => io.disconnect()
  }, [containerRef, selector])
  return active
}
