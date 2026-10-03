import { Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
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
}

const isCurrent = (item: NavItem, pathname: string): boolean => (item.to === '/parts-store' || item.to === '/machines') && pathname.startsWith(item.to)

export function SiteNav({ pathname, heroTone, Link }: SiteNavProps) {
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
          {nav.map((item) => (
            <Link key={item.label} to={item.to} external={item.external} className="nav__link" current={isCurrent(item, pathname)}>
              {item.label}
              {item.tag ? <span className="nav__tag">{item.tag}</span> : null}
            </Link>
          ))}
        </nav>
        <button className="nav__toggle" type="button" aria-expanded={open} aria-controls="mobile-menu" onClick={() => setOpen((v) => !v)}>
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
          {open ? <X size={26} aria-hidden="true" /> : <Menu size={26} aria-hidden="true" />}
        </button>
      </div>
      <div id="mobile-menu" className="nav__sheet" hidden={!open}>
        <nav aria-label="Mobile">
          {nav.map((item) => (
            <Link key={item.label} to={item.to} external={item.external} onClick={close} current={isCurrent(item, pathname)}>
              {item.label}
              {item.tag ? <span className="nav__tag">{item.tag}</span> : null}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  )
}
