import { TriangleAlert } from 'lucide-react'
import type { ApiError } from '../../api'

export function ThinkingNotice() {
  return (
    <div className="pi-thinking" role="status" aria-live="polite" aria-busy="true">
      <span className="pi-thinking__dot" aria-hidden="true" />
      <p>Understanding the question and checking the knowledge graph…</p>
    </div>
  )
}

/** Plain-language explanation for each way a request can fail. Nothing is invented as a fallback answer. */
export function errorMessage(error: ApiError): string {
  if (error.code === 'graph_unavailable' || error.status === 503) return 'Neo4j is currently unavailable. Parts Intelligence cannot verify this relationship right now.'
  if (error.status === 0) return 'The Parts Intelligence service could not be reached. Check that the API is running.'
  if (error.status === 404) return 'That part is not in the catalogue.'
  if (error.status === 422) return 'The question could not be processed. Try rephrasing it.'
  return 'Something went wrong while answering. Please try again.'
}

export function ErrorNotice({ error, onRetry, title = 'The question could not be answered' }: { error: ApiError; onRetry?: () => void; title?: string }) {
  return (
    <div className="pi-error" role="alert">
      <TriangleAlert size={22} strokeWidth={1.5} aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <p>{errorMessage(error)}</p>
        {onRetry ? (
          <button type="button" className="button button--secondary" onClick={onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    </div>
  )
}
