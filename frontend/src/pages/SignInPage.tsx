import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getDemoUsers, type DemoUser } from '../api/orders'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { roleLabel, useSession } from '../store/session'
import '../styles/wf.css'
import '../components/orders/orders.css'

const PURPOSE: Record<DemoUser['role'], string> = {
  END_USER: 'Needs a part: browse, investigate, get a recommendation, place an order and follow it through allocation, shipment and delivery.',
  ORDER_PROCESSOR: 'Processes customer orders: checks fitment, stock, supply and shipment, and moves orders through their steps.',
}

/** Demo sign-in: choose one of the seeded demo accounts. No password and no identity provider; the backend keeps a signed session. */
export default function SignInPage() {
  usePageMeta({ title: 'Sign in', description: 'Sign in to the Noordveld demo as an End User or an Order Processor.', path: '/sign-in' })
  const users = useApi((s) => getDemoUsers(s), 'demo-users')
  const { user, signIn } = useSession()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const choose = async (id: string) => {
    setBusy(id)
    setError(null)
    try {
      await signIn(id)
      const next = params.get('next')
      navigate(next && next.startsWith('/') ? next : '/orders')
    } catch {
      setError('That account could not be signed in. Please try again.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="wf ord-page">
      <div className="wf-container ord-signin">
        <p className="eyebrow">Noordveld demo</p>
        <h1>Sign in</h1>
        <p className="lede">Choose a demo account. Each account has one role, and the server decides what that role may see and do.</p>
        {user ? (
          <p className="pi-note">
            You are signed in as {user.name} ({roleLabel(user.role)}). <Link className="link-more" to="/orders">Continue</Link>
          </p>
        ) : null}
        {error ? (
          <p className="pi-error" role="alert">
            {error}
          </p>
        ) : null}
        {users.error ? (
          <p className="pi-empty">Demo accounts could not be loaded. Check that the API is running.</p>
        ) : !users.data ? (
          <p className="muted">Loading demo accounts…</p>
        ) : (
          <ul className="grid grid-3 ord-accounts">
            {users.data.map((u) => (
              <li key={u.id} className="card card-pad ord-account">
                <span className={`badge ${u.role === 'ORDER_PROCESSOR' ? 'badge-info' : 'badge-good'}`}>{roleLabel(u.role)}</span>
                <h2>{u.name}</h2>
                {u.customer ? <p className="small muted">For {u.customer}</p> : <p className="small muted">Noordveld order processing</p>}
                <p className="small">{PURPOSE[u.role]}</p>
                <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => choose(u.id)}>
                  {busy === u.id ? 'Signing in…' : `Sign in as ${u.name.replace(/ \(demo\)$/, '')}`}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="small muted ord-signin__note">Demo accounts only. There is no password, and no payment or real order placement is connected.</p>
      </div>
    </div>
  )
}
