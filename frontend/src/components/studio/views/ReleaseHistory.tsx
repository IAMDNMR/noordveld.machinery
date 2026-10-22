import { useEffect, useState } from 'react'
import {
  getReleases,
  retainRelease,
  releaseArchiveUrl,
  type RuntimeTest,
  type StudioRelease,
} from '../../../api/studio'

type Props = {
  projectId: string
  revision: number
  packageHash?: string
  canGenerate: boolean
  changed: number
  onRestoreTests: (result: RuntimeTest) => void
}

/** Releases remain attached to their file hash, even after a newer revision is generated. */
export function ReleaseHistory({
  projectId,
  revision,
  packageHash,
  canGenerate,
  changed,
  onRestoreTests,
}: Props) {
  const [releases, setReleases] = useState<StudioRelease[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    void getReleases(projectId, controller.signal).then(
      (items) => {
        if (controller.signal.aborted) return
        setReleases(items)
        setError(null)
        const latest = items.find((item) => item.id === packageHash)?.tests[0]
        if (latest?.result?.ran !== undefined) onRestoreTests(latest.result)
      },
      () => {
        if (!controller.signal.aborted)
          setError('Release history is unavailable. Check durable storage and retry.')
      },
    )
    return () => controller.abort()
    // Retry and completed tests explicitly invalidate this external history snapshot.
    // eslint-disable-next-line react/exhaustive-effect-dependencies
  }, [projectId, packageHash, changed, retry, onRestoreTests])
  const save = async () => {
    setSaving(true)
    try {
      await retainRelease(projectId, revision)
      setRetry((value) => value + 1)
    } catch {
      setError(
        'The release could not be retained. Check storage and refresh if the project changed.',
      )
    } finally {
      setSaving(false)
    }
  }
  return (
    <section className="sw-card" aria-label="Release history">
      <div className="sw-card__head">
        <h3>Saved releases</h3>
        {canGenerate ? (
          <button
            className="sw-button"
            disabled={saving || !packageHash}
            onClick={() => void save()}
          >
            {saving ? 'Saving…' : 'Save release'}
          </button>
        ) : null}
      </div>
      {error ? (
        <p role="alert">
          {error}{' '}
          <button className="sw-link-button" onClick={() => setRetry((value) => value + 1)}>
            Retry history
          </button>
        </p>
      ) : null}
      {!releases.length && !error ? (
        <p className="sw-muted">Generate an application to save its code and download here.</p>
      ) : null}
      {releases.map((item) => (
        <details key={item.id}>
          <summary>
            Revision {item.revision} · {new Date(item.created).toLocaleString()} ·{' '}
            {item.tests[0]?.status ?? 'Not tested'}
          </summary>
          <p className="sw-muted sw-release-digest">
            Package {item.id.slice(0, 12)} · Archive SHA-256 {item.archive_sha256}
          </p>
          {canGenerate ? (
            <a className="sw-button" href={releaseArchiveUrl(projectId, item.id)}>
              Download saved release
            </a>
          ) : null}
          <ul>
            {item.tests.map((run) => (
              <li key={run.id}>
                {new Date(run.started).toLocaleString()} · {run.status}
                {run.result?.ran !== undefined
                  ? ` · ${run.result.passed_count ?? 0} passed, ${run.result.failed_count ?? 0} failed, ${run.result.skipped_count ?? 0} skipped`
                  : ''}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </section>
  )
}
