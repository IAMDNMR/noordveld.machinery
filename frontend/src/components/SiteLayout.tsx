import { Suspense, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Footer } from './Footer'
import { Nav } from './Nav'
import '../styles/site-premium.css'
import '../styles/experience.css'
import '../styles/brand-refresh.css'
import '../styles/motion.css'
import '../styles/editorial-system.css'
import './cine/cine.css'
import '../styles/cinematic-site.css'

/** Scrolls to the hash target when there is one, otherwise to the top of the new page. */
function ScrollManager() {
  const location = useLocation()
  useEffect(() => {
    if (location.hash) {
      const id = decodeURIComponent(location.hash.slice(1))
      // The target may not be mounted yet on a cross-page navigation
      const frame = requestAnimationFrame(() =>
        document.getElementById(id)?.scrollIntoView({
          behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
            ? 'instant'
            : 'smooth',
          block: 'start',
        }),
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
  const spark = pathname === '/spark/chat'
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <ScrollManager />
      {!spark && <div className="read-progress" aria-hidden="true" />}
      <Nav />
      <main key={pathname} id="main" className="site-premium site-brand">
        {/* a page that is still loading keeps the navigation and footer on screen */}
        <Suspense
          fallback={
            <div className="page-loading" role="status">
              <span aria-hidden="true" />
              Loading…
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>
      {!spark && <Footer />}
    </>
  )
}
