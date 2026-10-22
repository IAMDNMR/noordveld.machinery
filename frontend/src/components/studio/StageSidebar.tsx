import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, PanelLeftClose, PanelLeftOpen, Plus } from 'lucide-react'
import { STAGES, STATUS_LABEL, type StageKey, type StudioState } from '../../api/studio'
import type { ApplicationDefinition } from '../../api/applicationDefinition'
import { BrandMark } from '../BrandMark'
import { Meter, STAGE_ICON } from './bits'

type Props = {
  collapsed: boolean
  onToggle: () => void
  studio: StudioState | null
  stage: StageKey
  onStage: (stage: StageKey) => void
  projects: ApplicationDefinition[]
  projectId: string | null
  onOpen: (id: string) => void
  onNew: () => void
}

/** Where the project is, stage by stage. Every status is computed by the server from the saved specification, its checks and its approvals. */
export function StageSidebar({
  collapsed,
  onToggle,
  studio,
  stage,
  onStage,
  projects,
  projectId,
  onOpen,
  onNew,
}: Props) {
  const [switching, setSwitching] = useState(false)
  const done = studio
    ? STAGES.filter(([key]) => studio.stages[key].status === 'completed').length
    : 0
  const name = studio?.definition.metadata.name ?? 'New project'
  return (
    <aside className="sw-left" data-collapsed={collapsed} aria-label="Project navigation">
      <div className="sw-left__top">
        <Link className="sw-brand" to="/design-studio" aria-label="Design Studio, back to overview">
          <span className="sw-brand__mark">
            <BrandMark size={24} />
          </span>
          {collapsed ? null : (
            <span>
              <strong>Design Studio</strong>
            </span>
          )}
        </Link>
        <button
          type="button"
          className="sw-icon-button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          aria-expanded={!collapsed}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
      {collapsed ? null : (
        <div className="sw-project">
          <button
            type="button"
            className="sw-project__button"
            onClick={() => setSwitching((open) => !open)}
            aria-expanded={switching}
            aria-haspopup="listbox"
          >
            <span>
              <small>Project</small>
              <strong>{name}</strong>
            </span>
            <ChevronDown size={16} aria-hidden="true" />
          </button>
          {switching ? (
            <div className="sw-project__menu" role="listbox" aria-label="Projects">
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  setSwitching(false)
                  onNew()
                }}
              >
                <Plus size={14} aria-hidden="true" /> New project
              </button>
              {projects.map((project) => (
                <button
                  type="button"
                  role="option"
                  aria-selected={project.id === projectId}
                  key={project.id}
                  onClick={() => {
                    setSwitching(false)
                    onOpen(project.id)
                  }}
                >
                  <span>{project.metadata.name}</span>
                  <small>revision {project.revision}</small>
                </button>
              ))}
              {projects.length === 0 ? <p>No saved projects yet.</p> : null}
            </div>
          ) : null}
        </div>
      )}
      <nav className="sw-stages" aria-label="Application stages">
        {STAGES.map(([key, label], index) => {
          const Icon = STAGE_ICON[key]
          const info = studio?.stages[key]
          const status = info?.status ?? 'not_started'
          return (
            <button
              type="button"
              key={key}
              className="sw-stage"
              data-status={status}
              aria-current={stage === key ? 'page' : undefined}
              onClick={() => onStage(key)}
              disabled={
                !studio
                  ? key !== 'brief'
                  : !!studio.flow &&
                    key !== studio.flow.active &&
                    !studio.flow.reviewed.includes(key)
              }
              title={collapsed ? `${label}: ${STATUS_LABEL[status]}` : info?.reason}
            >
              <span className="sw-stage__icon">
                <Icon size={16} aria-hidden="true" />
                <i aria-hidden="true" />
              </span>
              {collapsed ? (
                <span className="sw-sr">
                  {label}, {STATUS_LABEL[status]}
                </span>
              ) : (
                <span className="sw-stage__text">
                  <strong>
                    {index + 1}. {label}
                  </strong>
                  <small>{STATUS_LABEL[status]}</small>
                </span>
              )}
            </button>
          )
        })}
      </nav>
      {collapsed ? null : (
        <div className="sw-left__foot">
          <div className="sw-progress">
            <span>
              {done} of {STAGES.length} stages complete
            </span>
            <Meter done={done} total={STAGES.length} label="Stages complete" />
            <small>Review each draft to unlock the next stage.</small>
          </div>
        </div>
      )}
    </aside>
  )
}
