import { useRef, useState } from 'react'
import {
  Database,
  Minus,
  Plus,
  Maximize2,
  Network,
  List,
  Search,
  ArrowRight,
  X,
} from 'lucide-react'
import { Empty } from '../bits'
import { ErDiagram } from '../diagrams/ErDiagram'
import type { ViewProps } from './types'
import './DataModelView.css'

const TYPES = ['string', 'integer', 'decimal', 'boolean', 'date', 'datetime'] as const

/** The data the application keeps, as an interactive entity-relationship diagram. Select an entity to see its attributes, who uses it and to change what is mandatory. */
export function DataModelView({ studio, recent, act, ask, select, selection, busy }: ViewProps) {
  const { definition } = studio
  const entities = definition.business.entities
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(0)
  const [scale, setScale] = useState(1)
  const [showAll, setShowAll] = useState(true)
  const [presentation, setPresentation] = useState<'map' | 'list'>('map')
  const [search, setSearch] = useState('')
  const canvas = useRef<HTMLDivElement>(null)
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState<(typeof TYPES)[number]>('string')
  const chosen =
    entities.find(
      (item) =>
        item.id ===
        (selectedId ??
          (selection && entities.some((entity) => entity.id === selection) ? selection : null)),
    ) ?? null
  const roles = new Map(definition.business.roles.map((role) => [role.id, role.name]))
  const steps = definition.workflow_definitions.flatMap((workflow) =>
    workflow.states.map((state) => ({ workflow, state })),
  )
  const users = chosen
    ? steps.filter(
        ({ state }) =>
          (state.reads_entity_ids ?? []).includes(chosen.id) ||
          (state.writes_entity_ids ?? []).includes(chosen.id),
      )
    : []
  const targets = new Map(entities.map((entity) => [entity.id, entity.name]))
  const relationships = entities.flatMap((entity) =>
    entity.relationships.map((relation) => ({
      ...relation,
      source: entity.id,
      sourceName: entity.name,
    })),
  )
  const connected = new Set(relationships.flatMap((relation) => [relation.source, relation.target]))
  const neighbours = chosen
    ? relationships.filter(
        (relation) => relation.source === chosen.id || relation.target === chosen.id,
      )
    : []
  const matching = search.trim()
    ? entities.filter((entity) =>
        `${entity.name} ${entity.attributes.map((a) => a.name).join(' ')}`
          .toLowerCase()
          .includes(search.trim().toLowerCase()),
      )
    : []
  const choose = (id: string | null) => {
    setSelectedId(id)
    select(id)
    setSearch('')
    if (!id) setShowAll(true)
  }
  const cardinality = {
    one_to_one: 'One to one',
    one_to_many: 'One to many',
    many_to_one: 'Many to one',
    many_to_many: 'Many to many',
  }

  if (!entities.length)
    return (
      <Empty icon={<Database size={28} />} title="No data model yet">
        The data model is prepared from the process and requirements. Ask for an entity at any time
        — for example “add a Vehicle with a registration number and capacity”.
      </Empty>
    )
  return (
    <div className="sw-view sw-data">
      <section className="sw-card sw-data__overview">
        <div>
          <p className="sw-eyebrow">Application data</p>
          <h2>Your data, connected</h2>
          <p className="sw-muted">
            Explore how records relate. Select an entity to trace its connections and inspect its
            fields.
          </p>
        </div>
        <div className="sw-data__metrics">
          <span>
            <strong>{entities.length}</strong> entities
          </span>
          <span>
            <strong>{relationships.length}</strong> relationships
          </span>
          <span>
            <strong>{entities.reduce((sum, e) => sum + e.attributes.length, 0)}</strong> fields
          </span>
        </div>
      </section>
      <div className="sw-toolbar" role="toolbar" aria-label="Diagram tools">
        <div className="sw-data__tabs" role="group" aria-label="Data model presentation">
          <button
            type="button"
            aria-pressed={presentation === 'map'}
            onClick={() => setPresentation('map')}
          >
            <Network size={15} /> Relationship map
          </button>
          <button
            type="button"
            aria-pressed={presentation === 'list'}
            onClick={() => setPresentation('list')}
          >
            <List size={15} /> Relationship list
          </button>
        </div>
        <span className="sw-toolbar__spacer" />
        {presentation === 'map' ? (
          <>
            <label className="sw-relationship-toggle">
              <input
                type="checkbox"
                disabled={!chosen}
                checked={showAll}
                onChange={(event) => setShowAll(event.target.checked)}
              />{' '}
              All relationships
            </label>
            <button
              type="button"
              className="sw-icon-button"
              onClick={() => setZoom(Math.max(0.35, scale - 0.15))}
              aria-label="Zoom out"
            >
              <Minus size={14} />
            </button>
            <span className="sw-data__zoom" aria-label="Diagram zoom">
              {Math.round(scale * 100)}%
            </span>
            <button
              type="button"
              className="sw-icon-button"
              onClick={() => setZoom(Math.min(1.8, scale + 0.15))}
              aria-label="Zoom in"
            >
              <Plus size={14} />
            </button>
            <button
              type="button"
              className="sw-button"
              onClick={() => {
                setZoom(0)
                canvas.current?.scrollTo?.({ top: 0, left: 0, behavior: 'smooth' })
              }}
            >
              <Maximize2 size={14} /> Fit width
            </button>
          </>
        ) : null}
        <button
          type="button"
          className="sw-button"
          onClick={() => ask('Add a data entity called ')}
        >
          Add entity
        </button>
      </div>
      <div className="sw-data__navigation">
        <div className="sw-data__search">
          <Search size={16} />
          <input
            aria-label="Find a data entity"
            placeholder="Find an entity or field…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {search ? (
            <div className="sw-data__results">
              {matching.length ? (
                matching.map((entity) => (
                  <button type="button" key={entity.id} onClick={() => choose(entity.id)}>
                    {entity.name}
                    <small>{entity.attributes.length} fields</small>
                  </button>
                ))
              ) : (
                <p>No matching entities.</p>
              )}
            </div>
          ) : null}
        </div>
        {chosen ? (
          <span className="sw-data__selection">
            Tracing {chosen.name} · {neighbours.length} connections{' '}
            <button type="button" aria-label="Clear entity selection" onClick={() => choose(null)}>
              <X size={13} />
            </button>
          </span>
        ) : (
          <span className="sw-muted">All saved relationships are visible</span>
        )}
      </div>
      <div className="sw-data__body">
        {presentation === 'map' ? (
          <div className="sw-data__map">
            <div className="sw-data__canvas" ref={canvas}>
              <ErDiagram
                entities={entities}
                selectedId={chosen?.id ?? null}
                zoom={zoom}
                onScale={setScale}
                showAll={showAll}
                recent={recent}
                onSelect={choose}
              />
            </div>
            <div className="sw-legend">
              <span>◆ Primary key</span>
              <span>● Required field</span>
              <span>○ Optional field</span>
              <span className="sw-legend__solid">Required relationship</span>
              <span className="sw-legend__dashed">Optional relationship</span>
            </div>
          </div>
        ) : (
          <section className="sw-card sw-data__relationships" aria-label="All entity relationships">
            <table className="sw-table">
              <thead>
                <tr>
                  <th>From entity</th>
                  <th>Relationship</th>
                  <th>To entity</th>
                  <th>Cardinality</th>
                  <th>Required</th>
                </tr>
              </thead>
              <tbody>
                {relationships.map((relation) => (
                  <tr key={`${relation.source}:${relation.id}`}>
                    <td>
                      <button
                        type="button"
                        className="sw-link-button"
                        onClick={() => choose(relation.source)}
                      >
                        {relation.sourceName}
                      </button>
                    </td>
                    <td>{relation.name}</td>
                    <td>
                      <button
                        type="button"
                        className="sw-link-button"
                        onClick={() => choose(relation.target)}
                      >
                        {targets.get(relation.target) ?? 'Missing target entity'}
                      </button>
                    </td>
                    <td>{cardinality[relation.cardinality]}</td>
                    <td>{relation.required ? 'Required' : 'Optional'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!relationships.length ? (
              <p className="sw-muted">
                No relationships are defined in this model yet. Ask the assistant to link the
                appropriate entities.
              </p>
            ) : null}
          </section>
        )}
        {entities.some((entity) => !connected.has(entity.id)) ? (
          <p className="sw-muted sw-data__unlinked">
            Standalone entities:{' '}
            {entities
              .filter((entity) => !connected.has(entity.id))
              .map((entity) => entity.name)
              .join(', ')}
            . No connections have been defined for these records.
          </p>
        ) : null}
        <aside className="sw-card sw-entity" aria-label="Entity details">
          {!chosen ? (
            <>
              <h3>Select an entity</h3>
              <p className="sw-muted">
                See its attributes, the process steps that use it and the rules that apply. You can
                also ask for a change in plain words.
              </p>
            </>
          ) : (
            <>
              <p className="sw-eyebrow">Data entity</p>
              <h3>{chosen.name}</h3>
              {chosen.description ? <p className="sw-muted">{chosen.description}</p> : null}
              <p className="sw-muted">
                {chosen.owner_role_id
                  ? `Owned by ${roles.get(chosen.owner_role_id) ?? chosen.owner_role_id}. `
                  : ''}
                {chosen.origin
                  ? `From reference knowledge ${chosen.origin.pack_id}.`
                  : 'Created in this project.'}
              </p>
              <div className="sw-entity__cols">
                <div>
                  <table className="sw-table" aria-label={`${chosen.name} attributes`}>
                    <thead>
                      <tr>
                        <th>Attribute</th>
                        <th>Type</th>
                        <th>Mandatory</th>
                      </tr>
                    </thead>
                    <tbody>
                      {chosen.attributes.map((attribute) => {
                        const system =
                          (attribute.value_source ?? 'user_entered') !== 'user_entered' ||
                          attribute.writable === false
                        return (
                          <tr
                            key={attribute.id}
                            data-changed={recent.has(`${chosen.id}.${attribute.id}`) || undefined}
                          >
                            <td>
                              {attribute.key ? '◆ ' : ''}
                              {attribute.name}
                              {system ? <small> · system-managed</small> : null}
                              {attribute.sensitivity &&
                              attribute.sensitivity !== 'internal' &&
                              attribute.sensitivity !== 'public' ? (
                                <small> · {attribute.sensitivity}</small>
                              ) : null}
                            </td>
                            <td>{attribute.type}</td>
                            <td>
                              <button
                                type="button"
                                role="switch"
                                aria-checked={!!attribute.required}
                                aria-label={`${attribute.name} is ${attribute.required ? 'mandatory' : 'optional'}`}
                                className="sw-switch"
                                disabled={busy || !!attribute.key}
                                onClick={() =>
                                  act([
                                    {
                                      type: 'set_attribute_required',
                                      entity: chosen.id,
                                      attribute: attribute.id,
                                      required: !attribute.required,
                                    },
                                  ])
                                }
                              >
                                <i />
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <form
                    className="sw-inline-form"
                    onSubmit={(event) => {
                      event.preventDefault()
                      if (newName.trim()) {
                        act([
                          {
                            type: 'add_attribute',
                            entity: chosen.id,
                            attribute: { name: newName.trim(), type: newType },
                          },
                        ])
                        setNewName('')
                      }
                    }}
                  >
                    <label className="sw-sr" htmlFor="new-attribute">
                      New attribute name
                    </label>
                    <input
                      id="new-attribute"
                      value={newName}
                      onChange={(event) => setNewName(event.target.value)}
                      placeholder="New attribute"
                      maxLength={120}
                    />
                    <select
                      aria-label="Attribute type"
                      value={newType}
                      onChange={(event) => setNewType(event.target.value as (typeof TYPES)[number])}
                    >
                      {TYPES.map((type) => (
                        <option key={type}>{type}</option>
                      ))}
                    </select>
                    <button type="submit" className="sw-button" disabled={busy || !newName.trim()}>
                      Add
                    </button>
                  </form>
                </div>
                <div>
                  <h4>Connections · {neighbours.length}</h4>
                  {neighbours.length ? (
                    <ul className="sw-data__connection-list">
                      {neighbours.map((relation) => (
                        <li key={`${relation.source}:${relation.id}`}>
                          <span>
                            {relation.name}
                            <small>
                              {cardinality[relation.cardinality]} ·{' '}
                              {relation.required ? 'Required' : 'Optional'}
                            </small>
                          </span>
                          <div>
                            <button type="button" onClick={() => choose(relation.source)}>
                              {relation.sourceName}
                            </button>
                            <ArrowRight size={13} />
                            <button type="button" onClick={() => choose(relation.target)}>
                              {targets.get(relation.target) ?? 'Missing target'}
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="sw-muted">
                      No incoming or outgoing relationships are defined for this entity.
                    </p>
                  )}
                  <h4>Used by</h4>
                  {users.length ? (
                    <ul className="sw-list">
                      {users.map(({ workflow, state }) => (
                        <li key={`${workflow.id}/${state.id}`}>
                          {state.label}{' '}
                          <small>
                            {(state.writes_entity_ids ?? []).includes(chosen.id)
                              ? 'changes'
                              : 'reads'}
                          </small>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="sw-muted">No process step uses this yet.</p>
                  )}
                  <button
                    type="button"
                    className="sw-link-button"
                    onClick={() => ask(`About the ${chosen.name} entity: `)}
                  >
                    Ask the assistant about this entity
                  </button>
                </div>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
