import { useCallback, useEffect, useMemo, useRef, useState, type Ref } from 'react'
import { Code2, LoaderCircle, RefreshCw, WandSparkles, Maximize2 } from 'lucide-react'
import type { ApplicationDefinition } from '../../../api/applicationDefinition'
import { ApiError } from '../../../api/client'
import {
  generateFrontend,
  getFrontendPreview,
  getFrontendProgress,
  type FrontendPreview,
} from '../../../api/studioFrontend'
import './GeneratedFrontendView.css'

const phaseLabels: Record<string, string> = {
  preparing: 'Preparing your application…',
  editing: 'Updating the existing application…',
  art_direction: 'Designing the application…',
  planned: 'Planning pages around the process…',
  planning_repair: 'Completing the application plan…',
  checkpoint: 'Saving the design draft…',
  writing: 'Writing application pages…',
  building: 'Checking the React application…',
  repairing: 'Correcting source errors…',
  reviewing: 'Reviewing the interface in a browser…',
}

export function GeneratedFrontendView({
  definition,
  refresh,
  previewOnly = false,
  fullScreenHref,
  canGenerate = true,
  designRequest,
  onDesignRequestHandled,
  frameRef,
}: {
  definition: ApplicationDefinition
  refresh?: () => Promise<unknown>
  previewOnly?: boolean
  /** Where "Full screen" opens the application, in its own tab. */
  fullScreenHref?: string
  canGenerate?: boolean
  designRequest?: { id: number; projectId: string; brief: string } | null
  onDesignRequestHandled?: () => void
  /** The preview frame, for a host that talks to the application inside it (the screen explorer). */
  frameRef?: Ref<HTMLIFrameElement>
}) {
  const [loaded, setPreview] = useState<FrontendPreview | null>(null)
  const preview = loaded?.revision === definition.revision ? loaded : null
  const [error, setError] = useState('')
  const [diagnostics, setDiagnostics] = useState('')
  const [working, setWorking] = useState(false)
  const [phase, setPhase] = useState('preparing')
  const [source, setSource] = useState<string | null>(null)
  const [following, setFollowing] = useState(false)
  const attempted = useRef('')
  const requestedBrief = useRef('')
  const appliedDesignRequest = useRef<number | null>(null)
  const artifact = definition.generated_frontend
  // A data document has an explicit opaque navigation. srcdoc can remain blank
  // when a browser moves its containing dialog into the top layer.
  const documentUrl = useMemo(
    () =>
      preview?.current
        ? `data:text/html;charset=utf-8,${encodeURIComponent(preview.html)}`
        : undefined,
    [preview],
  )
  // Every saved project has an interface to preview: its schema-driven screens, or the generated one that replaces them.
  useEffect(() => {
    if (!definition.revision) return
    const controller = new AbortController()
    void getFrontendPreview(definition.id, controller.signal)
      .then((value) => {
        setPreview(value)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : 'Application preview could not load.')
      })
    return () => controller.abort()
  }, [definition.id, definition.revision])

  useEffect(() => {
    if (!working) return
    const controller = new AbortController()
    const poll = () => {
      void getFrontendProgress(definition.id, controller.signal)
        .then(({ progress }) => {
          if (progress?.phase) setPhase(progress.phase)
        })
        .catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 3000)
    return () => {
      controller.abort()
      clearInterval(timer)
    }
  }, [working, definition.id])

  const generate = useCallback(
    async (brief?: string) => {
      if (!canGenerate || previewOnly) return
      if (!definition.revision) {
        setError('Save this project before generating application code.')
        return
      }
      if (brief !== undefined) requestedBrief.current = brief
      setWorking(true)
      setPhase('preparing')
      setError('')
      setDiagnostics('')
      try {
        await generateFrontend(definition.id, definition.revision, requestedBrief.current)
        await refresh?.()
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Application generation failed.')
        if (cause instanceof ApiError && cause.status === 409) await refresh?.()
        if (
          cause instanceof ApiError &&
          cause.details &&
          typeof cause.details === 'object' &&
          'diagnostics' in cause.details &&
          typeof cause.details.diagnostics === 'string'
        ) {
          setDiagnostics(cause.details.diagnostics)
        }
      } finally {
        setWorking(false)
      }
    },
    [canGenerate, previewOnly, definition.id, definition.revision, refresh],
  )

  useEffect(() => {
    if (
      !designRequest ||
      designRequest.projectId !== definition.id ||
      previewOnly ||
      !canGenerate ||
      appliedDesignRequest.current === designRequest.id
    )
      return
    appliedDesignRequest.current = designRequest.id
    attempted.current = `${definition.id}:${definition.revision}`
    onDesignRequestHandled?.()
    void generate(designRequest.brief)
  }, [
    designRequest,
    definition.id,
    definition.revision,
    previewOnly,
    canGenerate,
    generate,
    onDesignRequestHandled,
  ])

  // The schema-driven screens are every project's interface; a model-written one is only made on request.
  // Entering Screens follows a job that is already running and shows a failed attempt, but never starts one.
  useEffect(() => {
    if (
      designRequest ||
      previewOnly ||
      !canGenerate ||
      artifact ||
      !definition.frontend_required ||
      !refresh
    )
      return
    let cancelled = false
    const key = `${definition.id}:${definition.revision}`
    void getFrontendProgress(definition.id)
      .then(({ progress, result }) => {
        if (cancelled || attempted.current === key) return
        attempted.current = key
        if (progress) {
          setPhase(progress.phase)
          setWorking(true)
          setFollowing(true)
        } else if (result?.status === 'failed' && result.revision === definition.revision) {
          requestedBrief.current = result.design_brief ?? ''
          setError(result.message ?? 'Generation did not finish. Retry to continue the draft.')
          setDiagnostics(result.diagnostics ?? '')
        }
      })
      .catch(() => {
        if (!cancelled) setError('Application preparation could not start. Try again.')
      })
    return () => {
      cancelled = true
    }
  }, [
    artifact,
    definition.id,
    definition.revision,
    definition.frontend_required,
    previewOnly,
    canGenerate,
    designRequest,
    refresh,
  ])

  // Resume observation of a server job after navigation or reload, without
  // issuing a second generation request against the same project.
  useEffect(() => {
    if (!following) return
    let cancelled = false
    const timer = setInterval(() => {
      void getFrontendProgress(definition.id)
        .then(async ({ progress, result: outcome }) => {
          if (cancelled || progress) return
          const result = await getFrontendPreview(definition.id)
          if (cancelled) return
          setFollowing(false)
          setWorking(false)
          setPreview(result)
          await refresh?.()
          if (outcome?.status === 'failed' || result.kind !== 'generated') {
            requestedBrief.current = outcome?.design_brief ?? ''
            setError(
              outcome?.message ??
                'Generation ended without a saved interface. Retry to continue the draft.',
            )
            setDiagnostics(outcome?.diagnostics ?? '')
          }
        })
        .catch(() => {})
    }, 3000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [following, definition.id, refresh])
  return (
    <section className="studio-generated" data-canvas aria-label="Project-specific application">
      {!preview && !error ? (
        <p role="status">
          <LoaderCircle className="sw-spin" size={16} /> Loading application preview…
        </p>
      ) : null}
      {!previewOnly && canGenerate && !working && error && !artifact ? (
        <div className="studio-generated__controls">
          <button
            type="button"
            className="sw-button sw-button--primary"
            disabled={working || !refresh}
            onClick={() => void generate()}
          >
            <WandSparkles size={16} /> Retry generation
          </button>
        </div>
      ) : null}
      {working ? (
        <p role="status">
          <LoaderCircle className="sw-spin" size={16} />{' '}
          {phaseLabels[phase] ?? 'Generating the application…'} This can take a few minutes.
        </p>
      ) : null}
      {error ? (
        <p className="studio-generated__error" role="alert">
          {error}
        </p>
      ) : null}
      {diagnostics ? (
        <details className="studio-generated__diagnostics">
          <summary>Technical details</summary>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{diagnostics}</pre>
        </details>
      ) : null}
      {artifact || preview ? (
        <>
          <div className="studio-generated__bar">
            <span>
              {artifact ? 'Your application' : 'Process draft preview'}{' '}
              <small>
                ·{' '}
                {artifact
                  ? `${artifact.pages.length} pages`
                  : preview?.screens
                    ? `${preview.screens.workflows} processes, ${preview.screens.records} record types, ${preview.screens.steps} steps, ${preview.screens.roles} roles`
                    : 'from your process'}
              </small>
            </span>
            <div className="studio-generated__tools">
              {artifact ? (
                <button
                  type="button"
                  className="sw-link-button"
                  onClick={() => setSource(source ? null : 'src/App.tsx')}
                >
                  <Code2 size={14} /> {source ? 'Show application' : 'View source'}
                </button>
              ) : null}
              {fullScreenHref ? (
                <a
                  className="sw-link-button"
                  href={fullScreenHref}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Maximize2 size={14} /> Full screen
                </a>
              ) : null}
            </div>
          </div>
          {preview && !preview.current ? (
            <p role="status" className="studio-generated__warning">
              <RefreshCw size={15} /> The process or data model has changed. Regenerate this
              interface before building the application.
              {!previewOnly && canGenerate && refresh ? (
                <button
                  className="sw-link-button"
                  disabled={working}
                  onClick={() => void generate()}
                >
                  Update application
                </button>
              ) : null}
            </p>
          ) : null}
          {source && artifact ? (
            <div className="studio-generated__source">
              <nav aria-label="Generated source files">
                {Object.keys(artifact.files).map((file) => (
                  <button
                    type="button"
                    key={file}
                    aria-pressed={source === file}
                    onClick={() => setSource(file)}
                  >
                    {file}
                  </button>
                ))}
              </nav>
              <pre>
                <code>{artifact.files[source]}</code>
              </pre>
            </div>
          ) : preview?.current ? (
            <iframe
              ref={frameRef}
              className="studio-generated__frame"
              title={`${definition.metadata.name} generated application`}
              sandbox="allow-scripts"
              referrerPolicy="no-referrer"
              src={documentUrl}
            />
          ) : !preview && !error ? (
            <p role="status">Loading application…</p>
          ) : null}
          {!previewOnly && artifact ? (
            <details className="studio-generated__checks">
              <summary>Build checks and page coverage</summary>
              {canGenerate ? (
                <button
                  type="button"
                  className="sw-link-button"
                  disabled={working || !refresh}
                  onClick={() => void generate()}
                >
                  Rebuild interface
                </button>
              ) : null}
              <ul>
                {artifact.checks.map((check) => (
                  <li key={check}>{check}</li>
                ))}
              </ul>
              <p>
                Page bindings are declared by the model. Review each interaction before approving
                the design.
              </p>
              <ul>
                {artifact.pages.map((page) => (
                  <li key={page.id}>
                    <strong>{page.title}</strong> — {page.purpose}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {!previewOnly && canGenerate && !artifact ? (
            <details className="studio-generated__checks">
              <summary>Interface details</summary>
              <p>
                These screens are derived from the process and records. A language model can write a
                tailored interface to replace them.
              </p>
              <button
                type="button"
                className="sw-link-button"
                disabled={working || !refresh}
                onClick={() => void generate()}
              >
                Create tailored interface
              </button>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
