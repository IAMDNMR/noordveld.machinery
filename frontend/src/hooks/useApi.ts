import { useCallback, useEffect, useState } from 'react'
import { ApiError, isAbort } from '../api'

export interface ApiState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  reload: () => void
}

/**
 * Runs `load` whenever `key` changes, aborting the previous request. `key` must change exactly when the request does
 * (build it from the request's inputs); `load` itself may be an inline function.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, key: string): ApiState<T> {
  const [state, setState] = useState<{ data: T | null; error: ApiError | null; loading: boolean }>({ data: null, error: null, loading: true })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setState((s) => ({ ...s, error: null, loading: true }))
    load(controller.signal).then(
      (data) => setState({ data, error: null, loading: false }),
      (error: unknown) => {
        if (isAbort(error)) return
        setState({ data: null, error: error instanceof ApiError ? error : new ApiError(0, 'unknown', 'Something went wrong.'), loading: false })
      },
    )
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for the request's inputs
  }, [key, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return { ...state, reload }
}
