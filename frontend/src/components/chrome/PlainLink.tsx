import type { ChromeLink } from './links'

/** For pages outside the single-page app: every link is a normal page load, with no router in the bundle. */
export const PlainLink: ChromeLink = ({ to, className, current, label, onClick, children }) => (
  <a href={to} className={className} aria-current={current ? 'page' : undefined} aria-label={label} onClick={onClick}>
    {children}
  </a>
)
