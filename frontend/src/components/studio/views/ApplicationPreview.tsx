import { useState, type CSSProperties } from 'react'
import { ArrowRight, Database, Home, Layers, Maximize2, Minimize2 } from 'lucide-react'
import type { ApplicationDefinition } from '../../../api/applicationDefinition'
import type { Viewport } from '../canvas/ScreenCanvas'
import { BusinessScreenPreview } from './BusinessScreenPreview'
import './ApplicationPreview.css'
import { contrastInk } from '../../../lib/colorContrast'
import { entityIcon, taskIcon } from './taskIcons'

const palettes = { Emerald: '#087e67', Indigo: '#5554cf', Ocean: '#176d9c', Graphite: '#475569' }

/** A navigable prototype built from the same saved screens and process as the export. */
export function ApplicationPreview({
  definition,
  viewport,
  onThemeChange,
}: {
  definition: ApplicationDefinition
  viewport: Viewport
  onThemeChange?: (color: string) => void
}) {
  const initials = definition.metadata.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()
  const [page, setPage] = useState('home')
  const [localPalette, setLocalPalette] = useState<{ source: string; value: string } | null>(null)
  const palette =
    !onThemeChange && localPalette?.source === definition.theme.primary
      ? localPalette.value
      : definition.theme.primary
  const [expanded, setExpanded] = useState(false)
  const business = definition.business ?? { entities: [], roles: [], brief: { goal: '' } }
  const screens = definition.screens.filter((screen) => screen.trace?.generated)
  const screen = screens.find((item) => item.id === page)
  const entity = business.entities.find((item) => `record:${item.id}` === page)
  const steps = (definition.workflow_definitions ?? []).flatMap((workflow) => workflow.states)
  const visibleEntityIds = new Set(
    steps.flatMap((item) => [...(item.reads_entity_ids ?? []), ...(item.writes_entity_ids ?? [])]),
  )
  // Supporting catalogue entities can be stored as knowledge without becoming
  // unrelated menu items. Keep custom records and the task's relationship closure.
  for (const item of business.entities) if (!item.origin) visibleEntityIds.add(item.id)
  let expandedRelations = true
  while (expandedRelations) {
    expandedRelations = false
    for (const item of business.entities.filter((record) => visibleEntityIds.has(record.id))) {
      for (const relationship of item.relationships ?? []) {
        if (!visibleEntityIds.has(relationship.target)) {
          visibleEntityIds.add(relationship.target)
          expandedRelations = true
        }
      }
    }
  }
  const visibleEntities = business.entities.filter((item) => visibleEntityIds.has(item.id))
  const step = screen ? steps.find((item) => item.id === screen.trace?.step_id) : undefined
  const role = business.roles.find((item) => item.id === step?.role_id)
  const iconFor = (id: string | null | undefined) => {
    const task = steps.find((item) => item.id === id)
    return taskIcon(task?.label ?? '', task?.kind, task?.outcome)
  }
  return (
    <section
      className={`app-prototype app-prototype--${viewport}${expanded ? ' app-prototype--expanded' : ''}`}
      style={{ '--app-accent': palette, '--app-accent-ink': contrastInk(palette) } as CSSProperties}
      aria-label="Application prototype"
    >
      <div className="app-prototype__tools">
        <span>
          <i /> Application prototype · records are not saved
        </span>
        <div>
          <label>
            Theme{' '}
            <select
              value={palette}
              onChange={(event) => {
                if (onThemeChange) onThemeChange(event.target.value)
                else
                  setLocalPalette({ source: definition.theme.primary, value: event.target.value })
              }}
            >
              <option value={definition.theme.primary}>Project theme</option>
              {Object.entries(palettes).map(([name, color]) => (
                <option key={name} value={color}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? 'Exit expanded preview' : 'Expand application preview'}
          >
            {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>
      <div className="app-prototype__shell">
        <aside className="app-prototype__nav">
          <div className="app-prototype__brand">
            <Layers size={22} />
            <strong>{definition.metadata.name}</strong>
          </div>
          <nav aria-label="Application navigation">
            <button
              type="button"
              aria-current={page === 'home' ? 'page' : undefined}
              onClick={() => setPage('home')}
            >
              <Home size={16} />
              Overview
            </button>
            <small>WORKSPACE</small>
            {screens.map((item) => {
              const Icon = iconFor(item.trace?.step_id)
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-current={page === item.id ? 'page' : undefined}
                  onClick={() => setPage(item.id)}
                >
                  <Icon size={16} />
                  <span>{item.title}</span>
                </button>
              )
            })}
            <small>RECORDS</small>
            {visibleEntities.map((item) => {
              const Icon = entityIcon(item.name)
              return (
                <button
                  type="button"
                  key={item.id}
                  aria-current={page === `record:${item.id}` ? 'page' : undefined}
                  onClick={() => setPage(`record:${item.id}`)}
                >
                  <Icon size={16} />
                  <span>{item.name}</span>
                </button>
              )
            })}
          </nav>
          <footer>
            <span>{initials}</span>
            <div>
              Design preview<small>Explore every workflow</small>
            </div>
          </footer>
        </aside>
        <main className="app-prototype__main">
          <header className="app-prototype__topbar">
            <span>
              Workspace <b>/</b> {screen?.title ?? entity?.name ?? 'Overview'}
            </span>
            <span className="app-prototype__avatar">{initials}</span>
          </header>
          {screen ? (
            <BusinessScreenPreview
              screen={screen}
              definition={definition}
              step={step}
              roleName={role?.name}
              viewport={viewport}
              navigate={setPage}
            />
          ) : entity ? (
            <div className="app-prototype__page">
              <span className="app-prototype__eyebrow">RECORDS</span>
              <h2>{entity.name}</h2>
              <p>
                {entity.description || `Manage and review ${entity.name.toLowerCase()} records.`}
              </p>
              <div className="app-prototype__table">
                <table>
                  <thead>
                    <tr>
                      {entity.attributes.map((attribute) => (
                        <th key={attribute.id}>{attribute.name}</th>
                      ))}
                    </tr>
                  </thead>
                </table>
                <div className="app-prototype__empty">
                  <Database size={30} />
                  <h3>Your records will appear here</h3>
                  <p>
                    This prototype shows the saved data structure. Live records are available in the
                    generated application.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="app-prototype__page">
              <span className="app-prototype__eyebrow">WORKSPACE</span>
              <h2>Application overview</h2>
              <p>{business.brief.goal || definition.metadata.name}</p>
              <div className="app-prototype__stats">
                {[
                  [screens.length, 'Workflow screens'],
                  [visibleEntities.length, 'Record types'],
                  [business.roles.length, 'Team roles'],
                ].map(([count, label]) => (
                  <div key={label}>
                    <strong>{count}</strong>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
              <div className="app-prototype__section-title">
                <h3>Workflow tasks</h3>
                <span>Choose a task to get started</span>
              </div>
              <div className="app-prototype__cards">
                {screens.map((item) => {
                  const Icon = iconFor(item.trace?.step_id)
                  const task = steps.find((candidate) => candidate.id === item.trace?.step_id)
                  const owner = business.roles.find((candidate) => candidate.id === task?.role_id)
                  return (
                    <button type="button" key={item.id} onClick={() => setPage(item.id)}>
                      <span className="app-prototype__card-icon">
                        <Icon size={21} />
                      </span>
                      <h3>{item.title}</h3>
                      <p>
                        {owner?.name ??
                          (task?.kind === 'end' ? 'Process outcome' : 'Team workspace')}
                      </p>
                      <span className="app-prototype__open">
                        Open workspace <ArrowRight size={15} />
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </main>
      </div>
    </section>
  )
}
