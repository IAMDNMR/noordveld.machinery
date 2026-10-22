import { useCallback, useEffect, useRef, useState } from 'react'
import { getRuntime, type RuntimeStatus } from '../../api/studio'
import { isAbort } from '../../api/client'

/** Unknown and unreachable runtimes must not be presented as stopped applications. */
export function useRuntimeStatus(projectId: string, revision: number) {
  const pending = useRef<AbortController | null>(null)
  const [snapshot, setSnapshot] = useState<{ projectId: string; status: RuntimeStatus } | null>(
    null,
  )
  const [error, setError] = useState<{ projectId: string; message: string } | null>(null)
  const [checking, setChecking] = useState(true)
  const refresh = useCallback(async () => {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setChecking(true)
    try {
      const status = await getRuntime(projectId, controller.signal)
      if (!controller.signal.aborted) {
        setSnapshot({ projectId, status })
        setError(null)
      }
    } catch (cause) {
      if (!controller.signal.aborted && !isAbort(cause))
        setError({
          projectId,
          message:
            cause instanceof Error ? cause.message : 'Application status could not be checked.',
        })
    } finally {
      if (!controller.signal.aborted) setChecking(false)
    }
  }, [projectId])
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0)
    const focus = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    window.addEventListener('focus', focus)
    const timer = window.setInterval(focus, 30000)
    return () => {
      pending.current?.abort()
      window.clearTimeout(initial)
      window.removeEventListener('focus', focus)
      window.clearInterval(timer)
    }
  }, [refresh])
  const currentStatus = snapshot?.projectId === projectId ? snapshot.status : null
  return {
    status:
      currentStatus?.running && currentStatus.revision !== undefined
        ? { ...currentStatus, stale: currentStatus.revision !== revision }
        : currentStatus,
    error: error?.projectId === projectId ? error.message : null,
    checking,
    refresh,
  }
}
