import { Link } from 'react-router-dom'
import type { ChromeLink } from './links'

/** In-app links use the router (no reload); `external` ones, such as the Agentic E-Commerce page, are plain anchors. */
export const RouterLink: ChromeLink = ({ to, external, className, current, label, onClick, children }) =>
  external ? (
    <a href={to} className={className} aria-current={current ? 'page' : undefined} aria-label={label} onClick={onClick}>
      {children}
    </a>
  ) : (
    <Link to={to} className={className} aria-current={current ? 'page' : undefined} aria-label={label} onClick={onClick}>
      {children}
    </Link>
  )
