import { useRef, type CSSProperties, type PointerEvent, type ReactNode } from 'react'
import './tilt.css'

/**
 * A surface that leans towards the pointer in 3D, with a soft glare that follows it. Only for a fine pointer (mouse or pen);
 * touch and reduced motion get the flat surface. The child keeps its own semantics (a link stays a link).
 */
export function Tilt({
  children,
  className = '',
  max = 7,
}: {
  children: ReactNode
  className?: string
  /** Largest lean in degrees */
  max?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const node = ref.current
    if (!node || event.pointerType === 'touch') return
    const box = node.getBoundingClientRect()
    const x = (event.clientX - box.left) / box.width
    const y = (event.clientY - box.top) / box.height
    node.style.setProperty('--rx', `${(0.5 - y) * max * 2}deg`)
    node.style.setProperty('--ry', `${(x - 0.5) * max * 2}deg`)
    node.style.setProperty('--gx', `${x * 100}%`)
    node.style.setProperty('--gy', `${y * 100}%`)
    node.dataset.active = 'true'
  }
  const leave = () => {
    const node = ref.current
    if (!node) return
    node.style.setProperty('--rx', '0deg')
    node.style.setProperty('--ry', '0deg')
    delete node.dataset.active
  }
  return (
    <div
      ref={ref}
      className={`tilt ${className}`}
      onPointerMove={move}
      onPointerLeave={leave}
      style={{ '--rx': '0deg', '--ry': '0deg' } as CSSProperties}
    >
      {children}
      <span className="tilt__glare" aria-hidden="true" />
    </div>
  )
}
