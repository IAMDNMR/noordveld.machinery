import { useSession } from '../store/session'
import { RouterLink } from './chrome/RouterLink'
import { SiteFooter } from './chrome/SiteFooter'

export function Footer() {
  const { user } = useSession()
  return <SiteFooter Link={RouterLink} showStudio={!user} />
}
