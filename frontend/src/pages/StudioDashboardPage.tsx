import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  Archive,
  ArrowLeft,
  CheckCheck,
  CircleAlert,
  FolderKanban,
  LayoutDashboard,
  LayoutGrid,
  List,
  ArrowUpRight,
  PanelLeftClose,
  ShieldCheck,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import { ensureOrganization } from '../api/studio'
import {
  getProjectDashboard,
  manageProject,
  type DashboardData,
  type DashboardProject,
  type ProjectAction,
  type ProjectStatus,
} from '../api/studioProjects'
import { isAbort } from '../api/client'
import { ProjectCard, dateLabel, operationLabel } from '../components/studio/dashboard/ProjectCard'
import { ProjectActionDialog } from '../components/studio/dashboard/ProjectActionDialog'
import { BrandMark } from '../components/BrandMark'
import './StudioDashboardPage.css'
import './StudioDashboardSurface.css'

export default function StudioDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<ProjectStatus>('active')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('recent')
  const [attentionOnly, setAttentionOnly] = useState(false)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [compactNav, setCompactNav] = useState(false)
  const [notice, setNotice] = useState('')
  const [selection, setSelection] = useState<{
    project: DashboardProject
    action: ProjectAction
  } | null>(null)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const inFlight = useRef<{ signal?: AbortSignal; promise: Promise<void> } | null>(null)
  const load = useCallback(async (signal?: AbortSignal) => {
    if (inFlight.current && !inFlight.current.signal?.aborted) return inFlight.current.promise
    const task = { signal, promise: Promise.resolve() }
    const execute = async () => {
      try {
        await ensureOrganization()
        const result = await getProjectDashboard(signal)
        if (!signal?.aborted) {
          setData(result)
          setError(null)
        }
      } catch (cause) {
        if (!signal?.aborted && !isAbort(cause))
          setError(cause instanceof Error ? cause.message : 'Could not load your projects.')
      } finally {
        if (!signal?.aborted) setLoading(false)
        if (inFlight.current === task) inFlight.current = null
      }
    }
    inFlight.current = task
    task.promise = execute()
    return task.promise
  }, [])
  // load writes state only after the dashboard request resolves or fails.
  // eslint-disable-next-line react/set-state-in-effect
  useEffect(() => {
    const controller = new AbortController()
    // eslint-disable-next-line react/set-state-in-effect
    void load(controller.signal)
    return () => controller.abort()
  }, [load])
  // Stay in sync when another Studio tab saves work; do not interrupt a management dialog.
  useEffect(() => {
    const focus = () => {
      if (!selection) void load()
    }
    window.addEventListener('focus', focus)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') focus()
    }, 30000)
    return () => {
      window.removeEventListener('focus', focus)
      window.clearInterval(timer)
    }
  }, [load, selection])
  const onAction = (project: DashboardProject, action: ProjectAction) => {
    setActionError(null)
    setSelection({ project, action })
  }
  const confirm = async (name?: string) => {
    if (!selection || saving) return
    setSaving(true)
    setActionError(null)
    try {
      await manageProject(selection.project, selection.action, name)
      setNotice(
        `${selection.project.name}: ${operationLabel(`project:${selection.action}`).toLowerCase()}.`,
      )
      setSelection(null)
      await load()
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'The project could not be updated.')
      await load()
    } finally {
      setSaving(false)
    }
  }
  const rows = (data?.projects ?? [])
    .filter(
      (project) =>
        project.status === status &&
        (!attentionOnly ||
          status !== 'active' ||
          project.errors > 0 ||
          ['failed', 'interrupted'].includes(project.release?.test_status ?? '')) &&
        `${project.name} ${project.description} ${project.domain}`
          .toLowerCase()
          .includes(query.trim().toLowerCase()),
    )
    .sort((a, b) =>
      sort === 'name'
        ? a.name.localeCompare(b.name)
        : sort === 'attention'
          ? b.errors - a.errors
          : b.updated_at.localeCompare(a.updated_at),
    )
  const recentActivity = (data?.activity ?? [])
    .filter(
      (event) =>
        data?.projects.find((project) => project.id === event.project_id)?.status === status,
    )
    .slice(0, 6)
  const showFilters =
    status !== 'active' ||
    (data?.counts.active ?? 0) > 1 ||
    (data?.counts.needs_attention ?? 0) > 0 ||
    !!query ||
    attentionOnly
  return (
    <div className={`sd-dashboard${compactNav ? ' sd-dashboard--compact' : ''}`}>
      <aside className="sd-sidebar">
        <Link className="sd-brand" to="/studio" aria-label="Design Studio home">
          <span>
            <BrandMark size={29} />
          </span>
          <strong>
            Design Studio<small>APPLICATION BUILDER</small>
          </strong>
        </Link>
        <div className="sd-workspace-label">WORKSPACE</div>
        <nav aria-label="Studio workspace">
          {(
            [
              ['active', LayoutDashboard, 'Projects'],
              ['archived', Archive, 'Archive'],
              ['trashed', Trash2, 'Trash'],
            ] as const
          ).map(([value, Icon, label]) => (
            <button
              key={value}
              aria-label={`${label} ${data?.counts[value] ?? 0}`}
              className={status === value ? 'is-active' : ''}
              onClick={() => {
                setStatus(value)
                setQuery('')
                setAttentionOnly(false)
              }}
              aria-current={status === value ? 'page' : undefined}
            >
              <Icon size={18} />
              <b>{label}</b>
              <span>{data?.counts[value] ?? '—'}</span>
            </button>
          ))}
        </nav>
        <Link className="sd-back" to="/studio">
          <ArrowLeft size={16} /> Back to website
        </Link>
      </aside>
      <main className="sd-main">
        <header className="sd-topbar">
          <div className="sd-breadcrumb">
            <button
              className="sd-collapse"
              type="button"
              aria-label={compactNav ? 'Expand sidebar' : 'Collapse sidebar'}
              onClick={() => setCompactNav(!compactNav)}
            >
              <PanelLeftClose size={19} />
            </button>
            <span>Workspace</span>
            <i>/</i>
            <strong>
              {status === 'active' ? 'Overview' : status === 'archived' ? 'Archive' : 'Trash'}
            </strong>
          </div>
          <div className="sd-topbar-actions">
            <span className="sd-sync" title="Project status refreshes automatically">
              <span className="sd-live-dot" />
              Live workspace
            </span>
            <button
              type="button"
              onClick={() => {
                setLoading(true)
                void load()
              }}
              disabled={loading}
              aria-label="Refresh dashboard"
            >
              <RefreshCw size={16} className={loading ? 'sd-spinning' : ''} />
            </button>
            <span className="sd-user-avatar" aria-label="Design Studio workspace">
              <BrandMark size={19} />
            </span>
          </div>
        </header>
        <section className="sd-heading">
          <div>
            <span className="sd-eyebrow">WORKSPACE</span>
            <h1>Your applications</h1>
            <p>Manage projects, review designs, and continue work.</p>
          </div>
          {data?.can_create !== false && (
            <Link to="/design-studio/new" className="sd-primary">
              <Plus size={18} />
              New application
            </Link>
          )}
        </section>
        <div className="sd-metrics" aria-label="Workspace statistics">
          <div>
            <FolderKanban size={19} />
            <strong>{data?.counts.active ?? '—'}</strong>
            <span>Active projects</span>
          </div>
          <div>
            <CheckCheck size={19} />
            <strong>
              {data
                ? (data.counts.reviewed ??
                  data.projects.filter(
                    (project) =>
                      project.status === 'active' &&
                      (project.design_reviewed ||
                        project.reviewed >= 7 ||
                        project.design_approval === 'valid'),
                  ).length)
                : '—'}
            </strong>
            <span>Designs reviewed</span>
            <small>Design stages complete</small>
          </div>
          <div>
            <CircleAlert size={19} />
            <strong>{data?.counts.needs_attention ?? '—'}</strong>
            <span>Need attention</span>
            <small>Validation issues</small>
          </div>
          <div>
            <ShieldCheck size={19} />
            <strong>{data?.counts.approved ?? '—'}</strong>
            <span>Ready to build</span>
            <small>Final design approval passed</small>
          </div>
        </div>
        {error && (
          <div role="alert" className="sd-error">
            {error}{' '}
            <button
              onClick={() => {
                setLoading(true)
                void load()
              }}
            >
              Try again
            </button>
          </div>
        )}
        {notice && (
          <div className="sd-notice" role="status">
            {notice}
            <button onClick={() => setNotice('')} aria-label="Dismiss notice">
              Dismiss
            </button>
          </div>
        )}
        <div className="sd-content">
          <section className="sd-projects-section" aria-label="Project list">
            {status !== 'active' && (
              <div className="sd-section-title">
                <h2>
                  {status === 'archived' ? 'Archived projects' : 'Trash'} <span>{rows.length}</span>
                </h2>
                <span>Saved, with full revision history</span>
              </div>
            )}
            {status === 'active' && showFilters && (
              <div className="sd-project-tabs" aria-label="Project filters">
                <button
                  type="button"
                  aria-pressed={!attentionOnly}
                  className={!attentionOnly ? 'is-active' : ''}
                  onClick={() => setAttentionOnly(false)}
                >
                  All projects <span>{data?.counts.active ?? 0}</span>
                </button>
                <button
                  type="button"
                  aria-pressed={attentionOnly}
                  className={attentionOnly ? 'is-active' : ''}
                  onClick={() => setAttentionOnly(true)}
                >
                  <CircleAlert size={14} />
                  Needs attention <span>{data?.counts.needs_attention ?? 0}</span>
                </button>
                <div className="sd-view-switch" aria-label="Project layout">
                  <button
                    type="button"
                    aria-label="Grid view"
                    aria-pressed={view === 'grid'}
                    onClick={() => setView('grid')}
                  >
                    <LayoutGrid size={16} />
                  </button>
                  <button
                    type="button"
                    aria-label="List view"
                    aria-pressed={view === 'list'}
                    onClick={() => setView('list')}
                  >
                    <List size={18} />
                  </button>
                </div>
              </div>
            )}
            {showFilters && (
              <div className="sd-filters">
                <label className="sd-search">
                  <Search size={17} />
                  <input
                    type="search"
                    placeholder="Find a project…"
                    aria-label="Search projects"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <select
                  aria-label="Sort projects"
                  value={sort}
                  onChange={(event) => setSort(event.target.value)}
                >
                  <option value="recent">Recently updated</option>
                  <option value="name">Name A–Z</option>
                  <option value="attention">Most validation issues</option>
                </select>
              </div>
            )}
            {status === 'trashed' && (
              <p className="sd-trash-note">
                Restore a project to continue working, or permanently delete it and its saved
                releases.
              </p>
            )}
            {loading && !data ? (
              <div className="sd-empty" role="status">
                Loading your workspace…
              </div>
            ) : rows.length ? (
              <div
                className={`sd-project-grid${view === 'list' ? ' sd-project-grid--list' : ''}${rows.length === 1 ? ' sd-project-grid--single' : ''}`}
              >
                {rows.map((project) => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    busy={saving}
                    onAction={onAction}
                  />
                ))}
              </div>
            ) : (
              !error && (
                <div className="sd-empty">
                  <FolderKanban size={32} />
                  <h3>
                    {query || attentionOnly
                      ? 'No projects match your search'
                      : status === 'active'
                        ? 'Give your next idea a place to grow.'
                        : status === 'archived'
                          ? 'No archived projects'
                          : 'Trash is empty'}
                  </h3>
                  <p>
                    {query || attentionOnly
                      ? 'Try a different search or switch to All projects.'
                      : status === 'active'
                        ? 'Describe your business. Studio will help shape the process, data, and screens.'
                        : 'Projects you move here will appear in this space.'}
                  </p>
                  {status === 'active' &&
                    !query &&
                    !attentionOnly &&
                    data?.can_create !== false && (
                      <Link to="/design-studio/new" className="sd-primary">
                        <Plus size={16} />
                        Create your first application
                      </Link>
                    )}
                </div>
              )
            )}
          </section>
          <details className="sd-activity">
            <summary>
              <span className="sd-activity-icon">
                <Activity size={18} />
              </span>
              <span>Recent activity</span>
              <span className="sd-activity-count">{recentActivity.length} updates</span>
            </summary>
            {recentActivity.length ? (
              <ol>
                {recentActivity.map((event) => (
                  <li key={`${event.project_id}-${event.revision}`}>
                    <span className="sd-activity-dot">
                      {event.operation.startsWith('approve') ? (
                        <CheckCheck size={13} />
                      ) : event.operation === 'create' ? (
                        <Plus size={13} />
                      ) : (
                        <ArrowUpRight size={13} />
                      )}
                    </span>
                    <div>
                      <strong>{operationLabel(event.operation)}</strong>
                      <Link
                        to={
                          data?.projects.find((project) => project.id === event.project_id)
                            ?.status === 'trashed'
                            ? '/design-studio'
                            : `/design-studio/${event.project_id}`
                        }
                        onClick={() =>
                          setStatus(
                            data?.projects.find((project) => project.id === event.project_id)
                              ?.status ?? 'active',
                          )
                        }
                      >
                        {event.project_name}
                      </Link>
                      <small>
                        {dateLabel(event.at)} · v{event.revision}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="sd-muted">Your project history will appear here as you build.</p>
            )}
          </details>
        </div>
      </main>
      {selection && (
        <ProjectActionDialog
          {...selection}
          busy={saving}
          error={actionError}
          onClose={() => setSelection(null)}
          onConfirm={(name) => void confirm(name)}
        />
      )}
    </div>
  )
}
