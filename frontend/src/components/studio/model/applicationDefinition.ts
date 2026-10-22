import type {
  ApplicationDefinition,
  ComponentNode,
  GridSettings,
} from '../../../api/applicationDefinition'
import { registry, type ComponentKind } from '../canvas/componentRegistry'
import { parseWorkflow } from './workflowDefinition'
import { validBinding, validFixtures, validLocalState } from './fixtures'
import {
  businessError,
  crossReferenceError,
  traceError,
  validationRule,
} from './businessDefinition'

type RecordValue = Record<string, unknown>
const record = (value: unknown): value is RecordValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const exact = (value: RecordValue, keys: string[]) =>
  Object.keys(value).every((key) => keys.includes(key))
const id = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-z][a-z0-9_-]{1,79}$/.test(value)
const text = (value: unknown, min: number, max: number) =>
  typeof value === 'string' && value.length >= min && value.length <= max
const strings = (value: unknown, max: number) =>
  Array.isArray(value) && value.length <= max && value.every((item) => typeof item === 'string')
const integer = (value: unknown, min: number, max: number) =>
  typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max
const validation = validationRule

const approval = (value: unknown) =>
  record(value) &&
  exact(value, [
    'scope',
    'revision',
    'content_sha256',
    'approved_by',
    'approved_at',
    'warnings_acknowledged',
    'comment',
  ]) &&
  (value.comment === undefined || text(value.comment, 0, 1000)) &&
  ['process', 'design'].includes(value.scope as string) &&
  integer(value.revision, 1, Number.MAX_SAFE_INTEGER) &&
  typeof value.content_sha256 === 'string' &&
  /^[0-9a-f]{64}$/.test(value.content_sha256) &&
  text(value.approved_by, 1, 120) &&
  text(value.approved_at, 1, 40) &&
  strings(value.warnings_acknowledged ?? [], 500)

function grid(value: unknown): value is GridSettings {
  return (
    record(value) &&
    exact(value, ['mode', 'columns']) &&
    ((value.mode === 'stack' && value.columns === 1) ||
      (value.mode === 'grid' && integer(value.columns, 1, 12)))
  )
}
function layout(value: unknown): boolean {
  return (
    record(value) &&
    exact(value, ['mobile', 'tablet', 'desktop']) &&
    grid(value.mobile) &&
    grid(value.tablet) &&
    grid(value.desktop)
  )
}
function props(node: RecordValue): boolean {
  const value = node.props
  if (!record(value)) return false
  switch (node.kind) {
    case 'container':
      return exact(value, ['title', 'layout']) && text(value.title, 0, 120) && layout(value.layout)
    case 'text':
      return exact(value, ['content']) && text(value.content, 0, 1000)
    case 'field':
      return (
        exact(value, ['field_type', 'label', 'help_text', 'options', 'validations']) &&
        ['text', 'number', 'email', 'telephone', 'date', 'select', 'checkbox', 'file'].includes(
          value.field_type as string,
        ) &&
        text(value.label, 1, 120) &&
        (value.help_text === null || text(value.help_text, 0, 500)) &&
        strings(value.options, 100) &&
        Array.isArray(value.validations) &&
        value.validations.length <= 20 &&
        value.validations.every(validation)
      )
    case 'table': {
      if (
        !exact(value, ['title', 'columns', 'searchable', 'filters', 'page_size']) ||
        !text(value.title, 1, 120) ||
        !Array.isArray(value.columns) ||
        value.columns.length < 1 ||
        value.columns.length > 30 ||
        typeof value.searchable !== 'boolean' ||
        !strings(value.filters, 20) ||
        !integer(value.page_size, 1, 100)
      )
        return false
      const columnIds = new Set<string>()
      for (const column of value.columns) {
        if (
          !record(column) ||
          !exact(column, ['id', 'label']) ||
          !id(column.id) ||
          !text(column.label, 1, 120) ||
          columnIds.has(column.id)
        )
          return false
        columnIds.add(column.id)
      }
      return true
    }
    case 'button':
      return exact(value, ['label']) && text(value.label, 1, 120)
    default:
      return false
  }
}

/** Pydantic serializes absent optional node fields as null; restore the
 * editor's discriminated shape before strict validation. Never drop a
 * non-null field or an unknown property. */
export function normalizeStoredDefinition(source: unknown): unknown {
  if (!record(source) || !Array.isArray(source.screens)) return source
  const normalizeNode = (value: unknown): unknown => {
    if (!record(value)) return value
    const node = { ...value }
    if (node.trace === null) delete node.trace
    if (node.kind === 'container') {
      if (node.binding === null) delete node.binding
      if (node.events === null) delete node.events
      if (Array.isArray(node.children)) node.children = node.children.map(normalizeNode)
    } else {
      if (node.children === null) delete node.children
      if (node.events === null) node.events = []
    }
    return node
  }
  const normalizeScreen = (screen: unknown): unknown => {
    if (!record(screen) || !Array.isArray(screen.components)) return screen
    const result: RecordValue = { ...screen, components: screen.components.map(normalizeNode) }
    if (result.trace === null) delete result.trace
    return result
  }
  return { ...source, screens: source.screens.map(normalizeScreen) }
}

/** Strict, deliberately limited v2 editor subset. Backend remains authoritative on persistence. */
export function validateEditorDefinition(source: unknown): {
  value: ApplicationDefinition | null
  error: string | null
} {
  const fail = (error: string) => ({ value: null, error })
  if (
    !record(source) ||
    !exact(source, [
      'version',
      'id',
      'metadata',
      'screens',
      'theme',
      'fixtures',
      'local_state',
      'navigation',
      'workflows',
      'workflow_definitions',
      'business',
      'approvals',
      'revision',
      'studio_flow',
      'project_lifecycle',
      'generated_frontend',
      'frontend_required',
    ]) ||
    source.version !== 2 ||
    !id(source.id) ||
    !record(source.metadata) ||
    !exact(source.metadata, ['name', 'description', 'purpose', 'domain']) ||
    !text(source.metadata.name, 1, 120) ||
    !text(source.metadata.description, 0, 1000) ||
    !text(source.metadata.purpose, 0, 1000) ||
    !['finance', 'crm', 'inventory', 'logistics', 'manufacturing', 'other'].includes(
      source.metadata.domain as string,
    )
  )
    return fail('Application metadata is invalid.')
  if (source.frontend_required !== undefined && typeof source.frontend_required !== 'boolean')
    return fail('Frontend generation requirement is invalid.')
  // Executable preview content is always fetched from the owner-scoped server endpoint.
  // The component editor carries this server-owned artifact through edits without executing it.
  if (source.generated_frontend != null && !record(source.generated_frontend))
    return fail('Generated frontend artifact is invalid.')
  const theme = source.theme
  if (
    !record(theme) ||
    !exact(theme, ['primary', 'background', 'surface', 'text', 'font', 'logo']) ||
    !['primary', 'background', 'surface', 'text'].every(
      (key) => typeof theme[key] === 'string' && /^#[0-9a-fA-F]{6}$/.test(theme[key] as string),
    ) ||
    !['inter', 'system', 'serif'].includes(theme.font as string) ||
    theme.logo !== null
  )
    return fail('Theme is invalid or uses an unsupported asset.')
  if (!validFixtures(source.fixtures) || !validLocalState(source.local_state))
    return fail('Fixture or local-state declarations are invalid.')
  if (!Array.isArray(source.screens) || source.screens.length < 1 || source.screens.length > 150)
    return fail('At least one valid screen is required.')
  if (
    source.navigation !== undefined &&
    (!Array.isArray(source.navigation) ||
      source.navigation.length > 150 ||
      source.navigation.some(
        (item) =>
          !record(item) ||
          !exact(item, ['screen_id', 'label']) ||
          !id(item.screen_id) ||
          !text(item.label, 1, 120),
      ))
  )
    return fail('Navigation is invalid.')
  if (
    source.workflows !== undefined &&
    (!Array.isArray(source.workflows) ||
      source.workflows.length > 20 ||
      source.workflows.some((item) => !id(item)))
  )
    return fail('Workflow references are invalid.')
  if (
    source.workflow_definitions !== undefined &&
    (!Array.isArray(source.workflow_definitions) ||
      source.workflow_definitions.length > 20 ||
      source.workflow_definitions.some((item) => !parseWorkflow(item)))
  )
    return fail('Workflow definitions are invalid.')
  if (
    source.workflows &&
    (source.workflows as string[]).some(
      (ref) =>
        !(source.workflow_definitions as Array<{ id: string }> | undefined)?.some(
          (workflow) => workflow.id === ref,
        ),
    )
  )
    return fail('Workflow reference is unresolved.')
  if (source.revision !== undefined && !integer(source.revision, 0, Number.MAX_SAFE_INTEGER))
    return fail('Revision is invalid.')
  if (source.business !== undefined) {
    const error = businessError(source.business)
    if (error) return fail(error)
  }
  if (
    (source.approvals !== undefined &&
      (!Array.isArray(source.approvals) ||
        source.approvals.length > 2 ||
        !source.approvals.every(approval))) ||
    new Set(((source.approvals ?? []) as RecordValue[]).map((item) => item.scope)).size !==
      ((source.approvals ?? []) as unknown[]).length
  )
    return fail('Approval records are invalid.')
  const screenIdSet = new Set(
    (source.screens as unknown[]).map((screen) => (record(screen) ? screen.id : null)),
  )
  const ids = new Set<string>([source.id])
  let count = 0
  const visit = (node: unknown, depth: number, root: boolean): string | null => {
    if (!record(node) || typeof node.kind !== 'string' || !(node.kind in registry))
      return 'Unsupported component kind.'
    if (!id(node.id) || ids.has(node.id)) return 'Component IDs must be valid and unique.'
    ids.add(node.id)
    count += 1
    if (count > 5000 || depth > 4) return 'Component tree exceeds the supported size or depth.'
    if (
      !record(node.placement) ||
      !exact(node.placement, ['span']) ||
      !integer(node.placement.span, 1, 12) ||
      !props(node)
    )
      return `Invalid ${node.kind} properties or layout.`
    if (root && node.kind === 'field') return 'Form fields must be inside a section.'
    if (node.kind === 'container') {
      if (
        !exact(node, ['kind', 'id', 'props', 'placement', 'children', 'trace']) ||
        traceError(node.trace) ||
        !Array.isArray(node.children) ||
        node.children.length > 100
      )
        return 'Invalid section children.'
      for (const child of node.children) {
        if (!record(child) || !registry.container.children.includes(child.kind as ComponentKind))
          return 'Unsupported child component.'
        const error = visit(child, depth + 1, false)
        if (error) return error
      }
      return null
    }
    const base = ['kind', 'id', 'props', 'placement', 'binding', 'events', 'trace']
    // Only buttons may carry events, and only inert navigation to a screen of this definition (as generated from the process).
    const events =
      node.kind === 'button'
        ? Array.isArray(node.events) &&
          node.events.length <= 10 &&
          node.events.every(
            (event) =>
              record(event) &&
              exact(event, ['trigger', 'action', 'target', 'value']) &&
              event.trigger === 'click' &&
              event.action === 'navigate' &&
              screenIdSet.has(event.target) &&
              (event.value === undefined || event.value === null),
          )
        : Array.isArray(node.events) && node.events.length === 0
    if (
      !exact(node, base) ||
      traceError(node.trace) ||
      ((node.kind === 'text' || node.kind === 'table' || node.kind === 'field') &&
        !validBinding(
          node.binding,
          source.fixtures as ApplicationDefinition['fixtures'],
          source.local_state as ApplicationDefinition['local_state'],
        )) ||
      (node.kind === 'button' && node.binding !== null) ||
      !events
    )
      return 'Unsupported binding, event or property.'
    return null
  }
  for (const screen of source.screens) {
    if (
      !record(screen) ||
      !exact(screen, ['id', 'title', 'components', 'trace']) ||
      traceError(screen.trace) ||
      !id(screen.id) ||
      ids.has(screen.id) ||
      !text(screen.title, 1, 120) ||
      !Array.isArray(screen.components) ||
      screen.components.length < 1 ||
      screen.components.length > 100
    )
      return fail('Screen is invalid.')
    ids.add(screen.id)
    for (const node of screen.components) {
      const error = visit(node, 1, true)
      if (error) return fail(error)
    }
  }
  const screenIds = new Set(source.screens.map((screen) => (screen as RecordValue).id))
  if (
    source.navigation &&
    (source.navigation as RecordValue[]).some((item) => !screenIds.has(item.screen_id))
  )
    return fail('Navigation refers to an unknown screen.')
  const referenceError = crossReferenceError(source as unknown as ApplicationDefinition)
  if (referenceError) return fail(referenceError)
  return { value: source as unknown as ApplicationDefinition, error: null }
}

export const emptyDefinition = (): ApplicationDefinition => ({
  version: 2,
  id: 'app_pixels',
  metadata: { name: 'Untitled application', description: '', purpose: '', domain: 'other' },
  screens: [
    {
      id: 'screen_main',
      title: 'New screen',
      components: [registry.container.create('container_main')],
    },
  ],
  theme: {
    primary: '#00756A',
    background: '#FFFFFF',
    surface: '#F7F5F0',
    text: '#14181A',
    font: 'inter',
    logo: null,
  },
  fixtures: [],
  local_state: [],
})

export function findNode(nodes: ComponentNode[], selectedId: string | null): ComponentNode | null {
  for (const node of nodes) {
    if (node.id === selectedId) return node
    if (node.kind === 'container') {
      const found = findNode(node.children, selectedId)
      if (found) return found
    }
  }
  return null
}

export function nextId(definition: ApplicationDefinition, kind: ComponentKind): string {
  let counter = 1
  while (
    definition.screens.some(
      (screen) =>
        findNode(screen.components, `${kind}_${counter}`) || screen.id === `${kind}_${counter}`,
    ) ||
    `${kind}_${counter}` === definition.id
  )
    counter += 1
  return `${kind}_${counter}`
}

function mapNodes(
  nodes: ComponentNode[],
  target: string,
  transform: (node: ComponentNode) => ComponentNode,
): ComponentNode[] {
  return nodes.map((node) =>
    node.id === target
      ? transform(node)
      : node.kind === 'container'
        ? { ...node, children: mapNodes(node.children, target, transform) }
        : node,
  )
}

export function updateNode(
  definition: ApplicationDefinition,
  target: string,
  transform: (node: ComponentNode) => ComponentNode,
  screenIndex = 0,
): ApplicationDefinition {
  return {
    ...definition,
    screens: definition.screens.map((screen, index) =>
      index === screenIndex
        ? { ...screen, components: mapNodes(screen.components, target, transform) }
        : screen,
    ),
  }
}

export function insertNode(
  definition: ApplicationDefinition,
  selectedId: string | null,
  kind: ComponentKind,
  screenIndex = 0,
): ApplicationDefinition | null {
  const selected = findNode(definition.screens[screenIndex].components, selectedId)
  const parentId = selected?.kind === 'container' ? selected.id : null
  if (kind === 'field' && !parentId) return null
  const node = registry[kind].create(nextId(definition, kind)) as ComponentNode
  if (parentId)
    return updateNode(
      definition,
      parentId,
      (parent) =>
        parent.kind === 'container' ? { ...parent, children: [...parent.children, node] } : parent,
      screenIndex,
    )
  return {
    ...definition,
    screens: definition.screens.map((screen, index) =>
      index === screenIndex ? { ...screen, components: [...screen.components, node] } : screen,
    ),
  }
}

function moveIn(nodes: ComponentNode[], target: string, direction: -1 | 1): ComponentNode[] {
  const index = nodes.findIndex((node) => node.id === target)
  if (index >= 0) {
    const destination = index + direction
    if (destination < 0 || destination >= nodes.length) return nodes
    const result = [...nodes]
    ;[result[index], result[destination]] = [result[destination], result[index]]
    return result
  }
  return nodes.map((node) =>
    node.kind === 'container'
      ? { ...node, children: moveIn(node.children, target, direction) }
      : node,
  )
}

export function moveNode(
  definition: ApplicationDefinition,
  target: string,
  direction: -1 | 1,
  screenIndex = 0,
): ApplicationDefinition {
  return {
    ...definition,
    screens: definition.screens.map((screen, index) =>
      index === screenIndex
        ? { ...screen, components: moveIn(screen.components, target, direction) }
        : screen,
    ),
  }
}

/** Drag reorder is confined to siblings, so parent/child constraints cannot be bypassed. */
export function moveBefore(
  definition: ApplicationDefinition,
  source: string,
  target: string,
  screenIndex = 0,
): ApplicationDefinition {
  if (source === target) return definition
  const reorder = (nodes: ComponentNode[]): ComponentNode[] => {
    const from = nodes.findIndex((node) => node.id === source)
    const to = nodes.findIndex((node) => node.id === target)
    if (from >= 0 && to >= 0) {
      const result = [...nodes]
      const [item] = result.splice(from, 1)
      result.splice(
        result.findIndex((node) => node.id === target),
        0,
        item,
      )
      return result
    }
    return nodes.map((node) =>
      node.kind === 'container' ? { ...node, children: reorder(node.children) } : node,
    )
  }
  return {
    ...definition,
    screens: definition.screens.map((screen, index) =>
      index === screenIndex ? { ...screen, components: reorder(screen.components) } : screen,
    ),
  }
}

function removeIn(nodes: ComponentNode[], target: string): ComponentNode[] {
  return nodes
    .filter((node) => node.id !== target)
    .map((node) =>
      node.kind === 'container' ? { ...node, children: removeIn(node.children, target) } : node,
    )
}

export function removeNode(
  definition: ApplicationDefinition,
  target: string,
  screenIndex = 0,
): ApplicationDefinition {
  return {
    ...definition,
    screens: definition.screens.map((screen, index) =>
      index === screenIndex
        ? { ...screen, components: removeIn(screen.components, target) }
        : screen,
    ),
  }
}

export function duplicateNode(
  definition: ApplicationDefinition,
  target: string,
  screenIndex = 0,
): ApplicationDefinition {
  const original = findNode(definition.screens[screenIndex].components, target)
  if (!original) return definition
  let result = definition
  const copy = (node: ComponentNode): ComponentNode => {
    const reservedId = nextId(result, node.kind)
    // Reserve the new ID while recursively cloning nested containers.
    const clone =
      node.kind === 'container'
        ? ({ ...node, id: reservedId, children: [] } as ComponentNode)
        : ({ ...node, id: reservedId } as ComponentNode)
    result = {
      ...result,
      screens: result.screens.map((screen, i) =>
        i === screenIndex ? { ...screen, components: [...screen.components, clone] } : screen,
      ),
    }
    return node.kind === 'container'
      ? ({ ...clone, children: node.children.map(copy) } as ComponentNode)
      : clone
  }
  const duplicated = copy(original)
  const insertAfter = (nodes: ComponentNode[]): ComponentNode[] => {
    const index = nodes.findIndex((node) => node.id === target)
    if (index >= 0) return [...nodes.slice(0, index + 1), duplicated, ...nodes.slice(index + 1)]
    return nodes.map((node) =>
      node.kind === 'container' ? { ...node, children: insertAfter(node.children) } : node,
    )
  }
  return {
    ...definition,
    screens: definition.screens.map((screen, i) =>
      i === screenIndex ? { ...screen, components: insertAfter(screen.components) } : screen,
    ),
  }
}
