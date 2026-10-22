import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getActiveOrganization, setActiveOrganization } from '../api/client'
import { getWorkspace, type Workspace } from '../api/workspace'
import { navFor } from '../data/content'
import { roleLabel, useSession } from '../store/session'
import { RouterLink } from './chrome/RouterLink'
import { SiteNav } from './chrome/SiteNav'

export function Nav() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const { user, signOut } = useSession()
  // Organization-aware navigation. Hiding a link is presentation only; the server enforces every permission. Where no organization
  // directory exists the older role-based links stay as they were.
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [organizationChanges, setOrganizationChanges] = useState(0)
  const ownChange = useRef(false) // the navigation's own update of the active organization must not trigger another fetch
  useEffect(() => {
    const changed = () => {
      if (!ownChange.current) setOrganizationChanges((count) => count + 1)
    }
    window.addEventListener('active-organization', changed)
    return () => window.removeEventListener('active-organization', changed)
  }, [])
  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    getWorkspace(getActiveOrganization(), controller.signal).then(
      (result) => {
        setWorkspace(result)
        ownChange.current = true
        setActiveOrganization(result.active_organization)
        ownChange.current = false
      },
      () => undefined,
    )
    return () => controller.abort()
    // Refetch when the organization changes in another workspace component.
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [user, organizationChanges])
  // Clear organization state when the authenticated identity changes.
  // eslint-disable-next-line react/exhaustive-effect-dependencies
  useEffect(
    () => () => {
      setWorkspace(null)
      ownChange.current = true
      setActiveOrganization(null)
      ownChange.current = false
    },
    // eslint-disable-next-line react/exhaustive-effect-dependencies
    [user],
  )
  const items = useMemo(() => {
    const base = navFor(user?.role ?? null).filter(
      (item) => !user || (item.to !== '/studio' && item.to !== '/design-studio'),
    )
    if (!user || !workspace?.directory_configured) return base
    const visible = workspace.studio?.visible
      ? base
      : base.filter((item) => item.to !== '/design-studio')
    return [{ label: 'Workspace', to: '/workspace' }, ...visible]
  }, [user, workspace])
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
  return (
    <SiteNav
      pathname={pathname + search}
      heroTone={pathname === '/'}
      Link={RouterLink}
      items={items}
      account={account}
    />
  )
}
