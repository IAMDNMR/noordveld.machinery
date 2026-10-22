import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  comparePack,
  exportPackUrl,
  getDomains,
  getEntities,
  getEntity,
  getGraph,
  getGraphStatus,
  getImpact,
  getPacks,
  getPath,
  importApply,
  importDryRun,
  searchConcepts,
  transitionVersion,
  type Change,
  type DomainSummary,
  type DryRun,
  type EntityDetail,
  type EntitySummary,
  type GraphStatus,
  type GraphView,
  type Hop,
  type Impact,
  type ImportRequest,
  type SearchHit,
  type VersionMeta,
  type Analysis,
  type Decision,
  type PackRef,
  type ProposalImpact,
  type Traversal,
  getDomainPermissions,
  getProposalImpact,
  traverse,
} from '../api/domainKnowledge'
import { ProvenanceBadge } from '../components/knowledge/ProvenanceBadge'
import { useSession } from '../store/session'
import './DomainKnowledgePage.css'

type Tab = 'explore' | 'search' | 'governance' | 'graph'
const TABS: [Tab, string][] = [
  ['explore', 'Domains and entities'],
  ['search', 'Search and paths'],
  ['governance', 'Import and versions'],
  ['graph', 'Graph storage'],
]
const errorText = (cause: unknown, fallback: string) =>
  cause instanceof ApiError ? cause.message : fallback

/** Neighbourhood of one entity on a circle. The relationship tables beside it carry the same information accessibly. */
export function Neighbourhood({
  graph,
  focus,
  onSelect,
}: {
  graph: GraphView
  focus: string
  onSelect: (id: string) => void
}) {
  const edges = graph.edges.filter((edge) => edge.source === focus || edge.target === focus)
  const linked = new Set(edges.flatMap((edge) => [edge.source, edge.target]))
  const others = graph.nodes.filter((node) => node.id !== focus && linked.has(node.id))
  const size = 560,
    centre = size / 2,
    radius = 220
  const place = new Map<string, [number, number]>([[focus, [centre, centre]]])
  others.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(1, others.length) - Math.PI / 2
    place.set(node.id, [centre + radius * Math.cos(angle), centre + radius * Math.sin(angle)])
  })
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="dk-graph"
      role="img"
      aria-label={`Relationships around ${focus}: ${edges.length} relationships, ${others.length} related entities`}
    >
      {edges.map((edge) => {
        const [x1, y1] = place.get(edge.source) ?? [0, 0],
          [x2, y2] = place.get(edge.target) ?? [0, 0]
        return (
          <g key={edge.id} className={`dk-graph__edge dk-graph__edge--${edge.provenance}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} />
            <title>{`${edge.source} ${edge.type} ${edge.target} (${edge.cardinality}, ${edge.provenance})`}</title>
          </g>
        )
      })}
      {graph.nodes
        .filter((node) => place.has(node.id))
        .map((node) => {
          const [x, y] = place.get(node.id)!
          return (
            <g
              key={node.id}
              className={`dk-graph__node${node.id === focus ? ' dk-graph__node--focus' : ''}`}
              transform={`translate(${x},${y})`}
              role="button"
              tabIndex={0}
              aria-label={`Open ${node.label}`}
              onClick={() => onSelect(node.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelect(node.id)
                }
              }}
            >
              <circle r={node.id === focus ? 30 : 22} />
              <text y={node.id === focus ? 46 : 36} textAnchor="middle">
                {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
              </text>
            </g>
          )
        })}
    </svg>
  )
}

function RelationshipTable({
  caption,
  rows,
  side,
  onSelect,
}: {
  caption: string
  rows: EntityDetail['outgoing']
  side: 'source_id' | 'target_id'
  onSelect: (id: string) => void
}) {
  if (!rows.length) return <p>{caption}: none.</p>
  return (
    <table className="dk-table">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Relationship</th>
          <th scope="col">{side === 'target_id' ? 'Target' : 'Source'}</th>
          <th scope="col">Cardinality</th>
          <th scope="col">Meaning</th>
          <th scope="col">Provenance</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((rel) => (
          <tr key={rel.id}>
            <td>
              <code>{rel.type}</code>
              {rel.required ? ' (required)' : ''}
            </td>
            <td>
              <button type="button" className="dk-link" onClick={() => onSelect(rel[side])}>
                {rel[side]}
              </button>
            </td>
            <td>{rel.cardinality.replace(/_/g, ' ')}</td>
            <td>{rel.meaning}</td>
            <td>
              <ProvenanceBadge provenance={rel.provenance} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function EntityPanel({ id, onSelect }: { id: string; onSelect: (id: string) => void }) {
  const [detail, setDetail] = useState<EntityDetail | null>(null)
  const [graph, setGraph] = useState<GraphView | null>(null)
  const [impact, setImpact] = useState<Impact | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    Promise.all([getEntity(id), getGraph(id)])
      .then(([entity, view]) => {
        if (live) {
          setDetail(entity)
          setGraph(view)
        }
      })
      .catch((cause) => live && setError(errorText(cause, 'The entity could not be loaded.')))
    return () => {
      live = false
    }
  }, [id])
  if (error)
    return (
      <div className="pixels-error" role="alert">
        {error}
      </div>
    )
  if (!detail || !graph) return <p role="status">Loading {id}…</p>
  const { entity, concept } = detail
  return (
    <article className="dk-entity" aria-label={`Entity ${entity.canonical_name}`}>
      <header>
        <h2>{entity.canonical_name}</h2>
        <ProvenanceBadge provenance={entity.provenance} />
        {entity.operational_label && (
          <small>
            Describes graph label <code>{entity.operational_label}</code> (read-only)
          </small>
        )}
      </header>
      <p>{entity.description}</p>
      {concept && (concept.synonyms.length > 0 || concept.acronyms.length > 0) && (
        <p>
          Also called:{' '}
          {[
            ...concept.synonyms.map((item) => `${item.term} (in ${item.domain_id})`),
            ...concept.acronyms,
          ].join(', ')}
        </p>
      )}
      <div className="dk-entity__split">
        <Neighbourhood graph={graph} focus={entity.id} onSelect={onSelect} />
        <div>
          <RelationshipTable
            caption="Outgoing relationships"
            rows={detail.outgoing}
            side="target_id"
            onSelect={onSelect}
          />
          <RelationshipTable
            caption="Incoming relationships"
            rows={detail.incoming}
            side="source_id"
            onSelect={onSelect}
          />
        </div>
      </div>
      <table className="dk-table">
        <caption>Attributes ({entity.attributes.length})</caption>
        <thead>
          <tr>
            <th scope="col">Attribute</th>
            <th scope="col">Type</th>
            <th scope="col">Required</th>
            <th scope="col">Value source</th>
            <th scope="col">Sensitivity</th>
          </tr>
        </thead>
        <tbody>
          {entity.attributes.map((attr) => (
            <tr key={attr.id}>
              <td>
                <code>{attr.id}</code>
                {attr.key ? ' (key)' : ''}
              </td>
              <td>
                {attr.type}
                {attr.provenance?.verification === 'needs_review'
                  ? ' · inferred, needs review'
                  : ''}
              </td>
              <td>{attr.required ? 'Yes' : 'No'}</td>
              <td>
                {attr.value_source.replace(/_/g, ' ')}, {attr.mutability.replace(/_/g, ' ')}
              </td>
              <td>{attr.sensitivity}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail.processes.length > 0 && (
        <section>
          <h3>Processes that use it</h3>
          <ul>
            {detail.processes.map((item) => (
              <li key={item.id}>
                {item.name} <small>template {item.design_template}</small>
              </li>
            ))}
          </ul>
        </section>
      )}
      {detail.rules.length > 0 && (
        <section>
          <h3>Rules</h3>
          <ul>
            {detail.rules.map((rule) => (
              <li key={rule.id}>
                {rule.description} <ProvenanceBadge provenance={rule.provenance} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {detail.mappings.length > 0 && (
        <section>
          <h3>Source-system mappings</h3>
          <ul>
            {detail.mappings.map((item) => (
              <li key={item.id}>
                {item.source_system}: {item.source_entity}.{item.source_attribute} →{' '}
                <code>{item.attribute_id}</code> ({item.transform.replace(/_/g, ' ')})
              </li>
            ))}
          </ul>
        </section>
      )}
      {detail.decisions.length > 0 && (
        <section>
          <h3>Open business decisions</h3>
          <ul>
            {detail.decisions.map((item) => (
              <li key={item.id}>{item.question}</li>
            ))}
          </ul>
        </section>
      )}
      <button
        type="button"
        onClick={() =>
          void getImpact(entity.id)
            .then(setImpact)
            .catch((cause) => setError(errorText(cause, 'Impact analysis failed.')))
        }
      >
        Analyse impact of a change
      </button>
      {impact && (
        <section aria-label="Impact analysis">
          <h3>Impact of changing {impact.item.name}</h3>
          <p>
            {impact.dependents.length} item(s) in the pack depend on it:{' '}
            {impact.dependents
              .slice(0, 12)
              .map((item) => item.id)
              .join(', ')}
            {impact.dependents.length > 12 ? '…' : ''}
          </p>
          {impact.project_storage !== 'available' ? (
            <p>Project storage is not configured here, so your projects could not be checked.</p>
          ) : impact.projects.length === 0 ? (
            <p>None of your projects use it.</p>
          ) : (
            <ul>
              {impact.projects.map((item) => (
                <li key={item.project_id}>
                  Project {item.project_id} r{item.revision}: entities {item.entities.join(', ')};
                  steps {item.steps.join(', ') || 'none'}; screens{' '}
                  {item.screens.join(', ') || 'none'}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </article>
  )
}

function Explore({
  domains,
  decisions,
  analysis,
  pack,
}: {
  domains: DomainSummary[]
  decisions: Decision[]
  analysis: Analysis
  pack: PackRef
}) {
  const [domain, setDomain] = useState<string>('')
  const [entities, setEntities] = useState<EntitySummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  useEffect(() => {
    void getEntities(domain || undefined)
      .then(setEntities)
      .catch(() => setEntities([]))
  }, [domain])
  const current = domains.find((item) => item.id === domain)
  return (
    <div className="dk-explore">
      <aside aria-label="Domain registry">
        <h2>Domains</h2>
        <p className="dk-muted">
          {pack.id} {pack.version}
          {pack.synthetic ? ' · mostly synthetic demo data' : ''}. Provenance:{' '}
          {Object.entries(analysis.provenance)
            .map(([kind, count]) => `${count} ${kind.replace(/_/g, ' ')}`)
            .join(', ')}
          .
        </p>
        <ul className="dk-list">
          <li>
            <button type="button" aria-pressed={domain === ''} onClick={() => setDomain('')}>
              All domains
            </button>
          </li>
          {domains.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={domain === item.id}
                onClick={() => setDomain(item.id)}
              >
                {item.name} <small>{item.entity_count}</small>
              </button>
            </li>
          ))}
        </ul>
        <details>
          <summary>
            Open business decisions ({decisions.filter((item) => item.status === 'open').length})
          </summary>
          <ul>
            {decisions.map((item) => (
              <li key={item.id}>{item.question}</li>
            ))}
          </ul>
        </details>
        <details>
          <summary>Validation ({analysis.counts.warning ?? 0} warnings)</summary>
          <ul>
            {analysis.findings.map((item) => (
              <li key={item.id} className={`dk-finding dk-finding--${item.severity}`}>
                {item.message}
              </li>
            ))}
          </ul>
        </details>
      </aside>
      <section aria-label="Entities">
        {current && (
          <p>
            <strong>{current.name}.</strong> {current.description}
            {current.depends_on.length ? ` Depends on: ${current.depends_on.join(', ')}.` : ''}
          </p>
        )}
        <ul className="dk-chips">
          {entities.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={selected === item.id}
                onClick={() => setSelected(item.id)}
              >
                {item.canonical_name}
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <EntityPanel key={selected} id={selected} onSelect={setSelected} />
        ) : (
          <p className="dk-muted">
            Choose an entity to see its attributes, relationships, rules, processes and source
            mappings.
          </p>
        )}
      </section>
    </div>
  )
}

const KINDS: [string, string][] = [
  ['entity', 'Entities'],
  ['attribute', 'Attributes'],
  ['process', 'Processes'],
  ['rule', 'Rules'],
  ['role', 'Roles'],
  ['decision', 'Decisions'],
  ['event', 'Events'],
  ['mapping', 'Source mappings'],
  ['domain', 'Domains'],
  ['concept', 'Concepts'],
]

/** Bounded, explained multi-hop queries: every result shows the path that reaches it. */
function MultiHop() {
  const [query, setQuery] = useState({
    start: 'order',
    direction: 'in' as 'in' | 'out' | 'both',
    kinds: 'process',
    depth: 2,
  })
  const [result, setResult] = useState<Traversal | null>(null)
  const [error, setError] = useState<string | null>(null)
  return (
    <section aria-label="Multi-hop query" className="dk-multihop">
      <h2>What depends on what?</h2>
      <p className="dk-muted">
        Follow relationships, processes, rules and roles up to six hops. Results are capped and each
        node is reached once by its shortest path.
      </p>
      <form
        className="dk-row"
        onSubmit={(event) => {
          event.preventDefault()
          setError(null)
          void traverse({ ...query, limit: 50 })
            .then(setResult)
            .catch((cause) => setError(errorText(cause, 'The query failed.')))
        }}
      >
        <label className="pixels-control">
          Start item
          <input
            value={query.start}
            onChange={(event) => setQuery({ ...query, start: event.target.value })}
          />
        </label>
        <label className="pixels-control">
          Direction
          <select
            value={query.direction}
            onChange={(event) =>
              setQuery({ ...query, direction: event.target.value as 'in' | 'out' | 'both' })
            }
          >
            <option value="out">What it reaches</option>
            <option value="in">What reaches it</option>
            <option value="both">Both</option>
          </select>
        </label>
        <label className="pixels-control">
          Show
          <select
            value={query.kinds}
            onChange={(event) => setQuery({ ...query, kinds: event.target.value })}
          >
            <option value="">Everything</option>
            {KINDS.map(([kind, label]) => (
              <option key={kind} value={kind}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="pixels-control">
          Max hops
          <input
            type="number"
            min={1}
            max={6}
            value={query.depth}
            onChange={(event) => setQuery({ ...query, depth: Number(event.target.value) })}
          />
        </label>
        <button type="submit" disabled={!query.start.trim()}>
          Run query
        </button>
      </form>
      {error && (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      )}
      {result &&
        (result.results.length === 0 ? (
          <p role="status">Nothing found within {result.max_depth} hop(s).</p>
        ) : (
          <table className="dk-table">
            <caption>
              {result.results.length} result(s) from {result.start.label}
              {result.truncated ? ` · limited to ${result.max_results}` : ''} ·{' '}
              {result.nodes_expanded} item(s) examined
            </caption>
            <thead>
              <tr>
                <th scope="col">Result</th>
                <th scope="col">Kind</th>
                <th scope="col">Hops</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((item) => (
                <tr key={item.node.id}>
                  <td>{item.node.label}</td>
                  <td>{item.node.kind}</td>
                  <td>{item.depth}</td>
                  <td>
                    <ol className="dk-hops">
                      {item.hops.map((hop, index) => (
                        <li key={index}>{hop.explanation}</li>
                      ))}
                    </ol>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  )
}

function Search() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [ends, setEnds] = useState({ source: 'order_line', target: 'machine' })
  const [path, setPath] = useState<{ hops: Hop[]; connected: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="dk-search">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          setError(null)
          void searchConcepts(query)
            .then(setHits)
            .catch((cause) => setError(errorText(cause, 'Search failed.')))
        }}
      >
        <label className="pixels-control">
          Search concepts, synonyms and acronyms
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. spare part, depot, WO"
          />
        </label>
        <button type="submit" disabled={!query.trim()}>
          Search
        </button>
      </form>
      {hits &&
        (hits.length === 0 ? (
          <p role="status">No concept matches “{query}”.</p>
        ) : (
          <table className="dk-table">
            <caption>{hits.length} match(es)</caption>
            <thead>
              <tr>
                <th scope="col">Concept</th>
                <th scope="col">Domain</th>
                <th scope="col">Matched on</th>
                <th scope="col">Provenance</th>
              </tr>
            </thead>
            <tbody>
              {hits.map((hit) => (
                <tr key={hit.concept_id}>
                  <td>
                    {hit.canonical_name}
                    {hit.entity_id ? <small> · entity {hit.entity_id}</small> : null}
                  </td>
                  <td>{hit.domain_id}</td>
                  <td>{hit.matched.join(', ')}</td>
                  <td>
                    <ProvenanceBadge provenance={hit.provenance} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          setError(null)
          void getPath(ends.source.trim(), ends.target.trim())
            .then(setPath)
            .catch((cause) => setError(errorText(cause, 'Path search failed.')))
        }}
      >
        <h2>How are two entities related?</h2>
        <label className="pixels-control">
          From entity
          <input
            value={ends.source}
            onChange={(event) => setEnds({ ...ends, source: event.target.value })}
          />
        </label>
        <label className="pixels-control">
          To entity
          <input
            value={ends.target}
            onChange={(event) => setEnds({ ...ends, target: event.target.value })}
          />
        </label>
        <button type="submit">Find path</button>
      </form>
      <MultiHop />
      {path &&
        (path.connected ? (
          <ol aria-label="Relationship path">
            {path.hops.map((hop) => (
              <li key={hop.relationship_id}>
                {hop.forward
                  ? `${hop.from} —${hop.type}→ ${hop.to}`
                  : `${hop.from} ←${hop.type}— ${hop.to}`}
              </li>
            ))}
          </ol>
        ) : (
          <p role="status">No path within six relationships.</p>
        ))}
      {error && (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}

function Governance({ userId }: { userId: string }) {
  const [packs, setPacks] = useState<{
    versions: VersionMeta[]
    active: PackRef[]
    writable: boolean
  } | null>(null)
  const [request, setRequest] = useState<ImportRequest>({ format: 'json', content: '' })
  const [dry, setDry] = useState<DryRun | null>(null)
  const [reason, setReason] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [diff, setDiff] = useState<{
    changes: Change[]
    compatibility: { message: string }
  } | null>(null)
  const [impact, setImpact] = useState<ProposalImpact | null>(null)
  const [may, setMay] = useState<string[]>([])
  const reload = () =>
    void getPacks()
      .then(setPacks)
      .catch((cause) => setError(errorText(cause, 'Versions could not be loaded.')))
  useEffect(reload, [])
  useEffect(() => {
    void getDomainPermissions()
      .then((result) => setMay(result.permissions))
      .catch(() => setMay([]))
  }, [])
  const can = (permission: string) => may.includes(permission)
  const act = async (work: () => Promise<unknown>, done: string) => {
    setError(null)
    setStatus(null)
    try {
      await work()
      setStatus(done)
      reload()
    } catch (cause) {
      setError(errorText(cause, 'The change failed. Nothing was changed.'))
    }
  }
  const edit = (next: Partial<ImportRequest>) => {
    setRequest({ ...request, ...next })
    setDry(null)
  }
  return (
    <div className="dk-governance">
      <section aria-label="Versions">
        <h2>Versions</h2>
        {packs && !packs.writable && (
          <p className="biz-warn">
            Read-only here: no approved store is configured for domain knowledge changes, so imports
            can be checked but not saved.
          </p>
        )}
        <p className="dk-muted">
          Your domain permissions (checked by the server):{' '}
          {may.length ? may.map((item) => item.replace('domain.', '')).join(', ') : 'none'}.
        </p>
        <table className="dk-table">
          <thead>
            <tr>
              <th scope="col">Pack</th>
              <th scope="col">Version</th>
              <th scope="col">Status</th>
              <th scope="col">Proposed by</th>
              <th scope="col">Reason</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {packs?.versions.map((item) => (
              <tr key={`${item.pack_id}-${item.version}`}>
                <td>{item.pack_id}</td>
                <td>
                  {item.version}
                  {packs.active.some((a) => a.id === item.pack_id && a.version === item.version)
                    ? ' (active)'
                    : ''}
                </td>
                <td>{item.status.replace('_', ' ')}</td>
                <td>{item.proposed_by}</td>
                <td>{item.reason}</td>
                <td className="dk-actions">
                  <a href={exportPackUrl(item.pack_id, item.version)}>Export</a>
                  {item.status !== 'approved' && (
                    <button
                      type="button"
                      onClick={() =>
                        void getProposalImpact(item.pack_id, item.version)
                          .then(setImpact)
                          .catch((cause) => setError(errorText(cause, 'Impact analysis failed.')))
                      }
                    >
                      Impact
                    </button>
                  )}
                  {item.status === 'under_review' && packs.writable && (
                    <button
                      type="button"
                      disabled={item.proposed_by === userId || !can('domain.approve')}
                      title={
                        item.proposed_by === userId
                          ? 'Another person must approve your proposal'
                          : !can('domain.approve')
                            ? 'You do not hold domain.approve'
                            : undefined
                      }
                      onClick={() =>
                        void act(
                          () =>
                            transitionVersion(
                              item.pack_id,
                              item.version,
                              'approved',
                              'Reviewed in the domain explorer',
                            ),
                          `${item.version} approved and now active.`,
                        )
                      }
                    >
                      Approve
                    </button>
                  )}
                  {item.status === 'under_review' && packs.writable && (
                    <button
                      type="button"
                      disabled={!can('domain.review')}
                      onClick={() =>
                        void act(
                          () =>
                            transitionVersion(
                              item.pack_id,
                              item.version,
                              'draft',
                              'Returned for changes',
                            ),
                          `${item.version} returned to draft.`,
                        )
                      }
                    >
                      Return to draft
                    </button>
                  )}
                  {item.status === 'approved' && packs.writable && (
                    <button
                      type="button"
                      disabled={!can('domain.administer')}
                      onClick={() =>
                        void act(
                          () =>
                            transitionVersion(
                              item.pack_id,
                              item.version,
                              'deprecated',
                              'Deprecated in the domain explorer',
                            ),
                          `${item.version} deprecated.`,
                        )
                      }
                    >
                      Deprecate
                    </button>
                  )}
                  {packs.active.find(
                    (a) => a.id === item.pack_id && a.version !== item.version,
                  ) && (
                    <button
                      type="button"
                      onClick={() =>
                        void comparePack(
                          item.pack_id,
                          packs.active.find((a) => a.id === item.pack_id)!.version,
                          item.version,
                        )
                          .then(setDiff)
                          .catch((cause) => setError(errorText(cause, 'Comparison failed.')))
                      }
                    >
                      Compare with active
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {impact && (
          <section aria-label="Proposal impact">
            <h3>
              Impact of {impact.pack_id} {impact.version}
            </h3>
            <p>
              {impact.compatibility.message}. {impact.changes.length} change(s) relative to{' '}
              {impact.base_version ?? 'nothing'}.
            </p>
            {impact.project_storage !== 'available' ? (
              <p>Project storage is not configured here, so your projects could not be checked.</p>
            ) : impact.projects.length === 0 ? (
              <p>None of your projects use the changed items.</p>
            ) : (
              <ul>
                {impact.projects.map((item) => (
                  <li key={item.project_id}>
                    {item.project_id} r{item.revision}: {item.entities.join(', ')} (adopted{' '}
                    {item.adopted_versions.join(', ')}) · not applied
                  </li>
                ))}
              </ul>
            )}
            <p className="dk-muted">{impact.note}</p>
          </section>
        )}
        {diff && (
          <section aria-label="Version comparison">
            <p>
              {diff.compatibility.message}. {diff.changes.length} change(s).
            </p>
            <ul>
              {diff.changes.slice(0, 50).map((item) => (
                <li key={`${item.group}/${item.item_id}`}>
                  {item.change} {item.group}/{item.item_id}
                  {item.fields ? ` (${item.fields.join(', ')})` : ''}
                </li>
              ))}
            </ul>
          </section>
        )}
      </section>
      <section aria-label="Import">
        <h2>Import a domain pack</h2>
        <p className="dk-muted">
          Every import is checked first. Saving creates a version under review; it becomes active
          only when another person approves it. Existing projects are not changed.
        </p>
        <div className="dk-row">
          <label className="pixels-control">
            Format
            <select
              value={request.format}
              onChange={(event) => edit({ format: event.target.value as ImportRequest['format'] })}
            >
              <option value="json">Whole pack (JSON)</option>
              <option value="csv">CSV rows</option>
            </select>
          </label>
          {request.format === 'csv' && (
            <>
              <label className="pixels-control">
                Rows describe
                <select
                  value={request.csv_kind ?? ''}
                  onChange={(event) =>
                    edit({
                      csv_kind: (event.target.value || undefined) as ImportRequest['csv_kind'],
                    })
                  }
                >
                  <option value="">Choose…</option>
                  <option value="concepts">Concepts</option>
                  <option value="relationships">Relationships</option>
                </select>
              </label>
              <label className="pixels-control">
                Pack
                <input
                  value={request.pack_id ?? ''}
                  onChange={(event) => edit({ pack_id: event.target.value })}
                />
              </label>
              <label className="pixels-control">
                Base version
                <input
                  value={request.base_version ?? ''}
                  onChange={(event) => edit({ base_version: event.target.value })}
                />
              </label>
              <label className="pixels-control">
                New version
                <input
                  value={request.new_version ?? ''}
                  onChange={(event) => edit({ new_version: event.target.value })}
                />
              </label>
            </>
          )}
        </div>
        <label className="pixels-control">
          Content
          <textarea
            rows={8}
            value={request.content}
            onChange={(event) => edit({ content: event.target.value })}
          />
        </label>
        <button
          type="button"
          disabled={request.content.trim().length < 2}
          onClick={() => {
            setError(null)
            void importDryRun(request)
              .then(setDry)
              .catch((cause) => setError(errorText(cause, 'The dry run failed.')))
          }}
        >
          Check import (dry run)
        </button>
        {dry && (
          <section aria-label="Dry-run report" className="dk-report">
            <p role="status">
              <strong>{dry.valid ? 'Valid' : 'Not valid'}</strong>
              {dry.pack_id ? ` · ${dry.pack_id} ${dry.version}` : ''}
              {dry.already_present ? ' · identical to a stored version (nothing to import)' : ''}
            </p>
            {dry.errors.length > 0 && (
              <ul>
                {dry.errors.slice(0, 30).map((item, index) => (
                  <li key={index} className="dk-finding dk-finding--error">
                    {item.location}: {item.message}
                  </li>
                ))}
              </ul>
            )}
            {dry.compatibility && <p>{dry.compatibility.message}</p>}
            {dry.summary && (
              <p>
                {dry.summary.added} added, {dry.summary.changed} changed, {dry.summary.removed}{' '}
                removed since {dry.base_version ?? 'nothing'}.
              </p>
            )}
            {dry.normalizations.length > 0 && (
              <details>
                <summary>{dry.normalizations.length} value(s) normalized</summary>
                <ul>
                  {dry.normalizations.map((item, index) => (
                    <li key={index}>
                      row {item.row} {item.column}: “{item.original}” → “{item.normalized}”
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {dry.analysis && (
              <details>
                <summary>{dry.analysis.counts.warning ?? 0} warning(s) to review</summary>
                <ul>
                  {dry.analysis.findings.map((item) => (
                    <li key={item.id}>{item.message}</li>
                  ))}
                </ul>
              </details>
            )}
            {dry.valid && !dry.already_present && (
              <div className="dk-row">
                <label className="pixels-control">
                  Reason for the change
                  <input value={reason} onChange={(event) => setReason(event.target.value)} />
                </label>
                <button
                  type="button"
                  disabled={!reason.trim() || !packs?.writable || !can('domain.propose')}
                  onClick={() =>
                    void act(async () => {
                      await importApply(request, dry.content_sha256!, reason)
                      setDry(null)
                      setReason('')
                    }, 'Proposal saved for review.')
                  }
                >
                  Propose this version for review
                </button>
              </div>
            )}
          </section>
        )}
      </section>
      {status && (
        <p className="biz-ok" role="status">
          {status}
        </p>
      )}
      {error && (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}

function GraphStorage() {
  const [status, setStatus] = useState<GraphStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    void getGraphStatus()
      .then(setStatus)
      .catch((cause) => setError(errorText(cause, 'Status unavailable.')))
  }, [])
  if (error)
    return (
      <div className="pixels-error" role="alert">
        {error}
      </div>
    )
  if (!status) return <p role="status">Loading…</p>
  return (
    <section className="dk-graphstatus" aria-label="Graph storage status">
      <p>
        <strong>
          Neo4j provider: {status.mode}. Writes enabled: {status.writes_enabled ? 'yes' : 'no'}.
        </strong>{' '}
        {status.note}
      </p>
      {status.isolation && (
        <p
          role={status.isolation.blocker ? 'alert' : 'status'}
          className={status.isolation.blocker ? 'biz-warn' : 'biz-ok'}
        >
          {status.isolation.blocker ??
            'A dedicated domain graph is configured. This build still performs no graph writes.'}
        </p>
      )}
      <p>
        Name collisions with the operational graph:{' '}
        {status.collisions_with_operational_graph.length
          ? status.collisions_with_operational_graph.join(', ')
          : 'none'}
        .
      </p>
      <p>
        Prepared import (dry run, not executed): {status.write_plan.statements} idempotent
        statements, {status.write_plan.rows} rows.
      </p>
      <details>
        <summary>Proposed namespace</summary>
        <p>Labels: {status.namespace.labels.join(', ')}</p>
        <p>Relationship types: {status.namespace.relationship_types.join(', ')}</p>
      </details>
      <details>
        <summary>Proposed constraints and indexes (awaiting authorization)</summary>
        <pre>{status.schema_proposal.join(';\n')}</pre>
      </details>
      <details>
        <summary>Parameterized read queries</summary>
        <ul>
          {status.read_queries.map((item) => (
            <li key={item}>
              <code>{item}</code>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}

export default function DomainKnowledgePage() {
  const { user, ready } = useSession()
  const [tab, setTab] = useState<Tab>('explore')
  const [data, setData] = useState<Awaited<ReturnType<typeof getDomains>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (user?.id)
      void getDomains()
        .then(setData)
        .catch((cause) => setError(errorText(cause, 'Domain knowledge is unavailable.')))
  }, [user?.id])
  if (!ready) return <p className="dk-page">Loading session…</p>
  if (!user)
    return (
      <section className="dk-page">
        <h1>Domain knowledge</h1>
        <p>Sign in to explore domain knowledge.</p>
        <Link to="/sign-in">Sign in</Link>
      </section>
    )
  return (
    <div className="dk-page">
      <header className="dk-page__head">
        <div>
          <p className="studio-page__eyebrow">NOORDVELD MACHINERY / DESIGN STUDIO</p>
          <h1>Domain knowledge</h1>
          <p>
            Shared business concepts, entities and relationships that designs reuse. Each item says
            where it comes from and whether it is verified.
          </p>
        </div>
        <Link to="/design-studio">← Back to Design Studio</Link>
      </header>
      <div role="tablist" aria-label="Domain knowledge views" className="dk-tabs">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {error && (
        <div className="pixels-error" role="alert">
          {error}
        </div>
      )}
      <div role="tabpanel">
        {tab === 'explore' &&
          (data ? (
            <Explore
              domains={data.domains}
              decisions={data.decisions}
              analysis={data.analysis}
              pack={data.pack}
            />
          ) : (
            !error && <p role="status">Loading domains…</p>
          ))}
        {tab === 'search' && <Search />}
        {tab === 'governance' && <Governance userId={user.id} />}
        {tab === 'graph' && <GraphStorage />}
      </div>
    </div>
  )
}
