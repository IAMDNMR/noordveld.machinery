import type { ReactElement, ReactNode } from 'react'

export interface ChromeLinkProps {
  to: string
  /** Leaves the single-page app: always a normal page load */
  external?: boolean
  className?: string
  current?: boolean
  label?: string
  onClick?: () => void
  children: ReactNode
}

/**
 * How the chrome renders links. The Noordveld site passes a router link (no page reloads);
 * the Agentic E-Commerce page, a separate document, passes plain anchors.
 */
export type ChromeLink = (props: ChromeLinkProps) => ReactElement
