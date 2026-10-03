import { ArrowRight, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

interface ButtonLinkProps {
  href: string
  variant?: 'primary' | 'secondary'
  children: ReactNode
}

export function ButtonLink({ href, variant = 'primary', children }: ButtonLinkProps) {
  const Icon = variant === 'primary' ? ArrowRight : ChevronRight
  return (
    <a className={`button button--${variant}`} href={href}>
      {children}
      <Icon className="button__arrow" size={variant === 'primary' ? 18 : 20} strokeWidth={2} aria-hidden="true" />
    </a>
  )
}
