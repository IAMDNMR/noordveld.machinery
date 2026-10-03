import { useLocation } from 'react-router-dom'
import { RouterLink } from './chrome/RouterLink'
import { SiteNav } from './chrome/SiteNav'

export function Nav() {
  const { pathname } = useLocation()
  // The home page and the Parts Store catalogue open on a dark hero, so the bar starts transparent there
  return <SiteNav pathname={pathname} heroTone={pathname === '/' || pathname === '/parts-store'} Link={RouterLink} />
}
