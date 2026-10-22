import { ArrowRight, Check, CircleDot, Layers3, Play, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DashboardProject } from '../../../api/studioProjects'

const STEPS = [
  'Requirements',
  'Domain knowledge',
  'Business process',
  'Data model',
  'Screens & UI',
  'Rules & logic',
  'Roles & access',
  'Validation',
  'Generate app',
]
const KEYS = [
  'brief',
  'knowledge',
  'workflow',
  'data',
  'screen',
  'rules',
  'roles',
  'checks',
  'export',
]

export function ProjectSpotlight({ project }: { project: DashboardProject }) {
  const current = KEYS.indexOf(project.stage)
  return (
    <section className="sd-spotlight" aria-label="Continue your latest project">
      <div className="sd-spotlight-copy">
        <span className="sd-spotlight-kicker">
          <span className="sd-live-dot" />
          PICK UP WHERE YOU LEFT OFF
        </span>
        <h2>Continue your latest project</h2>
        <p className="sd-spotlight-name">{project.name}</p>
        <p className="sd-spotlight-description">
          {project.description ||
            'Your business process, data, and experience — coming together in one application.'}
        </p>
        <Link className="sd-primary" to={`/design-studio/${project.id}?stage=${project.stage}`}>
          Continue designing <ArrowRight size={16} />
        </Link>
        <span className="sd-spotlight-revision">Revision {project.revision} · Changes saved</span>
      </div>
      <div className="sd-journey">
        <header>
          <span>
            <Workflow size={17} />
            YOUR APPLICATION JOURNEY
          </span>
          <strong>
            {project.reviewed}
            <small> / {project.stage_count - 1} reviewed</small>
          </strong>
        </header>
        <ol aria-label="Design stages">
          {STEPS.map((label, index) => (
            <li
              title={label}
              key={label}
              className={
                index < project.reviewed ? 'is-done' : index === current ? 'is-current' : ''
              }
            >
              <span>
                {index < project.reviewed ? (
                  <Check size={12} strokeWidth={3} />
                ) : index === current ? (
                  <CircleDot size={14} />
                ) : (
                  index + 1
                )}
              </span>
              <small>{label}</small>
            </li>
          ))}
        </ol>
        <div className="sd-next-step">
          <span className="sd-next-icon">
            <Layers3 size={21} />
          </span>
          <div>
            <small>CURRENT STAGE</small>
            <strong>{project.stage_label}</strong>
          </div>
          <span className="sd-stage-pill">
            <Play size={10} fill="currentColor" />
            In progress
          </span>
        </div>
        <p className="sd-journey-note">
          Reviewed stages are marked. The current stage is highlighted.
        </p>
      </div>
    </section>
  )
}
