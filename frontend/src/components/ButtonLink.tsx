import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface ButtonLinkProps {
  to: string
  variant?: 'primary' | 'secondary'
  children: ReactNode
  /** Plain anchor for mailto: and external targets */
  external?: boolean
  arrow?: boolean
}

export function ButtonLink({ to, variant = 'primary', children, external = false, arrow = true }: ButtonLinkProps) {
  const content = (
    <>
      {children}
      {arrow ? <ArrowRight size={18} strokeWidth={2} aria-hidden="true" /> : null}
    </>
  )
  const className = `button button--${variant}`
  return external ? (
    <a className={className} href={to}>
      {content}
    </a>
  ) : (
    <Link className={className} to={to}>
      {content}
    </Link>
  )
}

export function TextLink({ to, children, external = false }: { to: string; children: ReactNode; external?: boolean }) {
  const content = (
    <>
      {children}
      <ArrowRight size={16} strokeWidth={2} aria-hidden="true" />
    </>
  )
  return external ? (
    <a className="text-link" href={to}>
      {content}
    </a>
  ) : (
    <Link className="text-link" to={to}>
      {content}
    </Link>
  )
}
