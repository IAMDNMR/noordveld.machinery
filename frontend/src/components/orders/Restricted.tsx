import { Link, useLocation } from 'react-router-dom'

/** Shown when the backend refuses a page: not signed in (401) or the role / ownership does not allow it (403). */
export function Restricted({ reason }: { reason: 'signed_out' | 'forbidden' | 'not_found' }) {
  const { pathname, search } = useLocation()
  const text = {
    signed_out: ['Sign in to continue', 'This page shows order and request records, so it needs a signed-in account.'],
    forbidden: ['Not available for your role', 'Your account does not have access to this page or record.'],
    not_found: ['Order not found', 'There is no order or request with that reference.'],
  }[reason]
  return (
    <div className="card card-pad ord-restricted" role="alert">
      <h2>{text[0]}</h2>
      <p className="muted">{text[1]}</p>
      {reason === 'signed_out' ? (
        <Link className="btn btn-primary" to={`/sign-in?next=${encodeURIComponent(pathname + search)}`}>
          Sign in
        </Link>
      ) : (
        <Link className="btn btn-secondary" to="/orders">
          Back to orders
        </Link>
      )}
    </div>
  )
}
