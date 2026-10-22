/** Trusted transport and preview state. This file supplies no application layout. */
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

export type Data = Record<string, string | number | boolean | null>
export type RecordRow = {
  id: string
  entity: string
  data: Data
  revision: number
  links?: Record<string, string>
}
export type Attribute = {
  id: string
  name: string
  type: string
  required: boolean
  key?: boolean
  writable?: boolean
  value_source?: string
  options?: string[]
  enum?: string[]
  description?: string
  format?: string | null
  minimum?: number | null
  maximum?: number | null
  min_length?: number | null
  max_length?: number | null
  default?: string | number | boolean | null
  allow_unknown?: boolean
}
export type Entity = {
  id: string
  name: string
  attributes: Attribute[]
  writable?: boolean
  creatable?: boolean
  description?: string
  owner_role_id?: string | null
  source_system?: string
  relationships?: {
    id: string
    name?: string
    target_entity_id: string
    target?: string
    required?: boolean
    cardinality?: string
  }[]
}
export type Step = {
  id: string
  label: string
  kind: string
  role_id?: string | null
  permission?: string | null
  reads_entity_ids: string[]
  writes_entity_ids: string[]
  input_fields?: Record<string, string[]> | null
  input_relationships?: Record<string, string[]> | null
}
export type Workflow = {
  id: string
  name: string
  states: Step[]
  transitions: { source: string; target: string }[]
}
export type Instance = {
  id: string
  workflow: string
  state: string
  revision: number
  links: Record<string, string>
  step: Step
  can_act: boolean
  blocked: string[]
}
export type Identity = { id: string; name: string; role: string; tenant: string; primary?: boolean }
export type Application = {
  name: string
  project_id?: string
  entities: Entity[]
  workflows: Workflow[]
  roles: Record<string, string>
  user?: Identity
  unsupported?: string[]
  references?: {
    source: string
    target: string
    field: string
    relationship_id: string
    target_key: string | null
    enforcement: string
    required: boolean
  }[]
}
type Bootstrap = { mode: 'preview' | 'runtime'; app?: Application; preview_role?: string }
const previewRecordId = () =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `preview-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
const bootstrap: Bootstrap = JSON.parse(
  document.getElementById('studio-bootstrap')?.textContent ?? '{"mode":"runtime"}',
)
const firstTaskRole =
  bootstrap.preview_role ??
  bootstrap.app?.workflows
    .flatMap((workflow) => workflow.states)
    .find((state) => state.role_id && !['start', 'end', 'branch'].includes(state.kind))?.role_id
const previewUsers: Identity[] = Object.entries(bootstrap.app?.roles ?? {})
  .sort(([left], [right]) => Number(right === firstTaskRole) - Number(left === firstTaskRole))
  .map(([role, name]) => ({
    id: `preview-user:${role}`,
    name,
    role,
    tenant: 'local-preview',
  }))
type WireInstance = Omit<Instance, 'blocked'> & { blocked: (string | { message: string })[] }
const normalizeInstance = (instance: WireInstance): Instance => ({
  ...instance,
  blocked: instance.blocked.map((reason) => (typeof reason === 'string' ? reason : reason.message)),
})

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const value = await response.json()
  if (!response.ok)
    throw new Error(
      typeof value.error === 'string'
        ? value.error
        : (value.message ?? 'The action was refused by the application.'),
    )
  return value as T
}

export type Studio = {
  mode: 'preview' | 'runtime'
  app: Application
  records: Record<string, RecordRow[]>
  instances: Instance[]
  users: Identity[]
  user: Identity | null
  loading: boolean
  error: string | null
  signIn: (id: string) => Promise<void>
  refresh: () => Promise<void>
  createRecord: (entity: string, data: Data, links?: Record<string, string>) => Promise<RecordRow>
  updateRecord: (
    entity: string,
    id: string,
    data: Data,
    revision: number,
    taskContext?: { instance_id: string; expected_revision: number },
  ) => Promise<RecordRow>
  startWorkflow: (workflow: string, links: Record<string, string>) => Promise<Instance>
  advanceWorkflow: (
    id: string,
    revision: number,
    links?: Record<string, string>,
  ) => Promise<Instance>
}
const Context = createContext<Studio | null>(null)
export function useStudio(): Studio {
  const value = useContext(Context)
  if (!value) throw new Error('Application must be inside StudioProvider')
  return value
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const mode = bootstrap.mode
  const [app, setApp] = useState<Application>(
    bootstrap.app ?? { name: 'Application', entities: [], workflows: [], roles: {} },
  )
  const [records, setRecords] = useState<Record<string, RecordRow[]>>({})
  const recordsRef = useRef<Record<string, RecordRow[]>>({})
  const [instances, setInstances] = useState<Instance[]>([])
  const [users, setUsers] = useState<Identity[]>(mode === 'preview' ? previewUsers : [])
  const [user, setUser] = useState<Identity | null>(
    mode === 'preview' ? (previewUsers[0] ?? null) : null,
  )
  const [loading, setLoading] = useState(mode === 'runtime')
  const [error, setError] = useState<string | null>(null)
  async function refresh() {
    if (mode === 'preview') return
    const next = await api<Application & { user?: Identity & { actor?: string } }>('application')
    next.entities = next.entities.map((entity) => ({
      ...entity,
      attributes: entity.attributes.map((attribute) => ({
        ...attribute,
        options: attribute.options ?? (attribute as Attribute & { enum?: string[] }).enum ?? [],
      })),
      relationships: entity.relationships?.map((relationship) => ({
        ...relationship,
        target_entity_id:
          relationship.target_entity_id ??
          (relationship as typeof relationship & { target?: string }).target ??
          '',
      })),
    }))
    const rows = await Promise.all(
      next.entities.map(
        async (entity) =>
          [
            entity.id,
            (await api<RecordRow[]>(`records/${encodeURIComponent(entity.id)}`)).map((row) => ({
              ...row,
              entity: entity.id,
            })),
          ] as const,
      ),
    )
    setApp(next)
    const identity = next.user
      ? {
          ...next.user,
          id: next.user.id ?? next.user.actor ?? '',
          name: next.user.name ?? next.roles[next.user.role] ?? next.user.role,
        }
      : null
    setUser(identity)
    const allRows = Object.fromEntries(rows)
    for (const [entity, values] of Object.entries(allRows)) {
      const refs = next.references?.filter((reference) => reference.source === entity) ?? []
      allRows[entity] = values.map((row) => {
        const links: Record<string, string> = {}
        for (const reference of refs) {
          const target = allRows[reference.target]?.find((candidate) =>
            reference.enforcement === 'foreign_key'
              ? candidate.data[reference.target_key ?? ''] === row.data[reference.field]
              : candidate.id === row.data[reference.field],
          )
          if (target) {
            links[reference.relationship_id] = target.id
            if (refs.filter((other) => other.target === reference.target).length === 1)
              links[reference.target] = target.id
          }
        }
        return { ...row, links }
      })
    }
    recordsRef.current = allRows
    setRecords(allRows)
    const work = await api<WireInstance[]>('instances')
    setInstances(work.map(normalizeInstance))
  }
  useEffect(() => {
    if (mode === 'preview') {
      return
    }
    void api<Identity[]>('demo-users')
      .then(async (identities) => {
        setUsers(identities)
        try {
          await refresh()
        } catch {
          setUser(null)
        }
      })
      .catch(() => setError('Application identities could not be loaded.'))
      .finally(() => setLoading(false))
    // The bootstrap is immutable for the lifetime of the generated application.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  async function action<T>(work: () => Promise<T>): Promise<T> {
    setError(null)
    try {
      return await work()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Action failed.')
      throw cause
    }
  }
  async function signIn(id: string) {
    return action(async () => {
      if (mode === 'preview') {
        const identity = users.find((item) => item.id === id)
        if (!identity)
          throw new Error(
            'Unknown application identity. Choose an identity from users; a role ID is not a user ID.',
          )
        setUser(identity)
        return
      }
      await api('login', { user_id: id })
      await refresh()
    })
  }
  function validate(entityId: string, data: Data) {
    const entity = app.entities.find((item) => item.id === entityId)
    if (!entity) throw new Error('Unknown record type.')
    for (const attribute of entity.attributes) {
      if (attribute.value_source && attribute.value_source !== 'user_entered') continue
      if (attribute.required && (data[attribute.id] === undefined || data[attribute.id] === ''))
        throw new Error(`${attribute.name} is required.`)
    }
  }
  async function createRecord(entity: string, data: Data, links: Record<string, string> = {}) {
    return action(async () => {
      const mapped: Data = { ...data }
      const refs = app.references?.filter((reference) => reference.source === entity) ?? []
      for (const [key, id] of Object.entries(links)) {
        const matches = refs.filter((reference) =>
          [reference.field, reference.relationship_id, reference.target].includes(key),
        )
        if (matches.length !== 1)
          throw new Error('Choose an explicit relationship when linking this record.')
        const reference = matches[0]
        const target = recordsRef.current[reference.target]?.find((row) => row.id === id)
        if (!target)
          throw new Error(
            'The selected related record is unavailable. Refresh and choose it again.',
          )
        mapped[reference.field] =
          reference.enforcement === 'foreign_key'
            ? target.data[reference.target_key ?? '']
            : target.id
      }
      if (mode === 'runtime') {
        const row = await api<RecordRow>(`records/${encodeURIComponent(entity)}`, {
          data: mapped,
        })
        await refresh()
        return { ...row, entity }
      }
      validate(entity, mapped)
      const definition = app.entities.find((item) => item.id === entity)
      for (const attribute of definition?.attributes ?? []) {
        if (attribute.value_source === 'system_generated' && attribute.key) {
          mapped[attribute.id] =
            attribute.type === 'integer'
              ? Math.max(
                  0,
                  ...(recordsRef.current[entity] ?? []).map(
                    (item) => Number(item.data[attribute.id]) || 0,
                  ),
                ) + 1
              : previewRecordId()
        }
      }
      const row = { id: previewRecordId(), entity, data: mapped, revision: 1, links }
      const current = recordsRef.current
      const next = { ...current, [entity]: [...(current[entity] ?? []), row] }
      recordsRef.current = next
      setRecords(next)
      return row
    })
  }
  async function updateRecord(
    entity: string,
    id: string,
    data: Data,
    revision: number,
    taskContext?: { instance_id: string; expected_revision: number },
  ) {
    return action(async () => {
      if (mode === 'runtime') {
        const row = await api<RecordRow>(
          `records/${encodeURIComponent(entity)}/${encodeURIComponent(id)}`,
          { data, expected_revision: revision, task_context: taskContext },
        )
        await refresh()
        return { ...row, entity }
      }
      const previous = recordsRef.current[entity]?.find((item) => item.id === id)
      if (!previous || previous.revision !== revision)
        throw new Error('Record has changed. Reopen it.')
      const merged = { ...previous.data, ...data }
      validate(entity, merged)
      const row = { ...previous, data: merged, revision: revision + 1 }
      const current = recordsRef.current
      const next = {
        ...current,
        [entity]: current[entity].map((item) => (item.id === id ? row : item)),
      }
      recordsRef.current = next
      setRecords(next)
      return row
    })
  }
  async function startWorkflow(workflow: string, links: Record<string, string>) {
    return action(async () => {
      if (mode === 'preview')
        throw new Error(
          'Run the application to execute its server-validated process. This preview keeps form changes in memory only.',
        )
      const value = await api<WireInstance>('instances', { workflow_id: workflow, links })
      await refresh()
      return normalizeInstance(value)
    })
  }
  async function advanceWorkflow(id: string, revision: number, links: Record<string, string> = {}) {
    return action(async () => {
      if (mode === 'preview')
        throw new Error('Run the application to check permissions, rules and advance this process.')
      const value = await api<WireInstance>(`instances/${encodeURIComponent(id)}/advance`, {
        expected_revision: revision,
        links,
      })
      await refresh()
      return normalizeInstance(value)
    })
  }
  return (
    <Context.Provider
      value={{
        mode,
        app: { ...app, user: user ?? undefined },
        records,
        instances,
        users,
        user,
        loading,
        error,
        signIn,
        refresh,
        createRecord,
        updateRecord,
        startWorkflow,
        advanceWorkflow,
      }}
    >
      {children}
    </Context.Provider>
  )
}
