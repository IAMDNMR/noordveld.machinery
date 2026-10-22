import type { ReactNode } from 'react'
import type { ApplicationDefinition, ComponentNode } from '../../../api/applicationDefinition'
import { registry } from './componentRegistry'
import { validateEditorDefinition } from '../model/applicationDefinition'

/** An inert v2 preview: only the fixed registry renders, never generated source. */
export function renderApplicationNode(
  node: ComponentNode,
  children?: ReactNode,
  fixtures: ApplicationDefinition['fixtures'] = [],
): ReactNode {
  const fixture =
    node.kind !== 'container' && node.binding?.source === 'fixture'
      ? fixtures.find((item) => item.id === node.binding?.dataset)
      : null
  if (fixture && node.kind === 'table')
    return (
      <section className="pixels-table">
        <h3>{node.props.title}</h3>
        <div className="pixels-table__scroll">
          <table>
            <thead>
              <tr>
                {fixture.fields.map((field) => (
                  <th key={field.id}>{field.id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fixture.rows.map((row, index) => (
                <tr key={index}>
                  {fixture.fields.map((field) => (
                    <td key={field.id}>{String(row[field.id] ?? '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <small>Synthetic fixture data only</small>
      </section>
    )
  if (fixture && node.kind === 'text')
    return <p className="pixels-copy">{String(fixture.rows[0]?.[node.binding!.field] ?? '')}</p>
  switch (node.kind) {
    case 'container':
      return registry.container.render(node, children)
    case 'text':
      return registry.text.render(node)
    case 'field':
      return registry.field.render(node)
    case 'table':
      return registry.table.render(node)
    case 'button':
      return registry.button.render(node)
  }
}

function PreviewNode({
  node,
  fixtures,
}: {
  node: ComponentNode
  fixtures: ApplicationDefinition['fixtures']
}) {
  return (
    <div className="pixels-node" data-kind={node.kind}>
      {renderApplicationNode(
        node,
        node.kind === 'container' ? (
          <div className="pixels-children">
            {node.children.map((child) => (
              <PreviewNode key={child.id} node={child} fixtures={fixtures} />
            ))}
          </div>
        ) : undefined,
        fixtures,
      )}
    </div>
  )
}

export function ApplicationRenderer({ definition }: { definition: unknown }) {
  const parsed = validateEditorDefinition(definition)
  if (!parsed.value)
    return (
      <div role="alert">
        This application definition is invalid or unsupported. Nothing was rendered.
      </div>
    )
  return (
    <div aria-label="Mockup-only application preview">
      <p>MOCKUP ONLY · No business data or actions</p>
      {parsed.value.screens.map((screen) => (
        <section key={screen.id}>
          <h2>{screen.title}</h2>
          {screen.components.map((node) => (
            <PreviewNode key={node.id} node={node} fixtures={parsed.value!.fixtures} />
          ))}
        </section>
      ))}
    </div>
  )
}
