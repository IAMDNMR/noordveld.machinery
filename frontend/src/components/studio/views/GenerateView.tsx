import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Check,
  CircleAlert,
  Download,
  ExternalLink,
  Eye,
  LoaderCircle,
  Play,
  Rocket,
  Square,
  X,
} from 'lucide-react'
import { ApiError } from '../../../api/client'
import {
  compileProject,
  compiledArchiveUrl,
  compiledFile,
  type Compilation,
} from '../../../api/domainKnowledge'
import {
  launchRuntime,
  stopRuntime,
  studioDemoLink,
  testRuntime,
  retainRelease,
  type RuntimeTest,
} from '../../../api/studio'
import { Callout } from '../bits'
import type { ViewProps } from './types'
import { useRuntimeStatus } from '../useRuntimeStatus'
import { ReleaseHistory } from './ReleaseHistory'
import { GeneratedFrontendView } from './GeneratedFrontendView'

const KIND: Record<string, string> = {
  executable: 'Runnable code',
  configuration: 'Validated configuration',
  contract: 'Contracts',
  preview: 'Visual preview only',
  specification: 'Specification',
  manifest: 'Manifest',
  documentation: 'Documentation',
  build: 'Build setup',
}
const message = (cause: unknown, fallback: string) =>
  cause instanceof ApiError && cause.status !== 0 ? cause.message : fallback

function Step({ done, children }: { done: boolean; children: string }) {
  return (
    <li data-done={done}>
      {done ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
      <span>{children}</span>
    </li>
  )
}

/** Real generation: the compiler's own result, its checks, the files, the generated application's tests, and the application itself running locally. */
export function GenerateView({ studio, access, busy, refresh, say, autorun = 0 }: ViewProps) {
  const [showDemo, setShowDemo] = useState(false)
  const projectId = studio.definition.id
  const revision = studio.revision
  const approved = studio.approval.design.state === 'valid'
  const processApproved = studio.approval.process.state === 'valid'
  // The application has screens: those derived from its process and records, or a custom interface that replaces them.
  const generated =
    !!studio.definition.generated_frontend || studio.definition.workflow_definitions.length > 0
  const [compiled, setCompiled] = useState<{
    projectId: string
    revision: number
    result: Compilation
  } | null>(null)
  const [working, setWorking] = useState<'compile' | 'test' | 'launch' | 'stop' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTests] = useState<(RuntimeTest & { projectId: string }) | null>(null)
  const [historyChange, setHistoryChange] = useState(0)
  const restoreTests = useCallback(
    (result: RuntimeTest) => {
      if (result.revision === revision) setTests({ ...result, projectId })
    },
    [projectId, revision],
  )
  const runtimeState = useRuntimeStatus(projectId, revision)
  const runtime = runtimeState.status ?? { running: false }
  const launchAllowed = !access || access.can.launch
  const generateAllowed = !access || access.can.generate
  const [selectedFile, setFile] = useState<{
    projectId: string
    revision: number
    path: string
    content: string
  } | null>(null)
  const tests =
    testResult?.projectId === projectId && testResult.revision === revision ? testResult : null
  const file =
    selectedFile?.projectId === projectId && selectedFile.revision === revision
      ? selectedFile
      : null

  useEffect(() => {
    if (!approved || !generated) return
    const controller = new AbortController()
    // Reconstruct the downloadable package from the saved approved revision (read-only).
    void compileProject(projectId, controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) {
          setCompiled({ projectId, revision, result })
          void refresh(true)
        }
      },
      (cause) => {
        if (!controller.signal.aborted)
          setError(
            message(
              cause,
              'The generated package could not be checked. Try Generate application again.',
            ),
          )
      },
    )
    return () => controller.abort()
  }, [projectId, revision, approved, generated, refresh])

  const lastAutorun = useRef(0)
  const current =
    compiled && compiled.projectId === projectId && compiled.revision === revision
      ? compiled.result
      : null
  const run = useCallback(async () => {
    setWorking('compile')
    setError(null)
    setFile(null)
    setTests(null)
    try {
      const result = await compileProject(projectId)
      setCompiled({ projectId, revision, result })
      if (result.status === 'generated') {
        try {
          await retainRelease(projectId, revision)
          setHistoryChange((value) => value + 1)
        } catch (cause) {
          setError(
            message(
              cause,
              'The application was generated, but its download could not be saved. Retry Save release below.',
            ),
          )
        }
      }
      await refresh(true)
    } catch (cause) {
      setError(message(cause, 'Generation failed. Nothing was changed.'))
    } finally {
      setWorking(null)
    }
  }, [projectId, revision, refresh])
  useEffect(() => {
    if (autorun > lastAutorun.current && approved && generated) {
      const timer = window.setTimeout(() => {
        lastAutorun.current = autorun
        void run()
      }, 0)
      return () => window.clearTimeout(timer)
    }
  }, [autorun, approved, generated, run])
  const test = async () => {
    setWorking('test')
    setError(null)
    setTests(null)
    try {
      setTests({ ...(await testRuntime(projectId)), projectId })
    } catch (cause) {
      setError(message(cause, 'The generated tests could not be run.'))
    } finally {
      setWorking(null)
      setHistoryChange((value) => value + 1)
    }
  }
  const launch = async () => {
    setWorking('launch')
    setError(null)
    try {
      await launchRuntime(projectId)
      await runtimeState.refresh()
    } catch (cause) {
      setError(message(cause, 'The application could not be started.'))
    } finally {
      setWorking(null)
    }
  }
  const openLiveDemo = () => {
    // Open the tab now, while the click still counts for the browser, then point it at the signed link.
    const tab = window.open('', '_blank')
    setError(null)
    studioDemoLink(projectId).then(
      (link) => {
        const url = new URL(link.path, window.location.origin).href
        if (tab) tab.location.href = url
        else window.open(url, '_blank')
      },
      (cause) => {
        tab?.close()
        setError(message(cause, 'The live demo could not be opened.'))
      },
    )
  }
  const stop = async () => {
    setWorking('stop')
    try {
      await stopRuntime(projectId)
      await runtimeState.refresh()
    } catch (cause) {
      setError(message(cause, 'The application could not be stopped.'))
    } finally {
      setWorking(null)
    }
  }
  const open = async (path: string) => {
    try {
      setFile({ projectId, revision, path, content: await compiledFile(projectId, path) })
    } catch (cause) {
      setError(message(cause, 'The file could not be shown.'))
    }
  }
  const groups = current
    ? Object.entries(current.files).reduce<Record<string, string[]>>(
        (all, [path, info]) => ({ ...all, [info.kind]: [...(all[info.kind] ?? []), path] }),
        {},
      )
    : {}
  const ready = approved && generated
  const failed = current?.checks.filter((item) => item.status === 'fail') ?? []
  const coverage = current?.checks.find((item) => item.check === 'runtime_business_coverage')
  const coverageItems =
    coverage?.items ??
    (coverage?.status === 'warn'
      ? [
          {
            category: 'unknown',
            item: 'coverage',
            text: coverage.detail,
            detail: 'Application capability',
          },
        ]
      : [])
  const connectionsOnly =
    coverageItems.length > 0 &&
    coverageItems.every((item) => item.category === 'external_integration')
  const coverageLabel = connectionsOnly
    ? `${coverageItems.length} ${coverageItems.length === 1 ? 'connection needs' : 'connections need'} setup`
    : `${coverageItems.length} ${coverageItems.length === 1 ? 'capability needs' : 'capabilities need'} attention`

  return (
    <div className="sw-view">
      <section className="sw-card" aria-label="Your application">
        <div className="sw-card__head">
          <h3>{studio.definition.metadata.name}</h3>
          <span className="sw-muted">
            {runtimeState.error
              ? 'Status unavailable'
              : !runtimeState.status
                ? 'Checking application…'
                : runtime.running
                  ? `Running · revision ${runtime.revision}`
                  : 'Application stopped'}
          </span>
        </div>
        <p className="sw-muted">
          Explore the application’s screens and navigation. The demo preview needs no hosting setup;
          “Open live demo” shows it with sample data in its own tab, with a link you can share for a
          week.
        </p>
        <div className="sw-actions">
          {generated ? (
            <button
              type="button"
              className="sw-button sw-button--primary"
              aria-expanded={showDemo}
              onClick={() => setShowDemo((value) => !value)}
            >
              <Eye size={14} /> {showDemo ? 'Close demo preview' : 'View demo'}
            </button>
          ) : null}
          {generated ? (
            <button type="button" className="sw-button" onClick={openLiveDemo}>
              <ExternalLink size={14} /> Open live demo
            </button>
          ) : null}
          {runtime.running && runtime.url ? (
            <a className="sw-button" href={runtime.url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Open application
            </a>
          ) : (
            <button
              type="button"
              className="sw-button"
              disabled={
                !ready ||
                busy ||
                working !== null ||
                !launchAllowed ||
                !runtimeState.status ||
                !!runtimeState.error ||
                runtime.available === false ||
                runtimeState.checking
              }
              onClick={() => void launch()}
            >
              {working === 'launch' ? (
                <LoaderCircle className="sw-spin" size={14} />
              ) : (
                <Play size={14} />
              )}{' '}
              Start application
            </button>
          )}
          {runtime.running && (
            <button
              type="button"
              className="sw-button"
              disabled={working !== null || !launchAllowed || !!runtimeState.error}
              onClick={() => void stop()}
            >
              <Square size={14} /> Stop application
            </button>
          )}
          {runtime.running && runtime.stale && (
            <button
              type="button"
              className="sw-button"
              disabled={!ready || working !== null || !launchAllowed || !!runtimeState.error}
              onClick={() => void launch()}
            >
              Start latest revision
            </button>
          )}
        </div>
        {!launchAllowed && (
          <p className="sw-muted">
            {access?.denied.launch ??
              'Your project access does not include starting or stopping applications.'}
          </p>
        )}
        {runtime.available === false && (
          <details className="sw-muted">
            <summary>About running the application</summary>
            <p>{runtime.reason}</p>
            <p>The demo preview above remains available without a worker service.</p>
          </details>
        )}
        {runtimeState.error && (
          <Callout tone="warn" role="status">
            {runtimeState.error}{' '}
            <button
              type="button"
              className="sw-link-button"
              disabled={runtimeState.checking}
              onClick={() => void runtimeState.refresh()}
            >
              Retry status check
            </button>
          </Callout>
        )}
        {runtime.stale && (
          <p className="sw-muted">
            The running application uses an earlier design revision. Starting a different revision
            uses a separate demo database; earlier records are retained with their original
            revision.
          </p>
        )}
      </section>
      {showDemo && generated ? (
        <GeneratedFrontendView key={projectId} definition={studio.definition} previewOnly />
      ) : null}
      <details className="sw-card sw-explainer" aria-label="Preview or application">
        <summary>Design preview and running application</summary>
        <div className="sw-grid sw-grid--2">
          <div>
            <strong>Visual preview</strong>
            <p className="sw-muted">
              The application&apos;s screens from Screens &amp; UI. Form data stays temporary and is
              not connected to rules or permissions.
            </p>
          </div>
          <div>
            <strong>Generated application</strong>
            <p className="sw-muted">
              What this stage builds: a running program with stored data, validation, process rules
              and permission checks on its server. It is checked, tested and started below.
            </p>
          </div>
        </div>
      </details>

      <section className="sw-card" aria-label="Readiness">
        <h3>Readiness</h3>
        <ul className="sw-steps">
          <Step done={processApproved}>Process approval is valid</Step>
          <Step done={generated}>The application&apos;s screens are ready</Step>
          <Step done={approved}>The design is approved at this revision</Step>
          <Step done={!!current && current.status === 'generated'}>Package checks passed</Step>
          <Step done={!!tests?.passed && !tests.skipped_count}>
            Application tests passed without skipped cases
          </Step>
        </ul>
        <div className="sw-actions">
          <button
            type="button"
            className="sw-button sw-button--primary"
            disabled={!ready || busy || working !== null || (!!access && !access.can.generate)}
            onClick={() => void run()}
          >
            {working === 'compile' ? (
              <LoaderCircle className="sw-spin" size={14} />
            ) : (
              <Rocket size={14} />
            )}{' '}
            {current ? 'Generate again' : 'Generate application'}
          </button>
          {access && !access.can.generate ? (
            <span className="sw-muted" role="note">
              {access.denied.generate ?? 'Generating is not part of your access.'}
            </span>
          ) : null}
          {!ready && (!access || access.can.generate) ? (
            <span className="sw-muted">
              {!processApproved
                ? 'Approve the process in Validation first.'
                : !generated
                  ? 'Add a process and its records first.'
                  : 'Approve the design in Validation first.'}
            </span>
          ) : null}
          <button
            type="button"
            className="sw-link-button"
            onClick={() => say('Generate the application now')}
          >
            Ask the assistant to do it
          </button>
        </div>
        {error ? (
          <Callout tone="danger" role="alert">
            {error}
          </Callout>
        ) : null}
      </section>

      {current ? (
        <>
          <section className="sw-card" aria-label="Generation result" data-state={current.status}>
            <div className="sw-card__head">
              <h3>
                {current.status === 'generated'
                  ? `Generated from revision ${current.manifest.project_revision}`
                  : 'Generation is blocked'}
              </h3>
              <span
                className={`sw-badge sw-badge--${current.status === 'generated' ? 'confirmed' : 'assumption'}`}
              >
                {Object.keys(current.files).length} files
              </span>
            </div>
            {current.plan.reasons.length ? (
              <ul className="sw-list">
                {current.plan.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : null}
            <details open={failed.length > 0}>
              <summary>
                Package checks · {current.checks.filter((item) => item.status === 'pass').length}{' '}
                passed{failed.length ? ` · ${failed.length} failed` : ''}
              </summary>
              <ul className="sw-checks">
                {current.checks.map((item) => (
                  <li key={item.check} data-status={item.status}>
                    {item.status === 'pass' ? (
                      <Check size={14} />
                    ) : item.status === 'fail' ? (
                      <X size={14} />
                    ) : (
                      <CircleAlert size={14} />
                    )}
                    <span>
                      <strong>{item.check.replaceAll('_', ' ')}</strong>{' '}
                      <small>
                        {item === coverage && item.status !== 'pass' ? coverageLabel : item.detail}
                      </small>
                    </span>
                  </li>
                ))}
              </ul>
            </details>
            {coverage && coverage.status !== 'pass' ? (
              <Callout tone="warn">
                <details className="sw-unsupported">
                  <summary>
                    <strong>{coverageLabel}</strong>{' '}
                  </summary>
                  <ul>
                    {coverageItems.map((item) => (
                      <li key={item.item}>
                        <strong>{item.detail || item.item}</strong>
                        <p>{item.text}</p>
                      </li>
                    ))}
                  </ul>
                  {connectionsOnly && (
                    <p>
                      The manual workflows remain available. A live connection requires the customer
                      system, field mapping and credentials.
                    </p>
                  )}
                </details>
              </Callout>
            ) : null}
            {failed.length ? (
              <Callout tone="danger" role="alert">
                {failed.length} check{failed.length === 1 ? '' : 's'} failed, so the application is
                not offered for download or launch.
              </Callout>
            ) : null}
            {current.status === 'generated' && generateAllowed ? (
              <a className="sw-button sw-button--primary" href={compiledArchiveUrl(projectId)}>
                <Download size={14} /> Download the application (ZIP)
              </a>
            ) : null}
            <p className="sw-muted sw-aside">
              Regenerating never overwrites files you changed: the download carries a manifest, and
              the update plan keeps modified files and reports conflicts.
            </p>
          </section>

          <details className="sw-card sw-disclosure" aria-label="Generated artifacts">
            <summary>Application files · {Object.keys(current.files).length}</summary>
            <div className="sw-artifacts">
              {Object.entries(groups)
                .sort()
                .map(([kind, paths]) => (
                  <details key={kind}>
                    <summary>
                      {KIND[kind] ?? kind} <span className="sw-count">{paths.length}</span>
                    </summary>
                    <ul>
                      {paths.map((path) => (
                        <li key={path}>
                          <button
                            type="button"
                            className="sw-link-button"
                            onClick={() => void open(path)}
                          >
                            {path}
                          </button>{' '}
                          <small>{current.files[path].bytes.toLocaleString()} bytes</small>
                        </li>
                      ))}
                    </ul>
                  </details>
                ))}
            </div>
            {file ? (
              <figure className="sw-file">
                <figcaption>
                  <code>{file.path}</code>
                  <button
                    type="button"
                    className="sw-icon-button"
                    onClick={() => setFile(null)}
                    aria-label="Close file"
                  >
                    <X size={14} />
                  </button>
                </figcaption>
                <pre>{file.content.slice(0, 12000)}</pre>
              </figure>
            ) : null}
          </details>

          {current.status === 'generated' ? (
            <div>
              <section className="sw-card" aria-label="Tests">
                <h3>Run its tests</h3>
                <p className="sw-muted">
                  The application ships with its own tests. They run in a separate process; nothing
                  from Design Studio is involved.
                </p>
                <button
                  type="button"
                  className="sw-button"
                  disabled={working !== null || !generateAllowed || runtime.available === false}
                  onClick={() => void test()}
                >
                  {working === 'test' ? (
                    <LoaderCircle className="sw-spin" size={14} />
                  ) : (
                    <Play size={14} />
                  )}{' '}
                  Run generated tests
                </button>
                {tests ? (
                  <div
                    className="sw-tests"
                    data-passed={tests.passed}
                    data-partial={!!tests.skipped_count}
                    role="status"
                  >
                    <strong>{tests.passed_count ?? tests.ran} passed</strong>{' '}
                    {tests.failed_count ? <span> · {tests.failed_count} failed</span> : null}
                    {tests.skipped_count ? <span> · {tests.skipped_count} skipped</span> : null}
                    {!tests.passed && !tests.failed_count ? <span> · Test run failed</span> : null}
                    <small>
                      {tests.seconds}s · revision {tests.revision}
                    </small>
                    <p className="sw-muted">
                      Checks cover saved records, permissions, rule outcomes and process paths. They
                      use synthetic data; customer acceptance and live integrations need their own
                      checks.
                    </p>
                    <details>
                      <summary>View all {tests.ran} tests</summary>
                      <ul>
                        {tests.cases.map((line) => (
                          <li key={line}>{line.replace(/ \.\.\. /, ' — ')}</li>
                        ))}
                      </ul>
                    </details>
                    {!tests.passed ? <pre>{tests.output ?? tests.output_tail}</pre> : null}
                    {tests.output_truncated ? (
                      <p className="sw-muted">
                        The test log exceeded the display limit. The latest output is shown.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </section>
            </div>
          ) : null}
          {current.status === 'generated' ? (
            <ReleaseHistory
              key={projectId}
              projectId={projectId}
              revision={revision}
              packageHash={current.package_sha256}
              canGenerate={generateAllowed}
              changed={historyChange}
              onRestoreTests={restoreTests}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
