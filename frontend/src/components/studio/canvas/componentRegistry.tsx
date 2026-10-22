import type { ReactNode } from 'react'
import type { ComponentKind, ComponentNode } from '../../../api/applicationDefinition'

type Property = {
  name: string
  label: string
  control: 'text' | 'multiline' | 'select' | 'checkbox' | 'number'
  max?: number
}
type Entry<K extends ComponentKind> = {
  label: string
  description: string
  children: ComponentKind[]
  properties: Property[]
  create: (id: string) => Extract<ComponentNode, { kind: K }>
  render: (node: Extract<ComponentNode, { kind: K }>, children?: ReactNode) => ReactNode
}
const layout = {
  mobile: { mode: 'stack' as const, columns: 1 },
  tablet: { mode: 'grid' as const, columns: 2 },
  desktop: { mode: 'grid' as const, columns: 2 },
}

export const registry: { [K in ComponentKind]: Entry<K> } = {
  container: {
    label: 'Section',
    description: 'Group related components',
    children: ['container', 'text', 'field', 'table', 'button'],
    properties: [{ name: 'title', label: 'Title', control: 'text', max: 120 }],
    create: (id) => ({
      kind: 'container',
      id,
      props: { title: 'New section', layout },
      placement: { span: 12 },
      children: [],
    }),
    render: (node, children) => (
      <section className="pixels-section">
        <h2>{node.props.title}</h2>
        {children}
      </section>
    ),
  },
  text: {
    label: 'Text',
    description: 'Heading or descriptive copy',
    children: [],
    properties: [{ name: 'content', label: 'Content', control: 'multiline', max: 1000 }],
    create: (id) => ({
      kind: 'text',
      id,
      props: { content: 'Your text here' },
      placement: { span: 12 },
      binding: null,
      events: [],
    }),
    render: (node) => <p className="pixels-copy">{node.props.content}</p>,
  },
  field: {
    label: 'Form field',
    description: 'Mock input or dropdown',
    children: [],
    properties: [
      { name: 'label', label: 'Label', control: 'text', max: 120 },
      { name: 'help_text', label: 'Help text', control: 'text', max: 500 },
      { name: 'field_type', label: 'Input type', control: 'select' },
      { name: 'options', label: 'Options', control: 'multiline' },
    ],
    create: (id) => ({
      kind: 'field',
      id,
      props: {
        field_type: 'text',
        label: 'New field',
        help_text: null,
        options: [],
        validations: [],
      },
      placement: { span: 6 },
      binding: null,
      events: [],
    }),
    render: (node) => (
      <div className="pixels-field">
        <span className="pixels-field__label">{node.props.label}</span>
        {node.props.field_type === 'select' ? (
          <select aria-label={node.props.label} defaultValue="">
            <option value="">Select…</option>
            {node.props.options.map((option, i) => (
              <option key={i}>{option}</option>
            ))}
          </select>
        ) : (
          <input
            aria-label={node.props.label}
            type={node.props.field_type === 'telephone' ? 'tel' : node.props.field_type}
            onClick={(event) => event.stopPropagation()}
          />
        )}
        {node.props.help_text && <small>{node.props.help_text}</small>}
      </div>
    ),
  },
  table: {
    label: 'Table',
    description: 'Fixture-only data grid',
    children: [],
    properties: [
      { name: 'title', label: 'Title', control: 'text', max: 120 },
      { name: 'columns', label: 'Columns (one per line)', control: 'multiline' },
      { name: 'searchable', label: 'Searchable', control: 'checkbox' },
      { name: 'page_size', label: 'Page size', control: 'number' },
    ],
    create: (id) => ({
      kind: 'table',
      id,
      props: {
        title: 'New table',
        columns: [{ id: 'column_1', label: 'Column' }],
        searchable: false,
        filters: [],
        page_size: 20,
      },
      placement: { span: 12 },
      binding: null,
      events: [],
    }),
    render: (node) => (
      <section className="pixels-table">
        <h3>{node.props.title}</h3>
        {node.props.searchable && (
          <input aria-label={`Search ${node.props.title}`} placeholder="Search mock data" />
        )}
        <div className="pixels-table__scroll">
          <table>
            <thead>
              <tr>
                {node.props.columns.map((c) => (
                  <th key={c.id}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={node.props.columns.length}>No live business data</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    ),
  },
  button: {
    label: 'Button',
    description: 'Inert mockup action',
    children: [],
    properties: [{ name: 'label', label: 'Label', control: 'text', max: 120 }],
    create: (id) => ({
      kind: 'button',
      id,
      props: { label: 'Action' },
      placement: { span: 12 },
      binding: null,
      events: [],
    }),
    render: (node) => (
      <span className="pixels-inert-button" aria-disabled="true">
        {node.props.label}
      </span>
    ),
  },
}
export type { ComponentKind }
export const paletteKinds: ComponentKind[] = ['container', 'text', 'field', 'table', 'button']
