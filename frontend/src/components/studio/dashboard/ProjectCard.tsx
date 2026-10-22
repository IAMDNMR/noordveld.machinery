import {
  ArrowUpRight,
  Archive,
  Box,
  Truck,
  Factory,
  Warehouse,
  Users,
  Wallet,
  PanelsTopLeft,
  Database,
  CircleAlert,
  MoreHorizontal,
  Pencil,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { createElement, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { DashboardProject, ProjectAction } from '../../../api/studioProjects'

export const operationLabel = (operation: string) =>
  ({
    create: 'Created project',
    update: 'Updated the design',
    'assistant:apply': 'Applied an assistant change',
    'assistant:revert': 'Restored an earlier design',
    'approve:process': 'Approved the process',
    'approve:design': 'Approved the design',
    'generate:screens': 'Generated screens',
    'project:rename': 'Renamed project',
    'project:archive': 'Archived project',
    'project:trash': 'Moved project to Trash',
    'project:restore': 'Restored project',
    'project:delete': 'Permanently deleted project',
  })[operation] ?? operation.replaceAll(':', ' · ')
export function dateLabel(value: string) {
  if (!value) return 'No recorded activity'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? 'Unknown date'
    : new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date)
}

const DOMAIN_ICONS = {
  logistics: Truck,
  manufacturing: Factory,
  inventory: Warehouse,
  crm: Users,
  finance: Wallet,
}

export function ProjectCard({
  project,
  busy,
  onAction,
}: {
  project: DashboardProject
  busy: boolean
  onAction: (project: DashboardProject, action: ProjectAction) => void
}) {
  const menu = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !menu.current?.contains(event.target))
        menu.current?.removeAttribute('open')
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menu.current?.open) {
        menu.current.removeAttribute('open')
        menu.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [])
  const needsAttention =
    !!project.errors || ['failed', 'interrupted'].includes(project.release?.test_status ?? '')
  const status = needsAttention
    ? 'Needs attention'
    : project.design_approval === 'valid'
      ? 'Design approved'
      : 'Ready to review'
  return (
    <article className="sd-project">
      <header>
        <span className="sd-project-icon">
          {createElement(
            DOMAIN_ICONS[project.domain as keyof typeof DOMAIN_ICONS] ??
              (/transport|logistic/i.test(project.domain)
                ? Truck
                : /warehouse|inventory/i.test(project.domain)
                  ? Warehouse
                  : Box),
            {
              size: 22,
            },
          )}
        </span>
        <div className="sd-project-identity">
          <div className="sd-card-category">{project.domain.replaceAll('_', ' ')}</div>
          <h2>{project.name}</h2>
        </div>
        <span className={`sd-status ${needsAttention ? 'sd-status--attention' : ''}`}>
          {project.status === 'active'
            ? status
            : project.status === 'archived'
              ? 'Archived'
              : 'In Trash'}
        </span>
        {project.can_edit && (
          <details className="sd-menu" ref={menu}>
            <summary aria-label={`Actions for ${project.name}`}>
              <MoreHorizontal size={20} />
            </summary>
            <div>
              {project.status !== 'trashed' && (
                <button disabled={busy} onClick={() => onAction(project, 'rename')}>
                  <Pencil size={15} />
                  Rename
                </button>
              )}
              {project.status === 'active' ? (
                <button disabled={busy} onClick={() => onAction(project, 'archive')}>
                  <Archive size={15} />
                  Archive
                </button>
              ) : (
                <button disabled={busy} onClick={() => onAction(project, 'restore')}>
                  <RotateCcw size={15} />
                  Restore
                </button>
              )}
              {project.status !== 'trashed' && (
                <button
                  disabled={busy}
                  className="sd-danger"
                  onClick={() => onAction(project, 'trash')}
                >
                  <Trash2 size={15} />
                  Move to Trash
                </button>
              )}
            </div>
          </details>
        )}
      </header>
      <p className="sd-description">
        {project.description || 'Your next application, taking shape.'}
      </p>
      {project.runtime?.running && (
        <p className="sd-runtime">
          <span className="sd-live-dot" />
          Application running{project.runtime.stale ? ' · earlier revision' : ''}
        </p>
      )}
      {project.release ? (
        <p className="sd-runtime">
          Release saved ·{' '}
          {project.release.test_status === 'partial'
            ? 'Tests have skipped cases'
            : project.release.test_status === 'passed'
              ? 'Tests passed'
              : project.release.test_status === 'failed' ||
                  project.release.test_status === 'interrupted'
                ? 'Tests need attention'
                : project.release.test_status === 'running'
                  ? 'Tests running'
                  : 'Not tested'}
        </p>
      ) : null}
      <div className="sd-project-facts">
        <span>
          <PanelsTopLeft size={15} />
          {project.screens} screens
        </span>
        <span>
          <Database size={15} />
          {project.entities} entities
        </span>
        <span>Revision {project.revision}</span>
      </div>
      <div className="sd-progress-label">
        <span>
          Current stage <b>{project.stage_label}</b>
        </span>
        <strong>
          {project.reviewed}/{project.stage_count - 1} stages reviewed
        </strong>
      </div>
      <progress
        value={project.reviewed}
        max={project.stage_count - 1}
        aria-label={`${project.name}: stages reviewed`}
      />
      <div className="sd-project-bottom">
        <small>Updated {dateLabel(project.updated_at)}</small>
        {project.status !== 'trashed' ? (
          <div className="sd-project-actions">
            {project.runtime?.running && project.runtime.url && (
              <a href={project.runtime.url} target="_blank" rel="noreferrer">
                Open application <ArrowUpRight size={16} />
              </a>
            )}
            {project.screens > 0 && (
              <Link className="sd-preview-link" to={`/design-studio/${project.id}?stage=screen`}>
                Review screens
              </Link>
            )}
            <Link to={`/design-studio/${project.id}?stage=${project.stage}`}>
              Open project <ArrowUpRight size={16} />
            </Link>
          </div>
        ) : (
          <div className="sd-project-actions">
            <span>Restore to continue</span>
            {project.can_edit && project.can_delete && (
              <button
                className="sd-danger"
                disabled={busy}
                onClick={() => onAction(project, 'delete')}
              >
                <Trash2 size={15} /> Delete permanently
              </button>
            )}
          </div>
        )}
      </div>
      {!!project.errors && project.status === 'active' && (
        <div className="sd-issue">
          <CircleAlert size={14} />
          {project.errors} validation {project.errors === 1 ? 'issue' : 'issues'} to resolve
        </div>
      )}
    </article>
  )
}
