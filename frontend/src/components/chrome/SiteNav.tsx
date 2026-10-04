import { Menu, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { nav, type NavItem } from '../../data/content'
import { Logo } from '../Logo'
import './chrome-tokens.css'
import './chrome.css'
import type { ChromeLink } from './links'

interface SiteNavProps {
  /** Current path, used for the active item */
  pathname: string
  /** True where the page opens on a dark film: the bar starts transparent and turns solid on scroll */
  heroTone: boolean
  Link: ChromeLink
  /** the links to show; the public site navigation when omitted */
  items?: readonly NavItem[]
  /** the account area at the end of the bar (role label, sign in / out) */
  account?: ReactNode
}

/** Agentic Shopping is the hands-on step of Agentic E-Commerce, so it lights up that item. */
const isCurrent = (item: NavItem, pathname: string): boolean => {
  const [path] = pathname.split('?')
  if (item.to === '/agentic-commerce/') return path.startsWith('/agentic-commerce') || path.startsWith('/agentic-shopping')
  if (item.to.includes('?')) return pathname === item.to // a queue of the order list
  if (item.to === '/orders') return path.startsWith('/orders') && !pathname.includes('queue=')
  return ['/parts-store', '/parts-intelligence', '/machines', '/agentic-shopping'].includes(item.to) && path.startsWith(item.to)
}

export function SiteNav({ pathname, heroTone, Link, items = nav, account }: SiteNavProps) {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const overHero = heroTone && !scrolled && !open

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open])

  const close = () => setOpen(false)

  return (
    <header className={`nav nvx-chrome ${overHero ? 'nav--hero' : 'nav--solid'} ${open ? 'is-open' : ''}`}>
      <div className="nav__bar nvx-container">
        <Link to="/" className="nav__logo" label="Noordveld Machinery B.V., home" onClick={close}>
          <Logo tone={overHero ? 'light' : 'dark'} height={34} />
        </Link>
        <nav className="nav__links" aria-label="Primary">
          {items.map((item) => (
            <Link key={item.label} to={item.to} external={item.external} className="nav__link" current={isCurrent(item, pathname)}>
              {item.label}
              {item.tag ? <span className="nav__tag">{item.tag}</span> : null}
            </Link>
          ))}
        </nav>
        {account ? <div className="nav__account">{account}</div> : null}
        <button className="nav__toggle" type="button" aria-expanded={open} aria-controls="mobile-menu" onClick={() => setOpen((v) => !v)}>
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
          {open ? <X size={26} aria-hidden="true" /> : <Menu size={26} aria-hidden="true" />}
        </button>
      </div>
      <div id="mobile-menu" className="nav__sheet" hidden={!open}>
        <nav aria-label="Mobile">
          {items.map((item) => (
            <Link key={item.label} to={item.to} external={item.external} onClick={close} current={isCurrent(item, pathname)}>
              {item.label}
              {item.tag ? <span className="nav__tag">{item.tag}</span> : null}
            </Link>
          ))}
        </nav>
        {account ? <div className="nav__account nav__account--sheet">{account}</div> : null}
      </div>
    </header>
  )
}
