import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import {
  inviteMember,
  listInvitations,
  revokeInvitation,
  ROLE_LABEL,
  type InvitationRow,
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
            <option value="role">Organization role</option>
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
