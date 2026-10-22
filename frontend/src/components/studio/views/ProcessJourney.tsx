import { ArrowRight, Database, ShieldCheck, UserRound } from 'lucide-react'
import type { ApplicationDefinition, WorkflowDefinition } from '../../../api/applicationDefinition'
import { taskIcon } from './taskIcons'
import { layoutProcessVertical } from '../diagrams/processLayout'
import './ProcessJourney.css'

/** All content comes from the saved process; branch routes remain visible. */
export function ProcessJourney({
  workflow,
  definition,
  onSelect,
}: {
  workflow: WorkflowDefinition
  definition: ApplicationDefinition
  onSelect: (id: string) => void
}) {
  const business = definition.business ?? {
    roles: [],
    entities: [],
    rules: [],
    exceptions: [],
    requirements: [],
    knowledge: [],
  }
  const entityName = (id: string) => business.entities.find((e) => e.id === id)?.name ?? id
  const roleName = (id?: string | null) =>
    business.roles.find((r) => r.id === id)?.name ?? 'No role assigned'
  const layout = layoutProcessVertical(workflow)
  const ordered = [...workflow.states].sort((a, b) => {
    const first = layout.nodes.get(a.id)!
    const second = layout.nodes.get(b.id)!
    return first.rank - second.rank || first.x - second.x
  })

  return (
    <section className="process-journey" aria-label="Detailed business process">
      <div className="process-journey__intro">
        <div>
          <span>PROCESS BLUEPRINT</span>
          <h3>{workflow.name}</h3>
          <p>
            Explore each activity, its owner, information, rules and next paths. Branches follow the
            conditions shown.
          </p>
        </div>
        {business.knowledge.length ? (
          <small>
            Project reference versions
            <br />
            <strong>
              {business.knowledge
                .map((link) => `${link.pack_id} · ${link.pack_version}`)
                .join(', ')}
            </strong>
          </small>
        ) : (
          <small>Project-specific process</small>
        )}
      </div>
      <div className="process-journey__activities">
        {ordered.map((step, index) => {
          const Icon = taskIcon(step.label, step.kind, step.outcome)
          const rules = business.rules.filter((rule) => step.rule_ids?.includes(rule.id))
          const exceptions = business.exceptions.filter((item) =>
            step.exception_ids?.includes(item.id),
          )
          const routes = workflow.transitions.filter((edge) => edge.source === step.id)
          const requirements = business.requirements.filter((req) =>
            step.requirement_ids?.includes(req.id),
          )
          return (
            <article className="process-journey__activity" key={step.id} data-kind={step.kind}>
              <header>
                <span className="process-journey__icon">
                  <Icon size={21} />
                </span>
                <div>
                  <small>
                    ACTIVITY {String(index + 1).padStart(2, '0')} · {step.kind}
                  </small>
                  <h3>{step.label}</h3>
                </div>
                <button type="button" className="sw-button" onClick={() => onSelect(step.id)}>
                  Inspect
                </button>
              </header>
              <div className="process-journey__facts">
                <span>
                  <UserRound size={14} />
                  {step.kind === 'start' || step.kind === 'end'
                    ? 'Process boundary'
                    : roleName(step.role_id)}
                </span>
                {step.outcome ? <span>Outcome: {step.outcome}</span> : null}
              </div>
              {step.reads_entity_ids?.length ||
              step.writes_entity_ids?.length ||
              rules.length ||
              exceptions.length ? (
                <div className="process-journey__columns">
                  {step.reads_entity_ids?.length || step.writes_entity_ids?.length ? (
                    <section>
                      {step.reads_entity_ids?.length ? (
                        <>
                          <h4>
                            <Database size={14} />
                            Information used
                          </h4>
                          <p>{step.reads_entity_ids.map(entityName).join(', ')}</p>
                        </>
                      ) : null}
                      {step.writes_entity_ids?.length ? (
                        <>
                          <h4>Information changed</h4>
                          {step.writes_entity_ids.map((id) => {
                            const entity = business.entities.find((item) => item.id === id)
                            const fields = step.input_fields?.[id]
                            return (
                              <p key={id}>
                                <strong>{entityName(id)}</strong>
                                {fields?.length ? <br /> : null}
                                {fields?.length
                                  ? fields
                                      .map(
                                        (field) =>
                                          entity?.attributes.find((a) => a.id === field)?.name ??
                                          field,
                                      )
                                      .join(', ')
                                  : null}
                                {step.input_relationships?.[id]?.length ? (
                                  <>
                                    <br />
                                    Links:{' '}
                                    {step.input_relationships[id]
                                      .map(
                                        (rel) =>
                                          entity?.relationships.find((r) => r.id === rel)?.name ??
                                          rel,
                                      )
                                      .join(', ')}
                                  </>
                                ) : null}
                              </p>
                            )
                          })}
                        </>
                      ) : null}
                    </section>
                  ) : null}
                  {rules.length || exceptions.length ? (
                    <section>
                      <h4>
                        <ShieldCheck size={14} />
                        Business rules
                      </h4>
                      {rules.map((rule) => (
                        <p key={rule.id}>{rule.description}</p>
                      ))}
                      {exceptions.map((item) => (
                        <p key={item.id}>
                          <strong>{item.name}</strong>
                          <br />
                          {item.trigger}
                          {item.recovery ? (
                            <>
                              <br />
                              Recovery: {item.recovery}
                            </>
                          ) : null}
                        </p>
                      ))}
                    </section>
                  ) : null}
                </div>
              ) : null}
              {step.preconditions?.length || step.postconditions?.length ? (
                <details>
                  <summary>Entry and completion conditions</summary>
                  {step.preconditions?.map((text) => (
                    <p key={text}>Before: {text}</p>
                  ))}
                  {step.postconditions?.map((text) => (
                    <p key={text}>After: {text}</p>
                  ))}
                </details>
              ) : null}
              {requirements.length ? (
                <details>
                  <summary>{requirements.length} linked requirements</summary>
                  {requirements.map((item) => (
                    <p key={item.id}>{item.statement}</p>
                  ))}
                </details>
              ) : null}
              <footer>
                {routes.length ? (
                  routes.map((edge) => {
                    const target = workflow.states.find((item) => item.id === edge.target)
                    const rule = business.rules.find((item) => item.id === edge.condition.field)
                    return (
                      <button type="button" key={edge.id} onClick={() => onSelect(edge.target)}>
                        <span>
                          {edge.condition.kind === 'always'
                            ? 'Next'
                            : `${rule?.description ?? edge.condition.field} ${edge.condition.kind === 'not_equals' ? '≠' : '='} ${String(edge.condition.value)}`}
                        </span>
                        <strong>
                          {target?.label ?? edge.target}
                          <ArrowRight size={14} />
                        </strong>
                      </button>
                    )
                  })
                ) : (
                  <p>
                    {step.kind === 'end'
                      ? 'This process path ends here.'
                      : 'No onward path defined.'}
                  </p>
                )}
              </footer>
            </article>
          )
        })}
      </div>
    </section>
  )
}
