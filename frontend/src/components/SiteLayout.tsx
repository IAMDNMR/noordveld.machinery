import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Footer } from './Footer'
import { Nav } from './Nav'
import '../styles/site-premium.css'

/** Scrolls to the hash target when there is one, otherwise to the top of the new page. */
function ScrollManager() {
  const location = useLocation()
  useEffect(() => {
    if (location.hash) {
      const id = decodeURIComponent(location.hash.slice(1))
      // The target may not be mounted yet on a cross-page navigation
      const frame = requestAnimationFrame(() =>
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      )
      return () => cancelAnimationFrame(frame)
    }
    window.scrollTo({ top: 0, behavior: 'instant' })
    // Query-string changes (the Parts Store filters) must not scroll the page
    // Navigation must reposition the viewport even when the next page has the same hash.
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [location.pathname, location.hash])
  return null
}

export function SiteLayout() {
  const { pathname } = useLocation()
  const studio = pathname.startsWith('/design-studio')
  // Design Studio has its own full-height navigation.
  const ownShell = studio && !/^\/design-studio\/domains(\/|$)/.test(pathname)
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <ScrollManager />
      {!ownShell && <Nav />}
      <main id="main" className={studio ? undefined : 'site-premium'}>
        <Outlet />
      </main>
      {!studio && <Footer />}
    </>
  )
}
