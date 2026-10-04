import { useEffect, useState, type ComponentType } from 'react'
import { loadFilmData } from './launchData'
import './launch.css'

/**
 * Loads the film's records from the backend (the Noordveld graph), then the player. The acts read those records when their
 * modules load, so nothing in the film is hardcoded: change the graph and the film changes, with no frontend code change.
 */
export function LaunchFilm() {
  const [Player, setPlayer] = useState<ComponentType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    loadFilmData(controller.signal)
      .then(() => import('./LaunchFilmPlayer'))
      .then((m) => setPlayer(() => m.LaunchFilmPlayer))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'The film could not be loaded.')
      })
    return () => controller.abort()
  }, [attempt])

  if (Player) return <Player />
  return (
    <div className="lf-gate" role="status" aria-live="polite">
      {error ? (
        <>
          <p>{error}</p>
          <button type="button" onClick={() => { setError(null); setAttempt((n) => n + 1) }}>
            Try again
          </button>
        </>
      ) : (
        <p>Loading the film…</p>
      )}
    </div>
  )
}
