import type { CSSProperties, DragEvent, KeyboardEvent, ReactNode } from 'react'
import type { ApplicationDefinition, ComponentNode } from '../../../api/applicationDefinition'
import { registry, type ComponentKind } from './componentRegistry'
import { renderApplicationNode } from './ApplicationRenderer'

export type Viewport = 'desktop' | 'tablet' | 'mobile'

function componentPreview(
  node: ComponentNode,
  children?: ReactNode,
  fixtures: ApplicationDefinition['fixtures'] = [],
): ReactNode {
  return renderApplicationNode(node, children, fixtures)
}

export function CanvasNode({
  node,
  selectedId,
  onSelect,
  onMove,
  onDropNode,
  onDropPalette,
  interactive,
  viewport,
  fixtures,
}: {
  node: ComponentNode
  selectedId: string | null
  onSelect: (id: string) => void
  onMove: (id: string, direction: -1 | 1) => void
  onDropNode: (source: string, target: string) => void
  onDropPalette: (kind: ComponentKind, target: string) => void
  interactive: boolean
  viewport: Viewport
  fixtures: ApplicationDefinition['fixtures']
}) {
  const children =
    node.kind === 'container' ? (
      <div
        className="pixels-children"
        style={{ '--canvas-columns': node.props.layout[viewport].columns } as CSSProperties}
      >
        {node.children.length ? (
          node.children.map((child) => (
            <CanvasNode
              key={child.id}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
              onMove={onMove}
              onDropNode={onDropNode}
              onDropPalette={onDropPalette}
              interactive={interactive}
              viewport={viewport}
              fixtures={fixtures}
            />
          ))
        ) : (
          <p className="pixels-drop-hint">
            Choose a component from the palette to build this section.
          </p>
        )}
      </div>
    ) : undefined
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!interactive) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(node.id)
    }
    if (event.altKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault()
      onMove(node.id, event.key === 'ArrowUp' ? -1 : 1)
    }
  }
  return (
    <div
      className={`pixels-node${interactive && selectedId === node.id ? ' pixels-node--selected' : ''}`}
      data-kind={node.kind}
      style={{ '--node-span': node.placement.span } as CSSProperties}
      role="button"
      aria-disabled={!interactive}
      tabIndex={interactive ? 0 : -1}
      draggable={interactive}
      aria-label={interactive ? `Select ${registry[node.kind].label} ${node.id}` : undefined}
      aria-pressed={interactive ? selectedId === node.id : undefined}
      onClick={
        interactive
          ? (event) => {
              event.stopPropagation()
              onSelect(node.id)
            }
          : undefined
      }
      onKeyDown={onKeyDown}
      onDragStart={
        interactive
          ? (event) => {
              event.stopPropagation()
              event.dataTransfer.setData('application/x-pixels-node', node.id)
              event.dataTransfer.effectAllowed = 'move'
            }
          : undefined
      }
      onDragOver={
        interactive
          ? (event: DragEvent<HTMLDivElement>) => {
              if (
                event.dataTransfer.types.includes('application/x-pixels-node') ||
                event.dataTransfer.types.includes('application/x-pixels-kind')
              )
                event.preventDefault()
            }
          : undefined
      }
      onDrop={
        interactive
          ? (event) => {
              event.preventDefault()
              event.stopPropagation()
              const source = event.dataTransfer.getData('application/x-pixels-node')
              const kind = event.dataTransfer.getData('application/x-pixels-kind')
              if (source) onDropNode(source, node.id)
              else if (kind && node.kind === 'container' && kind in registry)
                onDropPalette(kind as ComponentKind, node.id)
            }
          : undefined
      }
    >
      {interactive && <span className="pixels-node__tag">{registry[node.kind].label}</span>}
      {componentPreview(node, children, fixtures)}
    </div>
  )
}

export function editProperty(
  node: ComponentNode,
  name: string,
  value: string | boolean | number,
): ComponentNode {
  switch (node.kind) {
    case 'container':
      return name === 'title' ? { ...node, props: { ...node.props, title: String(value) } } : node
    case 'text':
      return name === 'content'
        ? { ...node, props: { ...node.props, content: String(value) } }
        : node
    case 'field': {
      if (name === 'label') return { ...node, props: { ...node.props, label: String(value) } }
      if (name === 'help_text')
        return { ...node, props: { ...node.props, help_text: String(value) || null } }
      if (
        name === 'field_type' &&
        ['text', 'number', 'email', 'telephone', 'date', 'select', 'checkbox', 'file'].includes(
          String(value),
        )
      )
        return {
          ...node,
          props: { ...node.props, field_type: value as typeof node.props.field_type },
        }
      if (name === 'options')
        return {
          ...node,
          props: {
            ...node.props,
            options: String(value)
              .split('\n')
              .map((item) => item.trim())
              .filter(Boolean),
          },
        }
      return node
    }
    case 'table': {
      if (name === 'title') return { ...node, props: { ...node.props, title: String(value) } }
      if (name === 'columns')
        return {
          ...node,
          props: {
            ...node.props,
            columns: String(value)
              .split('\n')
              .map((label, index) => ({ id: `column_${index + 1}`, label: label.trim() }))
              .filter((column) => column.label),
          },
        }
      if (name === 'searchable')
        return { ...node, props: { ...node.props, searchable: Boolean(value) } }
      if (name === 'page_size')
        return { ...node, props: { ...node.props, page_size: Number(value) } }
      return node
    }
    case 'button':
      return name === 'label' ? { ...node, props: { ...node.props, label: String(value) } } : node
  }
}

export function propertyValue(node: ComponentNode, name: string): string | number | boolean {
  const value = (node.props as unknown as Record<string, unknown>)[name]
  if (name === 'columns' && Array.isArray(value)) return value.map((item) => item.label).join('\n')
  return Array.isArray(value)
    ? value.join('\n')
    : value === null || value === undefined
      ? ''
      : (value as string | number | boolean)
}
