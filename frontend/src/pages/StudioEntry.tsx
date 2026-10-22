import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { SessionProvider, useSession } from '../store/session'
import StudioWorkspacePage from './StudioWorkspacePage'
import StudioDashboardPage from './StudioDashboardPage'
import './StudioLandingPage.css'

function Preview({ createNew = false }: { createNew?: boolean }) {
  const { projectId } = useParams()
  const { user, ready, signIn } = useSession()
  const attempted = useRef(false)
  const [error, setError] = useState(false)
  const enter = () => {
    setError(false)
    void signIn('preview').catch(() => setError(true))
  }
  useEffect(() => {
    if (ready && !user && !attempted.current) {
      attempted.current = true
      enter()
    }
    // One local demo entry; never changes the commerce session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user])
  if (user) return projectId || createNew ? <StudioWorkspacePage /> : <StudioDashboardPage />
  return (
    <div className="sl-access">
      <span className="sl-eyebrow">DESIGN STUDIO</span>
      <h1>{error ? 'The preview is unavailable' : 'Opening your creative workspace…'}</h1>
      <p>
        {error
          ? 'The Design Studio could not open just now. Please try again in a moment, or explore the demo while we sort it out.'
          : 'A dedicated demo workspace. No new account needed.'}
      </p>
      {error ? (
        <>
          <Link className="sl-primary" to="/design-studio/demo">
            Explore the demo
          </Link>
          <button className="sl-text-link" onClick={enter}>
            Try again
          </button>
        </>
      ) : (
        <div className="sl-loading" role="status" aria-label="Opening Studio" />
      )}
      <Link to="/studio">Back to Design Studio</Link>
    </div>
  )
}

export default function StudioEntry({ createNew = false }: { createNew?: boolean }) {
  return (
    <SessionProvider scope="studio">
      <Preview createNew={createNew} />
    </SessionProvider>
  )
}
