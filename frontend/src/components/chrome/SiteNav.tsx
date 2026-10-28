import { Menu, X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { primaryNav, type NavItem } from '../../data/content'
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

/** Spark covers its introduction and the conversation. */
const isCurrent = (item: NavItem, pathname: string): boolean => {
  const [path] = pathname.split('?')
  if (item.to === '/spark') return path === '/spark' || path.startsWith('/spark/')
  if (item.to.includes('?')) return pathname === item.to // a queue of the order list
  if (item.to === '/orders') return path.startsWith('/orders') && !pathname.includes('queue=')
  if (item.to === '/workspace') return path === '/workspace'
  return (
    ['/aftersales', '/parts-services', '/parts-store', '/machines'].includes(item.to) &&
    path.startsWith(item.to)
  )
}

export function SiteNav({ pathname, heroTone, Link, items = primaryNav, account }: SiteNavProps) {
  const navigation = items.filter((item) => !item.to.startsWith('mailto:'))
  const [openPath, setOpenPath] = useState<string | null>(null)
  const open = openPath === pathname
  const [scrolled, setScrolled] = useState(false)
  const overHero = heroTone && !scrolled && !open
  const toggleRef = useRef<HTMLButtonElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenPath(null)
        toggleRef.current?.focus()
      }
      if (e.key === 'Tab') {
        const links = sheetRef.current?.querySelectorAll<HTMLElement>('a, button')
        const last = links?.[links.length - 1]
        if (e.shiftKey && document.activeElement === toggleRef.current) {
          e.preventDefault()
          last?.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          toggleRef.current?.focus()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open])

  useEffect(() => {
    const resized = () => {
      if (window.innerWidth >= 900) setOpenPath(null)
    }
    window.addEventListener('resize', resized)
    return () => window.removeEventListener('resize', resized)
  }, [])

  const close = () => setOpenPath(null)

  return (
    <header
      className={`nav nvx-chrome ${overHero ? 'nav--hero' : 'nav--solid'} ${open ? 'is-open' : ''}`}
    >
      <div className="nav__bar nvx-container">
        <Link to="/" className="nav__logo" label="Noordveld Machinery B.V., home" onClick={close}>
          <Logo tone={overHero ? 'light' : 'dark'} height={34} />
        </Link>
        <nav className="nav__links" aria-label="Primary">
          {navigation.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              external={item.external}
              className="nav__link"
              current={isCurrent(item, pathname)}
            >
              {item.label}
              {item.tag ? <span className="nav__tag">{item.tag}</span> : null}
            </Link>
          ))}
        </nav>
        {account ? <div className="nav__account">{account}</div> : null}
        <button
          ref={toggleRef}
          className="nav__toggle"
          type="button"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpenPath(open ? null : pathname)}
        >
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
          {open ? <X size={26} aria-hidden="true" /> : <Menu size={26} aria-hidden="true" />}
        </button>
      </div>
      <div ref={sheetRef} id="mobile-menu" className="nav__sheet" hidden={!open}>
        <span className="nav__sheet-label">EXPLORE NOORDVELD</span>
        <nav aria-label="Mobile">
          {navigation.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              external={item.external}
              onClick={close}
              current={isCurrent(item, pathname)}
            >
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
