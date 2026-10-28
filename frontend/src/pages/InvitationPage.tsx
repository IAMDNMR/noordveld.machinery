import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, setActiveOrganization } from '../api/client'
import {
  acceptInvitation,
  previewInvitation,
  ROLE_LABEL,
  type InvitationPreview,
} from '../api/workspace'
import { useSession } from '../store/session'
import './InvitationPage.css'

const appName = (id: string) =>
  id
    .replace(/^project:/, 'Generated application ')
    .replace(/_/g, ' ')
    .replace(/^\w/, (letter) => letter.toUpperCase())
const roleText = (role: string) =>
  ROLE_LABEL[role] ??
  (role === 'app_admin'
    ? 'Application administrator'
    : role === 'app_viewer'
      ? 'Read-only'
      : role.replace(/_/g, ' '))

/** What the invitation gives, in words a person can check before accepting. Nothing here grants anything: the server does that on accept. */
function Offer({ invitation }: { invitation: InvitationPreview }) {
  return (
    <ul className="inv-offer" aria-label="What this invitation gives you">
      {invitation.role ? (
        <li>
          <strong>{roleText(invitation.role)}</strong> in {invitation.organization.name}
        </li>
      ) : null}
      {invitation.app_grants.map((grant) => (
        <li key={`${grant.app_id}:${grant.app_role}`}>
          <strong>{appName(grant.app_id)}</strong> as {roleText(grant.app_role)}
          <small>Use this application with your own organization's data.</small>
        </li>
      ))}
    </ul>
  )
}

/** Landing page for an invitation link: verify it, sign in, accept it, and see what you can do first. */
export default function InvitationPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const { user, ready, signOut } = useSession()
  const navigate = useNavigate()
  const [invitation, setInvitation] = useState<InvitationPreview | null>(null)
  const [problem, setProblem] = useState<string | null>(
    token.length < 20
      ? 'This invitation link is incomplete. Ask the person who invited you to send it again.'
      : null,
  )
  const [wrongAccount, setWrongAccount] = useState(false)
  const [accepting, setAccepting] = useState(false)

  useEffect(() => {
    if (token.length < 20) return
    const controller = new AbortController()
    previewInvitation(token, controller.signal).then(setInvitation, (cause) => {
      if (!controller.signal.aborted)
        setProblem(
          cause instanceof ApiError && cause.status === 404
            ? 'This invitation is invalid, has expired, or has already been used. Ask your organization administrator for a new one.'
            : 'The invitation could not be checked right now. Try again in a moment.',
        )
    })
    return () => controller.abort()
  }, [token])

  const accept = async () => {
    setAccepting(true)
    setProblem(null)
    try {
      const result = await acceptInvitation(token)
      setActiveOrganization(result.org_id)
      navigate(`/workspace?welcome=1&org=${encodeURIComponent(result.org_id)}`)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) setWrongAccount(true)
      else
        setProblem(
          cause instanceof ApiError && cause.status === 404
            ? 'This invitation is invalid, has expired, or has already been used.'
            : 'The invitation could not be accepted. Nothing was changed.',
        )
    } finally {
      setAccepting(false)
    }
  }

  return (
    <main className="inv-page">
      <section className="inv-card" aria-labelledby="inv-title">
        <p className="inv-eyebrow">INVITATION</p>
        {invitation ? (
          <>
            <h1 id="inv-title">Join {invitation.organization.name}</h1>
            <p className="inv-lede">
              This invitation was sent to <strong>{invitation.email_hint}</strong> and is valid
              until{' '}
              {new Date(invitation.expires_at).toLocaleDateString(undefined, { dateStyle: 'long' })}
              .
            </p>
            <Offer invitation={invitation} />
            {!ready ? (
              <p role="status">Checking your sign-in…</p>
            ) : !user ? (
              <div className="inv-actions">
                <Link
                  className="inv-primary"
                  to={`/sign-in?next=${encodeURIComponent(`/invite?token=${token}`)}`}
                >
                  Sign in to accept
                </Link>
                <p className="inv-note">
                  You use one account for every application in your organization. Sign in with the
                  account that belongs to the invited email address.
                </p>
              </div>
            ) : wrongAccount ? (
              <div className="inv-actions" role="alert">
                <p>
                  <strong>This invitation is for a different account.</strong> You are signed in as{' '}
                  {user.name}. Sign in with the account that owns {invitation.email_hint} to accept
                  it.
                </p>
                <button
                  type="button"
                  className="inv-primary"
                  onClick={() =>
                    void signOut().then(() =>
                      navigate(`/sign-in?next=${encodeURIComponent(`/invite?token=${token}`)}`),
                    )
                  }
                >
                  Switch account
                </button>
              </div>
            ) : (
              <div className="inv-actions">
                <p className="inv-note">Signed in as {user.name}.</p>
                <button
                  type="button"
                  className="inv-primary"
                  disabled={accepting}
                  onClick={() => void accept()}
                >
                  {accepting ? 'Accepting…' : 'Accept invitation'}
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <h1 id="inv-title">
              {problem ? 'This invitation cannot be used' : 'Checking your invitation…'}
            </h1>
            {problem ? (
              <p className="inv-lede" role="alert">
                {problem}
              </p>
            ) : (
              <p role="status" className="inv-lede">
                One moment.
              </p>
            )}
            {problem ? (
              <Link className="inv-secondary" to="/sign-in">
                Go to sign in
              </Link>
            ) : null}
          </>
        )}
        {invitation && problem ? (
          <p className="inv-error" role="alert">
            {problem}
          </p>
        ) : null}
      </section>
    </main>
  )
}
