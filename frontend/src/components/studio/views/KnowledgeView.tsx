import { ArrowRight, BookOpen } from 'lucide-react'
import { useState } from 'react'
import { Empty, StatusChip } from '../bits'
import { DecisionList } from '../DecisionList'
import type { ViewProps } from './types'

const COUNT_LABEL: Record<string, string> = {
  requirements: 'requirements',
  roles: 'roles',
  entities: 'data entities',
  rules: 'rules',
  exceptions: 'exceptions',
  decisions: 'decisions',
  workflows: 'processes',
}

/** The domain the assistant recognised, the reference knowledge behind it, the concepts it brought in and the decisions only the business can make. */
export function KnowledgeView({ studio, recent, act, busy }: ViewProps) {
  const { definition, domain } = studio
  const [search, setSearch] = useState('')
  const processes = (domain.process_library ?? []).filter((item) =>
    `${item.name} ${item.family_id ?? ''} ${item.variant ?? ''} ${item.region ?? ''} ${item.source_system ?? ''} ${item.company ?? ''} ${item.domain_id ?? ''} ${item.pack_id}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )
  const business = definition.business
  const match =
    domain.matches.find((item) => item.domain_id === business.brief.domain_id) ?? domain.matches[0]
  const domainInfo = domain.domains.find(
    (item) => item.id === (business.brief.domain_id ?? match?.domain_id),
  )
  const adopted = new Map(business.knowledge.map((link) => [link.pack_id, link.pack_version]))
  const proposed = !!studio.flow && !business.knowledge.length && !!business.entities.length
  const fromPacks = proposed
    ? business.entities
    : business.entities.filter((entity) => entity.origin)
  const byName = new Map(business.entities.map((entity) => [entity.id, entity.name]))
  const relations = fromPacks.flatMap((entity) =>
    entity.relationships.map((relation) => ({
      id: `${entity.id}:${relation.id}`,
      from: entity.name,
      to: byName.get(relation.target) ?? relation.target,
      label: relation.name,
      cardinality: relation.cardinality.replaceAll('_', ' '),
    })),
  )
  const decisions = business.decisions.filter((item) => item.status === 'open')

  if (!domainInfo && !domain.packs.length && !fromPacks.length && !decisions.length) {
    // open decisions are shown even without a domain
    return (
      <Empty icon={<BookOpen size={28} />} title="The domain is not identified yet">
        As soon as you describe the business, I will recognise its domain and bring in the reference
        knowledge that fits.
      </Empty>
    )
  }
  return (
    <div className="sw-view">
      <section className="sw-card sw-summary" aria-label="Domain">
        <p className="sw-eyebrow">Business knowledge</p>
        <p className="sw-muted">Matched to your requirements from verified reference knowledge.</p>
        <h2>
          {domainInfo?.name ?? (proposed ? 'Designed from your requirements' : 'Not identified')}
        </h2>
        {proposed ? (
          <p className="sw-muted">
            No verified reference covers this request, so these definitions come only from what you
            described. Review or ask for changes before continuing.
          </p>
        ) : null}
        {match?.matched_keywords.length ? (
          <p className="sw-muted">Recognised from: {match.matched_keywords.join(', ')}.</p>
        ) : null}
      </section>

      <section className="sw-card" aria-label="Reference knowledge">
        <h3>Reference knowledge</h3>
        {domain.packs.length === 0 ? (
          <p className="sw-muted">
            No verified reference covers this domain yet. The foundation is designed only from what
            you described.
          </p>
        ) : (
          <ul className="sw-rows">
            {domain.packs.map((pack) => (
              <li key={pack.id}>
                <div>
                  <p>
                    <strong>{pack.title}</strong>{' '}
                    <small>
                      version {adopted.get(pack.id) ?? pack.version}
                      {pack.usage === 'source_reference'
                        ? ' · Source reference only'
                        : ' · Reusable blueprint'}
                    </small>
                  </p>
                  <small>{pack.description}</small>
                  {pack.quality?.configuration_required?.map((item) => (
                    <p className="sw-muted" key={item.integration_id}>
                      <strong>Customer connection required:</strong> {item.integration_id}.{' '}
                      {item.note}
                    </p>
                  ))}
                  {adopted.has(pack.id) && adopted.get(pack.id) !== pack.version ? (
                    <p className="sw-muted">
                      Reference update available: {adopted.get(pack.id)} → {pack.version}.{' '}
                      <button
                        type="button"
                        className="sw-button"
                        disabled={busy || domain.source !== 'neo4j'}
                        onClick={() => act([{ type: 'update_knowledge', pack_id: pack.id }])}
                      >
                        Review reference update
                      </button>
                    </p>
                  ) : null}
                  <details className="sw-knowledge-details">
                    <summary>View coverage</summary>
                    <ul className="sw-tags">
                      {Object.entries(pack.counts)
                        .filter(([, count]) => count)
                        .map(([group, count]) => (
                          <li key={group}>
                            {count} {COUNT_LABEL[group] ?? group}
                          </li>
                        ))}
                    </ul>
                  </details>
                </div>
                {pack.usage === 'source_reference' ? (
                  <span className="sw-muted">
                    Source reference only - use a reusable blueprint to generate
                  </span>
                ) : adopted.has(pack.id) ? (
                  studio.flow ? (
                    <span className="sw-chip">Included in draft</span>
                  ) : (
                    <StatusChip status="completed" />
                  )
                ) : (
                  <span className="sw-chip">Reference only</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="sw-muted sw-aside">
          Included knowledge adds processes, records and rules to this project, with links to their
          sources. Editing this project does not change the shared knowledge.
        </p>
      </section>

      {domain.process_library?.length ? (
        <details className="sw-card sw-disclosure" open>
          <summary>Verified processes · {domain.process_library.length}</summary>
          <p className="sw-muted">Each process was read from the documentation cited with it.</p>
          <label className="sw-field">
            <span>Find a process or domain</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Transport, purchasing, workforce…"
            />
          </label>
          <ul className="sw-rows">
            {processes.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  {studio.definition.business.knowledge.some(
                    (link) => link.pack_id === item.pack_id,
                  ) &&
                  !studio.definition.workflow_definitions.some(
                    (workflow) => workflow.id === item.workflow_id,
                  ) ? (
                    <p className="sw-callout-inline">
                      Not in this project: it applies in {item.region}. Choose that region in
                      Requirements to add it.
                    </p>
                  ) : null}
                  <p className="sw-muted">
                    {item.company ?? 'Shared domain process'} · {item.steps} activities ·{' '}
                    {item.decisions} decisions · {item.exceptions} exception paths
                  </p>
                  <small>
                    {item.pack_id} · {item.pack_version} · {item.verification}
                  </small>
                  <details>
                    <summary>Source and verification</summary>
                    <p>{item.source}</p>
                    <p>
                      Verification: {item.verification} · Region: {item.region ?? 'Unspecified'}
                      {item.source_system ? ` · System: ${item.source_system}` : ''}
                    </p>
                  </details>
                </div>
              </li>
            ))}
          </ul>
          {!processes.length ? (
            <p>No matching process is stored in the available library.</p>
          ) : null}
        </details>
      ) : null}

      <section className="sw-card" aria-label="Unresolved decisions" hidden={!!studio.flow}>
        <h3>
          Decisions only the business can make <span className="sw-count">{decisions.length}</span>
        </h3>
        <DecisionList studio={studio} act={act} busy={busy} recent={recent} />
        <p className="sw-muted sw-aside">
          I do not decide company policy. Open decisions stop the design from being approved. A
          recorded answer is a proposal that a project or process owner applies.
        </p>
      </section>

      {fromPacks.length ? (
        <details className="sw-card sw-disclosure" aria-label="Concepts">
          <summary>
            Business concepts <span className="sw-count">{fromPacks.length}</span>
          </summary>
          <ul className="sw-tags sw-tags--wide">
            {fromPacks.map((entity) => (
              <li
                key={entity.id}
                data-changed={recent.has(entity.id) || undefined}
                title={entity.description}
              >
                {entity.name}
              </li>
            ))}
          </ul>
          {relations.length ? (
            <>
              <h4>How they depend on each other</h4>
              <ul className="sw-deps">
                {relations.slice(0, 14).map((item) => (
                  <li key={item.id}>
                    <strong>{item.from}</strong> <ArrowRight size={12} aria-hidden="true" />{' '}
                    <strong>{item.to}</strong>{' '}
                    <small>
                      {item.label} · {item.cardinality}
                    </small>
                  </li>
                ))}
              </ul>
              {relations.length > 14 ? (
                <p className="sw-muted">and {relations.length - 14} more in the data model.</p>
              ) : null}
            </>
          ) : null}
        </details>
      ) : null}

      {business.terms.length ? (
        <details className="sw-card sw-disclosure" aria-label="Glossary">
          <summary>
            Glossary <span className="sw-count">{business.terms.length}</span>
          </summary>
          <dl className="sw-terms">
            {business.terms.map((term) => (
              <div key={term.id}>
                <dt>{term.term}</dt>
                <dd>{term.definition}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </div>
  )
}
