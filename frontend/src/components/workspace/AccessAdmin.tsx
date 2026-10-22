import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import {
  assignProjectAccess,
  getProjectAccess,
  inviteMember,
  listInvitations,
  removeProjectAccess,
  revokeInvitation,
  ROLE_LABEL,
  type InvitationRow,
  type ProjectAccess,
  type Workspace,
} from '../../api/workspace'

const message = (cause: unknown, fallback: string) =>
  cause instanceof ApiError && cause.status !== 0 ? cause.message : fallback
const ORG_ROLES = [
  'org_admin',
  'project_owner',
  'business_analyst',
  'process_owner',
  'business_approver',
  'designer',
  'developer',
  'reviewer',
]
const LEVELS = ['viewer', 'reviewer', 'editor', 'owner']

/** Invitations, for administrators. The link is shown once: only its hash is stored, and delivering it is outside this service. */
export function InvitePanel({
  org,
  applications,
}: {
  org: string
  applications: Workspace['applications']
}) {
  const [rows, setRows] = useState<InvitationRow[]>([])
  const [email, setEmail] = useState('')
  const [kind, setKind] = useState<'role' | 'app'>('app')
  const [role, setRole] = useState('reviewer')
  const [appId, setAppId] = useState(
    applications.find((item) => item.status === 'operational')?.id ?? applications[0]?.id ?? '',
  )
  const [appRole, setAppRole] = useState('customer')
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(() => {
    void listInvitations(org).then(setRows, () => setRows([]))
  }, [org])
  useEffect(reload, [reload])

  const send = async () => {
    setError(null)
    setLink(null)
    try {
      const result = await inviteMember(
        org,
        kind === 'role'
          ? { email, role }
          : { email, app_grants: [{ app_id: appId, app_role: appRole }] },
      )
      setLink(`${window.location.origin}/invite?token=${result.token}`)
      setEmail('')
      reload()
    } catch (cause) {
      setError(message(cause, 'The invitation could not be created.'))
    }
  }
  return (
    <section className="ws-access" aria-label="Invite people">
      <h2>Invite people</h2>
      <p className="ws-muted">
        An invitation joins one person to this organization with exactly what you choose. They use
        the same account everywhere.
      </p>
      <div className="ws-form">
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
          />
        </label>
        <label>
          They will
          <select value={kind} onChange={(event) => setKind(event.target.value as 'role' | 'app')}>
            <option value="app">Use an application</option>
            <option value="role">Work in Design Studio</option>
          </select>
        </label>
        {kind === 'role' ? (
          <label>
            Role
            <select value={role} onChange={(event) => setRole(event.target.value)}>
              {ORG_ROLES.map((item) => (
                <option key={item} value={item}>
                  {ROLE_LABEL[item] ?? item}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label>
              Application
              <select value={appId} onChange={(event) => setAppId(event.target.value)}>
                {applications.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              As
              <select value={appRole} onChange={(event) => setAppRole(event.target.value)}>
                <option value="customer">Business user</option>
                <option value="app_viewer">Read-only</option>
                <option value="app_admin">Application administrator</option>
              </select>
            </label>
          </>
        )}
        <button
          type="button"
          className="ws-primary"
          disabled={!email.includes('@')}
          onClick={() => void send()}
        >
          Create invitation
        </button>
      </div>
      {error ? (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      ) : null}
      {link ? (
        <p className="ws-linkbox" role="status">
          Share this link once; it cannot be shown again: <code>{link}</code>
        </p>
      ) : null}
      {rows.length ? (
        <ul className="ws-invitations" aria-label="Invitations">
          {rows.map((row) => (
            <li key={row.id}>
              <span>
                <strong>{row.email}</strong> ·{' '}
                {row.role
                  ? (ROLE_LABEL[row.role] ?? row.role)
                  : row.app_grants.map((grant) => `${grant.app_id} (${grant.app_role})`).join(', ')}
              </span>
              <span
                className={`ws-status ws-status--${row.status === 'pending' ? 'operational' : 'planned'}`}
              >
                {row.status}
              </span>
              {row.status === 'pending' ? (
                <button
                  type="button"
                  onClick={() => void revokeInvitation(org, row.id).then(reload)}
                >
                  Revoke
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

/** Who may do what inside one project. Owners and organization administrators assign access; it is separate from editing the project. */
export function ProjectAccessPanel({ org, project }: { org: string; project: string }) {
  const [access, setAccess] = useState<ProjectAccess | null>(null)
  const [person, setPerson] = useState('')
  const [level, setLevel] = useState('viewer')
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(() => {
    void getProjectAccess(org, project).then(setAccess, (cause) =>
      setError(message(cause, 'Access could not be loaded.')),
    )
  }, [org, project])
  useEffect(reload, [reload])
  const change = async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
      reload()
    } catch (cause) {
      setError(message(cause, 'Access was not changed.'))
    }
  }
  if (!access)
    return error ? (
      <div className="pixels-error" role="alert">
        {error}
      </div>
    ) : (
      <p className="ws-muted" role="status">
        Loading access…
      </p>
    )
  return (
    <div className="ws-project-access" aria-label={`Access to ${project}`}>
      <p className="ws-muted">
        {access.policy === 'assigned'
          ? 'Only the people and teams below can open this project.'
          : 'Everyone in the organization with a Design Studio role can open this project; the levels below still apply to what they can change.'}
      </p>
      <ul>
        {access.access.map((item) => (
          <li key={`${item.subject}:${item.id}`}>
            <span>
              {item.subject === 'team' ? 'Team ' : ''}
              {item.id}
            </span>{' '}
            <strong>{item.level}</strong>
            <button
              type="button"
              onClick={() =>
                void change(() => removeProjectAccess(org, project, item.subject, item.id))
              }
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="ws-form">
        <label>
          Person
          <input
            value={person}
            onChange={(event) => setPerson(event.target.value)}
            placeholder="user id"
          />
        </label>
        <label>
          Level
          <select value={level} onChange={(event) => setLevel(event.target.value)}>
            {LEVELS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!person.trim()}
          onClick={() =>
            void change(() =>
              assignProjectAccess(org, project, 'user', person.trim(), level).then(() =>
                setPerson(''),
              ),
            )
          }
        >
          Give access
        </button>
      </div>
      {error ? (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      ) : null}
    </div>
  )
}
