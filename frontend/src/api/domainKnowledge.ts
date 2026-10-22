import { apiGet, apiPost, getActiveOrganization } from './client'
import type { ApplicationDefinition } from './applicationDefinition'

/** Shared domain knowledge (backend app/domain_knowledge). The backend validates everything; these types mirror it. */
export type Provenance = {
  kind: 'verified_source' | 'derived' | 'synthetic' | 'user_provided' | 'assumption'
  reference: string
  verification: 'verified' | 'unverified' | 'needs_review'
}
export type DomainSummary = {
  id: string
  name: string
  description: string
  scope: string
  parent_id: string | null
  depends_on: string[]
  keywords: string[]
  provenance: Provenance
  entity_count: number
  process_ids: string[]
  children: string[]
}
export type PackRef = { id: string; version: string; synthetic?: boolean }
export type Finding = {
  id: string
  code: string
  severity: 'error' | 'warning' | 'info'
  items: string[]
  message: string
}
export type Analysis = {
  findings: Finding[]
  counts: Record<string, number>
  provenance: Record<string, number>
}
export type Decision = {
  id: string
  question: string
  status: 'open' | 'decided'
  answer: string
  affects: string[]
  provenance: Provenance
}
export type EntitySummary = {
  id: string
  canonical_name: string
  domain_id: string
  description: string
  attribute_count: number
  provenance: Provenance
  operational_label: string | null
}
export type Attribute = {
  id: string
  name: string
  type: string
  required: boolean
  key: boolean
  value_source: string
  mutability: string
  sensitivity: string
  code_list_id: string | null
  provenance: Provenance | null
}
export type Relationship = {
  id: string
  source_id: string
  type: string
  target_id: string
  cardinality: string
  meaning: string
  required: boolean
  provenance: Provenance
}
export type EntityDetail = {
  entity: EntitySummary & { attributes: Attribute[]; natural_keys: string[] }
  concept: {
    id: string
    canonical_name: string
    definition: string
    synonyms: { term: string; domain_id: string | null }[]
    acronyms: string[]
  } | null
  outgoing: Relationship[]
  incoming: Relationship[]
  rules: { id: string; description: string; status: string; provenance: Provenance }[]
  processes: { id: string; name: string; design_template: string }[]
  events: { id: string; name: string; from_state: string; to_state: string }[]
  mappings: {
    id: string
    source_system: string
    source_entity: string
    source_attribute: string
    attribute_id: string
    transform: string
  }[]
  decisions: Decision[]
}
export type SearchHit = {
  concept_id: string
  entity_id: string | null
  canonical_name: string
  domain_id: string
  kind: string
  matched: string[]
  provenance: Provenance
}
export type GraphView = {
  nodes: { id: string; label: string; domain_id: string; provenance: string }[]
  edges: {
    id: string
    source: string
    target: string
    type: string
    cardinality: string
    provenance: string
  }[]
}
export type Hop = {
  relationship_id: string
  type: string
  from: string
  to: string
  forward: boolean
}
export type Impact = {
  item: { id: string; group: string; name: string }
  dependents: { id: string; group: string; name: string }[]
  projects: {
    project_id: string
    revision: number
    entities: string[]
    steps: string[]
    screens: string[]
  }[]
  project_storage: string
}
export type VersionMeta = {
  pack_id: string
  version: string
  status: 'draft' | 'under_review' | 'approved' | 'deprecated'
  content_sha256: string
  proposed_by: string
  reason: string
  created_at: string
  title: string
}
export type Change = {
  group: string
  item_id: string
  change: 'added' | 'removed' | 'changed'
  fields?: string[]
}
export type DryRun = {
  valid: boolean
  errors: { location: string; message: string }[]
  normalizations: { row: number; column: string; original: string; normalized: string }[]
  pack_id?: string
  version?: string
  content_sha256?: string
  base_version?: string | null
  changes?: Change[]
  summary?: Record<string, number>
  compatibility?: { level: string; ok: boolean; message: string; breaking: string[] }
  analysis?: Analysis
  already_present?: boolean
  version_conflict?: boolean
}
export type GraphStatus = {
  mode: string
  writes_enabled: boolean
  isolation?: {
    operational_graph_configured: boolean
    dedicated_domain_graph_configured: boolean
    writes_allowed: boolean
    blocker: string | null
  }
  collisions_with_operational_graph: string[]
  schema_proposal: string[]
  read_queries: string[]
  namespace: { labels: string[]; relationship_types: string[] }
  write_plan: { statements: number; rows: number; executed: boolean }
  note: string
}
export type Suggestion = {
  pack: PackRef
  domains: { domain_id: string; name: string; matched_keywords: string[] }[]
  concepts: {
    concept_id: string
    entity_id: string | null
    canonical_name: string
    domain_id: string
    matched: string[]
    provenance: Provenance
  }[]
  ambiguous_terms: { term: string; concept_ids: string[]; message: string }[]
  missing_dependencies: { entity_id: string; reason: string }[]
  processes: { id: string; name: string; design_template: string }[]
  decisions: Decision[]
}
export type AdoptReport = {
  added: string[]
  kept_existing: string[]
  missing_dependencies: string[]
  relationships_excluded: string[]
  pack: PackRef
}
export type Override = { entity_id: string; state: string; fields: string[] }
export type ImportRequest = {
  format: 'json' | 'csv'
  content: string
  csv_kind?: 'concepts' | 'relationships'
  pack_id?: string
  base_version?: string
  new_version?: string
}

const base = '/domain-knowledge'
const apiBase =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'
export const getDomains = () =>
  apiGet<{ pack: PackRef; domains: DomainSummary[]; decisions: Decision[]; analysis: Analysis }>(
    `${base}/domains`,
  )
export const getEntities = (domain?: string) =>
  apiGet<EntitySummary[]>(`${base}/entities`, { domain })
export const getEntity = (id: string) =>
  apiGet<EntityDetail>(`${base}/entities/${encodeURIComponent(id)}`)
export const searchConcepts = (q: string) => apiGet<SearchHit[]>(`${base}/search`, { q })
export const getGraph = (focus?: string, domain?: string, depth = 1) =>
  apiGet<GraphView>(`${base}/graph`, { focus, domain, depth })
export const getPath = (source: string, target: string) =>
  apiGet<{ hops: Hop[]; connected: boolean }>(`${base}/path`, { source, target })
export const getImpact = (id: string) => apiGet<Impact>(`${base}/impact/${encodeURIComponent(id)}`)
export const getPacks = () =>
  apiGet<{ versions: VersionMeta[]; active: PackRef[]; writable: boolean }>(`${base}/packs`)
export const comparePack = (id: string, baseVersion: string, target: string) =>
  apiGet<{ changes: Change[]; compatibility: { level: string; message: string } }>(
    `${base}/packs/${encodeURIComponent(id)}/compare`,
    { base: baseVersion, target },
  )
export const getGraphStatus = () => apiGet<GraphStatus>(`${base}/graph-provider`)
export const importDryRun = (body: ImportRequest) => apiPost<DryRun>(`${base}/import/dry-run`, body)
export const importApply = (body: ImportRequest, expected_sha256: string, reason: string) =>
  apiPost<{ proposal: VersionMeta }>(`${base}/import/apply`, { ...body, expected_sha256, reason })
export const transitionVersion = (
  id: string,
  version: string,
  to: VersionMeta['status'],
  reason: string,
) =>
  apiPost<VersionMeta>(
    `${base}/packs/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/transition`,
    { to, reason },
  )
export const suggestKnowledge = (text: string) => apiPost<Suggestion>(`${base}/suggest`, { text })
export const adoptEntities = (definition: ApplicationDefinition, entity_ids: string[]) =>
  apiPost<{ definition: ApplicationDefinition; report: AdoptReport }>(`${base}/adopt`, {
    definition,
    entity_ids,
  })
export const getOverrides = (definition: ApplicationDefinition) =>
  apiPost<{ pack: PackRef; overrides: Override[] }>(`${base}/overrides`, { definition })
export const exportPackUrl = (id: string, version: string) =>
  `${apiBase}${base}/packs/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/export`

// ── Multi-hop traversal, governance permissions, proposal impact ──
export type TraversalHop = {
  from: string
  to: string
  type: string
  forward: boolean
  explanation: string
}
export type TraversalResult = {
  node: { id: string; kind: string; label: string }
  depth: number
  hops: TraversalHop[]
  explanation: string
}
export type Traversal = {
  start: { id: string; kind: string; label: string }
  results: TraversalResult[]
  truncated: boolean
  max_depth: number
  max_results: number
  nodes_expanded: number
}
export type TraverseQuery = {
  start: string
  direction?: 'out' | 'in' | 'both'
  depth?: number
  limit?: number
  kinds?: string
}
export const traverse = (query: TraverseQuery) => apiGet<Traversal>(`${base}/traverse`, query)
export const getDomainPermissions = () =>
  apiGet<{ user_id: string; permissions: string[]; store_writable: boolean }>(`${base}/me`)
export type ProposalImpact = {
  pack_id: string
  version: string
  base_version: string | null
  changes: Change[]
  compatibility: { level: string; message: string; ok: boolean }
  projects: {
    project_id: string
    revision: number
    entities: string[]
    adopted_versions: string[]
    applied: boolean
  }[]
  project_storage: string
  note: string
}
export const getProposalImpact = (id: string, version: string) =>
  apiGet<ProposalImpact>(
    `${base}/packs/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/impact`,
  )
export const adoptWithDependencies = (
  definition: ApplicationDefinition,
  entity_ids: string[],
  include_required: boolean,
) =>
  apiPost<{
    definition: ApplicationDefinition
    report: AdoptReport & { added_as_required_dependency: string[] }
  }>(`${base}/adopt`, { definition, entity_ids, include_required })

// ── Domain-to-application compilation (Design Studio project) ──
export type CompileIssue = {
  code: string
  severity: 'error' | 'warning' | 'info'
  item: string
  message: string
  remediation: string
}
export type CompileCheck = {
  check: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
  items?: { category: string; item: string; text: string; detail: string }[]
}
export type Compilation = {
  package_sha256?: string
  status: 'generated' | 'blocked'
  resolution: {
    packs: {
      pack_id: string
      version: string
      status: string
      active_version: string | null
      entities: string[]
    }[]
    adopted: {
      entity_id: string
      pack_version: string
      item_id: string
      state: string
      overridden_fields: string[]
    }[]
    issues: CompileIssue[]
    unresolved_decisions: { id: string; question: string }[]
  }
  specification: {
    project_revision: number
    compiler_version: string
    references: {
      relationship_id: string
      source: string
      target: string
      field: string
      required: boolean
      enforcement: 'foreign_key' | 'link'
      cardinality: string
    }[]
    collections: { entity: string; lists: string; via: string }[]
    operations: {
      id: string
      kind: string
      entity: string
      permission: string | null
      roles: string[]
    }[]
  }
  plan: { blocked: boolean; reasons: string[] }
  checks: CompileCheck[]
  manifest: {
    compiler_version: string
    generator_version: string
    project_revision: number
    domain_packs: { pack_id: string; version: string }[]
    files: Record<string, { sha256: string; kind: string; sources: string[] }>
  }
  files: Record<string, { kind: string; bytes: number }>
}
const project = (id: string) => `/design-studio/projects/${encodeURIComponent(id)}`
export const compileProject = (id: string, signal?: AbortSignal) =>
  apiGet<Compilation>(`${project(id)}/compile`, {}, signal)
export async function compiledFile(id: string, path: string): Promise<string> {
  const org = getActiveOrganization()
  const response = await fetch(
    `${apiBase}${project(id)}/compile/file?${new URLSearchParams({ path })}`,
    { credentials: 'same-origin', headers: org ? { 'X-Org-Id': org } : {} },
  )
  if (!response.ok) throw new Error('The file could not be loaded.')
  return response.text()
}
export const compiledArchiveUrl = (id: string) =>
  `${apiBase}${project(id)}/compile/archive${getActiveOrganization() ? `?${new URLSearchParams({ org: getActiveOrganization()! })}` : ''}`
export const projectDependencies = (id: string, query: TraverseQuery) =>
  apiGet<Traversal>(`${project(id)}/dependencies`, query)
