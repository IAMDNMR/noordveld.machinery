import { useLocation, useNavigate } from 'react-router-dom'
import { navFor } from '../data/content'
import { roleLabel, useSession } from '../store/session'
import { RouterLink } from './chrome/RouterLink'
import { SiteNav } from './chrome/SiteNav'

export function Nav() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const { user, signOut } = useSession()
  const account = user ? (
    <>
      <span className="nav__role" title={user.name}>
        {roleLabel(user.role)}
      </span>
      <button
        type="button"
        className="nav__signout"
        onClick={async () => {
          await signOut()
          navigate('/')
        }}
      >
        Sign out
      </button>
    </>
  ) : (
    <RouterLink to="/sign-in" className="nav__signin">
      Sign in
    </RouterLink>
  )
  // Only the home page opens on a dark film, so only there does the bar start transparent
  return <SiteNav pathname={pathname + search} heroTone={pathname === '/'} Link={RouterLink} items={navFor(user?.role ?? null)} account={account} />
}
