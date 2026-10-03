import { PackageSearch, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ApiError } from '../../api'

export function LoadingView({ label, rows = 6 }: { label: string; rows?: number }) {
  return (
    <div className="sstate sstate--loading" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <ul className="scat__grid scat__grid--grid" aria-hidden="true">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i}>
            <div className="pcard pcard--skeleton" />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ErrorView({ error, onRetry, what }: { error: ApiError; onRetry: () => void; what: string }) {
  return (
    <div className="scat__empty" role="alert">
      <TriangleAlert size={44} strokeWidth={1.1} aria-hidden="true" />
      <h3>{error.status === 0 ? 'The parts service is not reachable' : `${what} could not be loaded`}</h3>
      <p>{error.message}</p>
      <button type="button" className="button button--secondary" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}

export function EmptyView({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="scat__empty">
      <PackageSearch size={44} strokeWidth={1.1} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  )
}
