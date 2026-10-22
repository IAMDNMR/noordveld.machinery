import { createElement, type CSSProperties } from 'react'
import {
  ArrowRight,
  Check,
  Database,
  Layers,
  ListChecks,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import type {
  ApplicationDefinition,
  ComponentNode,
  ScreenDefinition,
  WorkflowState,
} from '../../../api/applicationDefinition'
import { renderApplicationNode } from '../canvas/ApplicationRenderer'
import type { Viewport } from '../canvas/ScreenCanvas'
import './BusinessScreenPreview.css'
import { taskIcon } from './taskIcons'
import { taskPresentation } from './taskPresentation'

/** Older generated definitions include design documentation as screen content. Keep it accessible, outside the task UI. */
export function isDesignDocumentation(node: ComponentNode) {
  if (!node.trace?.generated) return false
  return node.kind === 'container'
    ? ['Requirements this screen satisfies', 'Business rules applied'].includes(node.props.title)
    : node.kind === 'text' && node.props.content.startsWith('Step: ') && !node.trace.entity_id
}

function BusinessNode({
  node,
  definition,
  viewport,
  navigate,
}: {
  node: ComponentNode
  definition: ApplicationDefinition
  viewport: Viewport
  navigate: (id: string) => void
}) {
  if (node.kind === 'field') {
    const required = node.props.validations.some((rule) => rule.kind === 'required')
    const help = node.props.help_text?.replace(/^Required\.$/, '')
    return (
      <label className="pixels-field">
        <span className="pixels-field__label">
          {node.props.label}
          {required ? <span className="business-preview__required"> *</span> : null}
        </span>
        {node.props.field_type === 'select' ? (
          <select aria-label={node.props.label} required={required} defaultValue="">
            <option value="">Select an option</option>
            {node.props.options.map((option) => (
              <option key={option} value={option}>
                {option
                  .replaceAll('_', ' ')
                  .toLowerCase()
                  .replace(/^./, (char) => char.toUpperCase())}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-label={node.props.label}
            required={required}
            type={node.props.field_type === 'telephone' ? 'tel' : node.props.field_type}
            placeholder={
              ['date', 'checkbox', 'file'].includes(node.props.field_type)
                ? undefined
                : `Enter ${node.props.label.toLowerCase()}`
            }
          />
        )}
        {help ? <small>{help}</small> : null}
      </label>
    )
  }
  if (node.kind === 'text' && node.trace?.attribute_id && !node.binding) {
    const attribute = definition.business?.entities
      .find((entity) => entity.id === node.trace?.entity_id)
      ?.attributes.find((item) => item.id === node.trace?.attribute_id)
    if (
      attribute &&
      (attribute.writable === false ||
        (attribute.value_source && attribute.value_source !== 'user_entered'))
    )
      return (
        <div className="business-preview__readonly">
          <span>{attribute.name}</span>
          <strong>Assigned automatically</strong>
          <small>{node.props.content}</small>
        </div>
      )
  }
  if (node.kind === 'button') {
    const destination = node.events.find((event) => event.action === 'navigate')?.target
    const conditional = node.trace?.generated && node.props.label.startsWith('If ')
    const label = conditional
      ? (definition.screens.find((item) => item.id === destination)?.title ?? node.props.label)
      : node.props.label
    return (
      <button
        type="button"
        className="business-preview__action"
        title={conditional ? node.props.label : undefined}
        disabled={!destination}
        onClick={() => destination && navigate(destination)}
      >
        <span>
          {label}
          {conditional ? <small>Conditional route</small> : null}
        </span>
        <ArrowRight size={15} />
      </button>
    )
  }
  if (node.kind === 'container')
    return (
      <section className="business-preview__section">
        <header>
          <h3>{node.props.title}</h3>
          <span>
            {node.children.some((child) => child.kind === 'field') ? 'Details' : 'Information'}
          </span>
        </header>
        <div
          className="business-preview__fields"
          style={
            {
              '--preview-columns':
                node.props.layout[viewport].mode === 'stack'
                  ? 1
                  : node.props.layout[viewport].columns,
            } as CSSProperties
          }
        >
          {node.children.map((child) => (
            <div
              key={child.id}
              className={child.placement.span >= 12 ? 'business-preview__wide' : undefined}
            >
              <BusinessNode
                node={child}
                definition={definition}
                viewport={viewport}
                navigate={navigate}
              />
            </div>
          ))}
        </div>
      </section>
    )
  if (node.kind === 'table' && !node.binding)
    return (
      <section className="business-preview__section business-preview__records">
        <header>
          <h3>{node.props.title}</h3>
          <span>Related records</span>
        </header>
        <div className="pixels-table__scroll">
          <table>
            <thead>
              <tr>
                {node.props.columns.map((column) => (
                  <th key={column.id}>{column.label}</th>
                ))}
              </tr>
            </thead>
          </table>
        </div>
        <div className="business-preview__empty">
          <Database size={21} />
          <strong>No records to display</strong>
          <p>Business records will appear here in the running application.</p>
        </div>
      </section>
    )
  return renderApplicationNode(node, undefined, definition.fixtures)
}

export function BusinessScreenPreview({
  screen,
  definition,
  step,
  roleName,
  viewport,
  navigate,
}: {
  screen: ScreenDefinition
  definition: ApplicationDefinition
  step: WorkflowState | null | undefined
  roleName: string | undefined
  viewport: Viewport
  navigate: (id: string) => void
}) {
  const content = screen.components.filter((node) => !isDesignDocumentation(node))
  const documentation = screen.components.filter(isDesignDocumentation)
  const actions = content.filter((node) => node.kind === 'button')
  const body = content.filter((node) => node.kind !== 'button')
  // Put the task's editable information before reference tables, without changing the saved definition.
  const ordered = [
    ...body.filter((node) => node.kind !== 'table'),
    ...body.filter((node) => node.kind === 'table'),
  ]
  const workflow = definition.workflow_definitions?.find(
    (item) => item.id === screen.trace?.workflow_id,
  )
  const rules = definition.business?.rules.filter((rule) => step?.rule_ids?.includes(rule.id)) ?? []
  const requirements =
    definition.business?.requirements.filter((item) => step?.requirement_ids?.includes(item.id)) ??
    []
  const destinations = actions.flatMap((node) =>
    node.kind === 'button'
      ? node.events
          .filter((event) => event.action === 'navigate')
          .map((event) => definition.screens.find((item) => item.id === event.target))
          .filter((item) => !!item)
      : [],
  )
  const intent = {
    form: [
      'Capture the details',
      'Enter the information for this step. Required fields are marked with an asterisk.',
    ],
    search: [
      'Find the right record',
      'Search the available records, then choose where to go next.',
    ],
    review: [
      'Review before continuing',
      'Check the information and the applicable business rules before taking the next action.',
    ],
    approval: [
      'Make an informed decision',
      'Review the supporting records and approval criteria before choosing an outcome.',
    ],
    exception: [
      'Resolve the exception',
      'Review what happened and follow the recovery path defined for this process.',
    ],
    action: ['Move work forward', 'Check the information and complete the action for this step.'],
    end: [
      'Process outcome',
      'This is the end of this process path. Review its recorded outcome below.',
    ],
    start: ['Start a new process', 'Capture the information needed to begin.'],
    branch: ['Choose the next path', 'The business rules determine which path follows.'],
  }[step?.kind ?? 'form']
  const Icon = taskIcon(screen.title, step?.kind, step?.outcome)
  const presentation = taskPresentation(step, screen.title)
  const references = ordered.filter((node) => node.kind === 'table')
  const decisionNodes =
    presentation.layout === 'decision'
      ? ordered.filter(
          (node) =>
            node.kind === 'container' && node.children.some((child) => child.kind === 'field'),
        )
      : []
  const referenceInRail =
    ['document', 'planning'].includes(presentation.layout) && references.length > 0
  const mainNodes = (
    referenceInRail ? ordered.filter((node) => node.kind !== 'table') : ordered
  ).filter((node) => !decisionNodes.includes(node))
  const linkedEntities = (definition.business?.entities ?? []).filter((entity) =>
    [...(step?.reads_entity_ids ?? []), ...(step?.writes_entity_ids ?? [])].includes(entity.id),
  )
  return (
    <div
      className={`business-preview business-preview--${viewport} business-preview--${step?.kind ?? 'form'}`}
      data-outcome={step?.outcome ?? undefined}
      data-layout={presentation.layout}
    >
      <div className="business-preview__appbar">
        <span>
          <span className="business-preview__brand">
            <Layers size={17} />
          </span>
          {definition.metadata.name}
        </span>
        <span className="business-preview__mode">Interactive layout preview</span>
      </div>
      <div className="business-preview__breadcrumb">
        <span>Workspace</span>
        <span>/</span>
        <strong>{workflow?.name ?? 'Application'}</strong>
      </div>
      <header className="business-preview__heading">
        <div className="business-preview__title-icon">{createElement(Icon, { size: 23 })}</div>
        <div>
          <span className="business-preview__eyebrow">{intent[0]}</span>
          <h2>{screen.title}</h2>
          <p>{intent[1]}</p>
          <div>
            {roleName ? (
              <span className="business-preview__role">
                <UserRound size={13} />
                {roleName}
              </span>
            ) : null}
            <span>Preview only · no records are saved</span>
          </div>
        </div>
      </header>
      {['decision', 'receiving', 'recovery', 'outcome'].includes(presentation.layout) && (
        <section className="business-preview__task-strip" aria-label={presentation.label}>
          <div>
            <small>{presentation.label}</small>
            <strong>{screen.title}</strong>
          </div>
          {linkedEntities.map((entity) => (
            <span key={entity.id}>
              <Database size={14} />
              {entity.name}
            </span>
          ))}
          {presentation.layout === 'outcome' && (
            <strong>
              {step?.outcome === 'success' ? 'Completed' : (step?.outcome ?? 'Process closed')}
            </strong>
          )}
        </section>
      )}
      <div className="business-preview__layout">
        <div className="business-preview__content" key={screen.id}>
          {mainNodes.map((node) => (
            <BusinessNode
              key={node.id}
              node={node}
              definition={definition}
              viewport={viewport}
              navigate={navigate}
            />
          ))}
        </div>
        <aside className="business-preview__guidance" aria-label="Task guidance">
          {decisionNodes.length > 0 && (
            <div className="business-preview__decision-form" aria-label="Decision details">
              {decisionNodes.map((node) => (
                <BusinessNode
                  key={node.id}
                  node={node}
                  definition={definition}
                  viewport={viewport}
                  navigate={navigate}
                />
              ))}
            </div>
          )}
          {referenceInRail && (
            <div className="business-preview__reference-rail">
              <h3>Reference records</h3>
              {references.map((node) => (
                <BusinessNode
                  key={node.id}
                  node={node}
                  definition={definition}
                  viewport={viewport}
                  navigate={navigate}
                />
              ))}
            </div>
          )}
          <section>
            <span className="business-preview__rail-icon">
              <ListChecks size={17} />
            </span>
            <h3>Task ownership</h3>
            {step?.preconditions?.length ? (
              <ul>
                {step.preconditions.map((item) => (
                  <li key={item}>
                    <Check size={13} />
                    {item}
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="business-preview__ownership">
              <small>RESPONSIBLE</small>
              <strong>
                {roleName ?? (step?.kind === 'end' ? 'End of process path' : 'Not assigned yet')}
              </strong>
            </div>
          </section>
          {rules.length ? (
            <section>
              <h3>
                <ShieldCheck size={15} />
                Business checks
              </h3>
              <ul>
                {rules.map((rule) => (
                  <li key={rule.id}>
                    <span className="business-preview__check-dot" />
                    <div>
                      {rule.description}
                      {rule.status === 'assumption' ? (
                        <small>Assumption · needs confirmation</small>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {destinations.length ? (
            <section>
              <h3>What happens next</h3>
              <ul>
                {destinations.map((item, index) => (
                  <li key={`${item.id}-${index}`}>
                    <ArrowRight size={14} />
                    <span>{item.title}</span>
                  </li>
                ))}
              </ul>
              <small>
                Preview navigation follows the saved process. Rules run in the generated
                application.
              </small>
            </section>
          ) : null}
          {requirements.length ? (
            <details>
              <summary>Why this step matters</summary>
              <ul>
                {requirements.map((item) => (
                  <li key={item.id}>{item.statement}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </aside>
      </div>
      {actions.length > 0 ? (
        <footer className="business-preview__actions">
          <span>
            <ShieldCheck size={14} />
            Explore the saved process
          </span>
          <div>
            {actions.map((node) => (
              <BusinessNode
                key={node.id}
                node={node}
                definition={definition}
                viewport={viewport}
                navigate={navigate}
              />
            ))}
          </div>
        </footer>
      ) : null}
      {documentation.length > 0 ? (
        <details className="business-preview__details">
          <summary>Design notes & traceability</summary>
          {documentation.map((node) => (
            <div key={node.id}>
              {node.kind === 'container' ? (
                <>
                  <h4>{node.props.title}</h4>
                  {node.children.map((child) =>
                    child.kind === 'text' ? <p key={child.id}>{child.props.content}</p> : null,
                  )}
                </>
              ) : node.kind === 'text' ? (
                <p>{node.props.content}</p>
              ) : null}
            </div>
          ))}
        </details>
      ) : null}
    </div>
  )
}
