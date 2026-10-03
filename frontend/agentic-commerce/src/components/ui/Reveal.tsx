import { useRef, type CSSProperties, type ElementType, type ReactNode } from 'react'
import { useInView } from '../../hooks/useInView'

interface RevealProps {
  as?: ElementType
  className?: string
  delay?: number
  children: ReactNode
}

/** Fades and lifts content in once it enters the viewport. Reduced motion is handled in base.css. */
export function Reveal({ as: Tag = 'div', className = '', delay = 0, children }: RevealProps) {
  const ref = useRef<HTMLElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.2, rootMargin: '0px 0px -8% 0px' })
  const style = { '--reveal-delay': `${delay}ms` } as CSSProperties
  return (
    <Tag ref={ref} className={`reveal ${inView ? 'is-in' : ''} ${className}`} style={style}>
      {children}
    </Tag>
  )
}
