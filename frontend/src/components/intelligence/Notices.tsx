import { TriangleAlert } from 'lucide-react'
import type { ApiError } from '../../api'

export function ThinkingNotice() {
  return (
    <div className="pi-thinking" role="status" aria-live="polite" aria-busy="true">
      <span className="pi-thinking__dot" aria-hidden="true" />
      <p>
        Understanding the question, identifying the parts and machines in it, querying the knowledge graph, verifying the results and preparing the answer…
      </p>
    </div>
  )
}

/** Plain-language explanation for each way a request can fail. Nothing is invented as a fallback answer. */
export function errorMessage(error: ApiError): string {
  if (error.code === 'llm_unavailable') return 'The question-understanding service is not available right now, so the question could not be answered. Please try again in a moment.'
  if (error.code === 'llm_invalid_response') return 'The question could not be understood reliably. Please rephrase it and try again.'
  if (error.code === 'graph_unavailable' || error.status === 503) return 'Neo4j is currently unavailable. Parts Intelligence cannot verify this relationship right now.'
  if (error.status === 0) return 'The Parts Intelligence service could not be reached. Check that the API is running.'
  if (error.status === 404) return 'That part is not in the catalogue.'
  if (error.status === 422) return 'The question could not be processed. Try rephrasing it.'
  if (error.status >= 500 && error.code === 'error') return 'The Parts Intelligence service did not respond. Check that the API is running, then try again.'
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
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    </div>
  )
}
