import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, setActiveOrganization } from '../api/client'
import {
  getWorkspace,
  ROLE_LABEL,
  STATUS_LABEL,
  type Workspace,
  type WorkspaceApp,
} from '../api/workspace'
import { useSession } from '../store/session'
import { InvitePanel } from '../components/workspace/AccessAdmin'
import './WorkspacePage.css'
import '../components/orders/orders-redesign.css'

type Filter = 'all' | 'operational' | 'in_design' | 'planned'
const FILTERS: [Filter, string][] = [
  ['all', 'All'],
  ['operational', 'Available'],
  ['in_design', 'In design'],
  ['planned', 'Planned'],
]
const label = (role: string) => ROLE_LABEL[role] ?? role.replace(/_/g, ' ')

function AppCard({ app }: { app: WorkspaceApp }) {
  const navigate = useNavigate()
  return (
    <article className={`ws-card ws-card--${app.status}`} aria-label={app.name}>
      <header>
        <h3>{app.name}</h3>
        <span className={`ws-status ws-status--${app.status}`}>{STATUS_LABEL[app.status]}</span>
      </header>
      <p className="ws-muted">{app.domain}</p>
      <p>{app.description}</p>
      {app.your_roles.length > 0 && (
        <p className="ws-roles">Your role: {app.your_roles.map(label).join(', ')}</p>
      )}
      {app.launchable && app.route ? (
        <button type="button" className="ws-primary" onClick={() => navigate(app.route!)}>
          Open {app.name}
        </button>
      ) : (
        <p className="ws-reason" role="note">
          {app.reason}
        </p>
      )}
    </article>
  )
}

/** The landing page after sign-in: organization, systems, projects and what needs attention. All of it comes from the server. */
export default function WorkspacePage() {
  const { user, ready } = useSession()
  const [data, setData] = useState<Workspace | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search] = useSearchParams()
  const [org, setOrg] = useState<string | null>(search.get('org'))
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [attempt, setAttempt] = useState(0)
  const userId = user?.id ?? null

  useEffect(() => {
    if (!userId) return
    const controller = new AbortController()
    getWorkspace(org, controller.signal)
      .then((result) => {
        setData(result)
        setError(null)
        setActiveOrganization(result.active_organization)
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(cause instanceof ApiError ? cause.message : 'The workspace could not be loaded.')
      })
    return () => controller.abort()
    // An explicit retry must fetch again without changing the selected organization.
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [userId, org, attempt])

  const apps = useMemo(
    () =>
      (data?.applications ?? []).filter(
        (app) =>
          (filter === 'all' || app.status === filter) &&
          `${app.name} ${app.domain} ${app.description}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
      ),
    [data, filter, query],
  )

  if (!ready)
    return (
      <p className="ws-page" role="status">
        Loading your workspace…
      </p>
    )
  if (!user)
    return (
      <section className="ws-page">
        <h1>Workspace</h1>
        <p>Sign in to see your applications.</p>
        <Link to="/sign-in?next=/workspace">Sign in</Link>
      </section>
    )
  if (error)
    return (
      <section className="ws-page">
        <h1>Workspace</h1>
        <div className="pixels-error" role="alert">
          {error}
        </div>
        <button
          type="button"
          onClick={() => {
            setError(null)
            setAttempt((count) => count + 1)
          }}
        >
          Try again
        </button>
      </section>
    )
  if (!data)
    return (
      <p className="ws-page" role="status">
        Loading your workspace…
      </p>
    )

  const active = data.organizations.find((item) => item.id === data.active_organization)
  return (
    <div className="ws-page">
      <header className="ws-head">
        <div>
          <p className="ws-eyebrow">NOORDVELD WORKSPACE</p>
          <h1>{active ? active.name : `Welcome, ${data.user.name}`}</h1>
          <p className="ws-muted">
            {active
              ? `Signed in as ${data.user.name} · ${active.roles.map(label).join(', ') || 'application user'}`
              : data.platform_roles.length
                ? `Platform: ${data.platform_roles.map(label).join(', ')}`
                : data.user.email}
          </p>
        </div>
        {data.organizations.length > 1 && (
          <label className="ws-org">
            Organization
            <select
              value={data.active_organization ?? ''}
              onChange={(event) => setOrg(event.target.value)}
            >
              {data.organizations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {search.get('welcome') === '1' && active ? (
        <section className="ws-welcome" aria-label="Welcome">
          <h2>Welcome to {active.name}</h2>
          <p>You now have one account for everything your organization has given you access to.</p>
          <ul>
            {data.journeys?.business_user ? (
              <li>
                <strong>Use applications.</strong>{' '}
                {data.applications
                  .filter((item) => item.launchable)
                  .map((item) => item.name)
                  .join(', ')}{' '}
                {data.applications.some((item) => item.launchable) ? 'are ready below.' : ''}
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {data.profiles && data.profiles.length > 0 ? (
        <ul className="ws-profiles" aria-label="Your profiles">
          {data.profiles.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}

      {data.onboarding.length > 0 && (
        <section className="ws-onboarding" aria-label="Getting started">
          {data.onboarding.map((text) => (
            <p key={text}>{text}</p>
          ))}
        </section>
      )}

      {data.active_organization && (
        <div className="ws-filters" role="search">
          <label className="ws-search">
            Search
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search applications"
            />
          </label>
          <div role="group" aria-label="Filter systems">
            {FILTERS.map(([id, text]) => (
              <button
                key={id}
                type="button"
                aria-pressed={filter === id}
                onClick={() => setFilter(id)}
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      )}

      {data.active_organization && (
        <section aria-label="Systems">
          <h2>Your applications</h2>
          {apps.length === 0 ? (
            <p className="ws-muted" role="status">
              {data.applications.length
                ? 'No system matches your search.'
                : 'No applications have been assigned to you yet. Ask your organization administrator for access.'}
            </p>
          ) : (
            <div className="ws-grid">
              {apps.map((app) => (
                <AppCard key={app.id} app={app} />
              ))}
            </div>
          )}
        </section>
      )}

      {data.can_administer && data.active_organization ? (
        <InvitePanel org={data.active_organization} applications={data.applications} />
      ) : null}

      {data.activity.length > 0 && (
        <section aria-label="Recent activity">
          <h2>Recent activity</h2>
          <ul className="ws-activity">
            {data.activity.map((item, index) => (
              <li key={index}>
                <span>{item.action.replace(/[._]/g, ' ')}</span>{' '}
                <span className="ws-muted">
                  {item.actor} · {item.detail}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
