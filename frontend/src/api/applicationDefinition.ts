import { ApiError, apiGet, apiPost, apiPut } from './client'

/** Versioned, inert application definition. The backend schema is authoritative on save/export. */
export type ComponentKind = 'container' | 'text' | 'field' | 'table' | 'button'
export type GridSettings = { mode: 'stack' | 'grid'; columns: number }
export type ResponsiveLayout = { mobile: GridSettings; tablet: GridSettings; desktop: GridSettings }
export type Placement = { span: number }
export type Binding = { source: 'fixture' | 'state'; dataset: string; field: string } | null
export type Event = {
  trigger: 'click' | 'change'
  action: 'set_state' | 'navigate'
  target: string
  value?: string | null
}
/** Where a screen or component came from: its process step, requirements and business items. */
export type Trace = {
  generated?: boolean
  workflow_id?: string | null
  step_id?: string | null
  requirement_ids?: string[]
  entity_id?: string | null
  attribute_id?: string | null
  relationship_id?: string | null
  rule_id?: string | null
  exception_id?: string | null
  source_sha256?: string | null
}
export type ContainerNode = {
  kind: 'container'
  id: string
  props: { title: string; layout: ResponsiveLayout }
  placement: Placement
  children: ComponentNode[]
  trace?: Trace
}
export type TextNode = {
  kind: 'text'
  id: string
  props: { content: string }
  placement: Placement
  binding: Binding
  events: []
  trace?: Trace
}
export type FieldNode = {
  kind: 'field'
  id: string
  props: {
    field_type: 'text' | 'number' | 'email' | 'telephone' | 'date' | 'select' | 'checkbox' | 'file'
    label: string
    help_text: string | null
    options: string[]
    validations: {
      kind: 'required' | 'email' | 'min_length' | 'max_length' | 'pattern' | 'minimum' | 'maximum'
      value: string | number | boolean | null
      message?: string | null
    }[]
  }
  placement: Placement
  binding: Binding
  events: Event[]
  trace?: Trace
}
export type TableNode = {
  kind: 'table'
  id: string
  props: {
    title: string
    columns: { id: string; label: string }[]
    searchable: boolean
    filters: string[]
    page_size: number
  }
  placement: Placement
  binding: Binding
  events: []
  trace?: Trace
}
export type ButtonNode = {
  kind: 'button'
  id: string
  props: { label: string }
  placement: Placement
  binding: null
  events: Event[]
  trace?: Trace
}
export type ComponentNode = ContainerNode | TextNode | FieldNode | TableNode | ButtonNode
export type ScreenDefinition = {
  id: string
  title: string
  components: ComponentNode[]
  trace?: Trace
}

export type StepKind =
  'start' | 'form' | 'search' | 'review' | 'approval' | 'branch' | 'action' | 'exception' | 'end'
export type WorkflowState = {
  id: string
  label: string
  kind: StepKind
  outputs: string[]
  outcome?: 'success' | 'failure' | 'cancelled' | null
  role_id?: string | null
  permission?: string | null
  requirement_ids?: string[]
  reads_entity_ids?: string[]
  writes_entity_ids?: string[]
  rule_ids?: string[]
  exception_ids?: string[]
  input_fields?: Record<string, string[]> | null
  input_relationships?: Record<string, string[]> | null
  preconditions?: string[]
  postconditions?: string[]
}
export type WorkflowTransition = {
  id: string
  source: string
  target: string
  condition: {
    kind: 'always' | 'equals' | 'not_equals'
    field: string | null
    value: string | number | boolean | null
  }
}
export type WorkflowDefinition = {
  version: 1
  id: string
  name: string
  states: WorkflowState[]
  transitions: WorkflowTransition[]
}

export type KnowledgeOrigin = { pack_id: string; pack_version: string; item_id: string }
export type BusinessBrief = {
  goal: string
  problem: string
  domain_id: string | null
  subdomain: string
  capability: string
  purpose: string
  user_types: string[]
  outcomes: string[]
  constraints: string[]
  dependencies: string[]
}
export type RequirementCategory =
  | 'security'
  | 'usability'
  | 'performance'
  | 'accessibility'
  | 'auditability'
  | 'reliability'
  | 'compliance'
  | 'other'
export type Requirement = {
  id: string
  statement: string
  kind?: 'functional' | 'non_functional'
  category?: RequirementCategory | null
  priority: 'must' | 'should' | 'could' | 'wont'
  status: 'draft' | 'agreed' | 'deferred' | 'rejected'
  acceptance_criteria: { id: string; statement: string }[]
  deferral_reason?: string
  origin?: KnowledgeOrigin | null
}
export type BusinessRole = {
  id: string
  name: string
  responsibilities: string[]
  permissions: string[]
  approval_authority?: string[]
  origin?: KnowledgeOrigin | null
}
export type AttributeType = 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime'
export type ValueSource = 'user_entered' | 'system_generated' | 'calculated' | 'imported'
export type AttributeFormat =
  'email' | 'phone' | 'url' | 'postal_code' | 'currency_amount' | 'percentage'
export type Sensitivity = 'public' | 'internal' | 'personal' | 'confidential'
export type EntityAttribute = {
  id: string
  name: string
  type: AttributeType
  required?: boolean
  key?: boolean
  allow_unknown?: boolean
  description?: string
  validations?: FieldNode['props']['validations']
  /** Anything but user_entered is system-managed: shown read-only, never an input. */
  value_source?: ValueSource
  writable?: boolean
  default?: string | number | boolean | null
  format?: AttributeFormat | null
  minimum?: number | null
  maximum?: number | null
  min_length?: number | null
  max_length?: number | null
  pattern?: 'digits' | 'letters' | 'alphanumeric' | null
  enum?: string[]
  sensitivity?: Sensitivity
  owner_role_id?: string | null
  reference?: { entity_id: string; attribute_id: string } | null
}
export type Cardinality = 'one_to_one' | 'one_to_many' | 'many_to_one' | 'many_to_many'
export type EntityRelationship = {
  id: string
  name: string
  target: string
  cardinality: Cardinality
  required?: boolean
}
export type BusinessEntity = {
  id: string
  name: string
  description?: string
  owner_role_id?: string | null
  source_system?: string
  attributes: EntityAttribute[]
  relationships: EntityRelationship[]
  origin?: KnowledgeOrigin | null
}
export type RuleSourceKind =
  | 'business_owner'
  | 'implemented_code'
  | 'document'
  | 'graph_data'
  | 'workshop'
  | 'synthetic_assumption'
export type BusinessRule = {
  execution?: {
    kind: 'compare' | 'value'
    field: string
    operator?: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'present'
    other_field?: string | null
    value?: string | number | boolean | null
    pass_outcome?: string | null
    fail_outcome?: string | null
  } | null
  id: string
  description: string
  type?: 'validation' | 'decision' | 'calculation' | 'policy'
  status: 'confirmed' | 'assumption'
  source: { kind: RuleSourceKind; reference: string }
  condition?: string
  outcomes?: string[]
  origin?: KnowledgeOrigin | null
}
export type ExceptionScenario = {
  id: string
  name: string
  trigger: string
  recovery: string
  resolution?: 'recover' | 'terminate' | 'escalate' | null
  resolution_state_id?: string | null
  origin?: KnowledgeOrigin | null
}
export type BusinessDecision = {
  id: string
  question: string
  status: 'open' | 'decided' | 'deferred'
  answer?: string
  deferral_reason?: string
  affects?: string[]
  origin?: KnowledgeOrigin | null
}
export type Integration = {
  id: string
  name: string
  system: string
  direction: 'inbound' | 'outbound' | 'bidirectional'
  events: string[]
  entity_ids: string[]
  failure_handling?: string
  contract_status?: 'defined' | 'deferred'
  origin?: KnowledgeOrigin | null
}
export type Term = { id: string; term: string; definition: string; origin?: KnowledgeOrigin | null }
export type DiscoveryQuestion = {
  id: string
  topic: string
  text: string
  answer: string
  status: 'open' | 'answered' | 'not_applicable'
}
export type BusinessDefinition = {
  brief: BusinessBrief
  requirements: Requirement[]
  roles: BusinessRole[]
  entities: BusinessEntity[]
  rules: BusinessRule[]
  exceptions: ExceptionScenario[]
  decisions: BusinessDecision[]
  integrations: Integration[]
  terms: Term[]
  questions: DiscoveryQuestion[]
  knowledge: { pack_id: string; pack_version: string }[]
}
export type ApprovalRecord = {
  scope: 'process' | 'design'
  revision: number
  content_sha256: string
  approved_by: string
  approved_at: string
  warnings_acknowledged: string[]
  comment?: string
}

export type ApplicationDefinition = {
  frontend_required?: boolean
  /** The application template this project was configured against. */
  template?: { template_id: string; version: string; selected_at: string }
  generated_frontend?: {
    version: number
    design_summary: string
    pages: {
      id: string
      title: string
      purpose: string
      step_ids: string[]
      entity_ids: string[]
      surface_ids?: string[]
    }[]
    files: Record<string, string>
    input_sha256: string
    source_sha256: string
    provider: string
    generated_at: string
    bundle_js: string
    bundle_css: string
    checks: string[]
  } | null
  project_lifecycle?: {
    status: 'active' | 'archived' | 'trashed'
    restore_status: 'active' | 'archived'
  } | null
  studio_flow?: { reviewed: string[]; reviewed_digests?: Record<string, string> } | null
  version: 2
  id: string
  metadata: {
    name: string
    description: string
    purpose: string
    domain: 'finance' | 'crm' | 'inventory' | 'logistics' | 'manufacturing' | 'other'
  }
  screens: ScreenDefinition[]
  theme: {
    primary: string
    background: string
    surface: string
    text: string
    font: 'inter' | 'system' | 'serif'
    logo: null | { asset_id: string }
    /** Parts of the generated screens that were hidden on request; absent or empty means everything is shown. */
    hidden_sections?: ('stats' | 'pipelines' | 'steps' | 'exceptions' | 'records' | 'finished')[]
  }
  fixtures: {
    id: string
    fields: { id: string; type: 'string' | 'number' | 'boolean' }[]
    rows: Record<string, string | number | boolean | null>[]
  }[]
  local_state: {
    id: string
    type: 'string' | 'number' | 'boolean'
    initial: string | number | boolean
  }[]
  navigation?: { screen_id: string; label: string }[]
  workflows?: string[]
  workflow_definitions?: WorkflowDefinition[]
  business?: BusinessDefinition
  /** Written only by the server's approve endpoint. */
  approvals?: ApprovalRecord[]
  revision?: number
}

export type FindingCategory = 'defect' | 'business_decision' | 'assumption' | 'information'
export type Finding = {
  id: string
  code: string
  severity: 'error' | 'warning' | 'info'
  category: FindingCategory
  artefacts: string[]
  message: string
  remediation: string
  rationale: string
  tab: string
}
export type Change = {
  area: string
  item_id: string
  change: 'added' | 'removed' | 'changed'
  fields?: string[]
}
export type AuditEntry = { revision: number; actor: string; operation: string; at: string }
export type ApprovalChanges = Partial<
  Record<
    'process' | 'design',
    { approved_revision: number; state: 'valid' | 'stale' | 'none'; changes: Change[] }
  >
>
export type ArtifactCatalogue = {
  files: { path: string; kind: string; note: string; generated: boolean }[]
  unsupported: { artifact: string; status: string; reason: string }[]
  validation: Record<string, unknown>
}
export type Analysis = {
  scope: 'process' | 'design'
  findings: Finding[]
  counts: { error: number; warning: number; info: number }
  blocking: boolean
}
export type ApprovalState = { state: 'none' | 'valid' | 'stale'; record: ApprovalRecord | null }
export type ProjectAnalysis = {
  revision: number
  process: Analysis
  design: Analysis
  approval: { process: ApprovalState; design: ApprovalState }
}
export type PackSummary = {
  id: string
  version: string
  layer: 'reusable' | 'business'
  title: string
  description: string
  synthetic: boolean
  domain_id: string | null
  depends_on: string[]
  counts: Record<string, number>
}
export type DomainSuggestion = {
  domain_id: string
  name: string
  score: number
  matched_keywords: string[]
  pack_ids: string[]
}
export type KnowledgeDomain = { id: string; name: string; subdomains: string[]; keywords: string[] }
export type Traceability = {
  revision: number
  requirements: {
    id: string
    statement: string
    status: string
    priority: string
    steps: { workflow_id: string; step_id: string }[]
    screens: string[]
    components: string[]
    covered_by_process: boolean
    covered_by_screens: boolean
  }[]
  covered_requirements: string[]
  requirements_without_process: string[]
  requirements_without_screens: string[]
  steps_without_screens: string[]
  screens_without_trace: { screen_id: string; title: string }[]
  handoffs: {
    workflow_id: string
    from_step: string
    to_step: string
    from_role: string
    to_role: string
    requires_authorisation: string | null
  }[]
  assumption_rules: { id: string; description: string; source: string }[]
  unresolved_decisions: { id: string; question: string; status: string; deferral_reason: string }[]
}
export type Impact = {
  item_id: string
  kind: string
  steps: string[]
  screens: string[]
  components: string[]
  related_items: string[]
  artefacts: string[]
  approvals_invalidated_by_change: string[]
}

export const listProjects = () => apiGet<ApplicationDefinition[]>('/design-studio/projects')
export const getProject = (id: string) =>
  apiGet<ApplicationDefinition>(`/design-studio/projects/${encodeURIComponent(id)}`)
export const getProjectHistory = (id: string) =>
  apiGet<ApplicationDefinition[]>(`/design-studio/projects/${encodeURIComponent(id)}/history`)
export const createProject = (definition: ApplicationDefinition) =>
  apiPost<ApplicationDefinition>('/design-studio/projects', definition)
export const updateProject = (definition: ApplicationDefinition, expected_revision: number) =>
  apiPut<ApplicationDefinition>(`/design-studio/projects/${encodeURIComponent(definition.id)}`, {
    expected_revision,
    definition,
  })

export const listPacks = () => apiGet<PackSummary[]>('/design-studio/knowledge/packs')
export const listKnowledgeDomains = () =>
  apiGet<KnowledgeDomain[]>('/design-studio/knowledge/domains')
export const applyPack = (definition: ApplicationDefinition, pack_id: string) =>
  apiPost<{ definition: ApplicationDefinition; added: Record<string, number> }>(
    '/design-studio/knowledge/apply',
    { definition, pack_id },
  )
export const runDiscovery = (definition: ApplicationDefinition, brief_text?: string) =>
  apiPost<{
    definition: ApplicationDefinition
    domain_suggestions: DomainSuggestion[]
    mode: string
  }>('/design-studio/discovery', { definition, brief_text })
export const analyzeDefinition = (definition: ApplicationDefinition) =>
  apiPost<{ process: Analysis; design: Analysis; traceability: Omit<Traceability, 'revision'> }>(
    '/design-studio/application-definition/analyze',
    definition,
  )
export const getProjectAnalysis = (id: string) =>
  apiGet<ProjectAnalysis>(`/design-studio/projects/${encodeURIComponent(id)}/analysis`)
export const approveProject = (
  id: string,
  expected_revision: number,
  scope: 'process' | 'design',
  acknowledged_warnings: string[],
  comment = '',
) =>
  apiPost<ApplicationDefinition>(`/design-studio/projects/${encodeURIComponent(id)}/approve`, {
    expected_revision,
    scope,
    acknowledged_warnings,
    comment,
  })
export const getAudit = (id: string) =>
  apiGet<AuditEntry[]>(`/design-studio/projects/${encodeURIComponent(id)}/audit`)
export const compareRevisions = (id: string, base: number, target: number) =>
  apiGet<{ base: number; target: number; changes: Change[] }>(
    `/design-studio/projects/${encodeURIComponent(id)}/compare`,
    { base, target },
  )
export const getApprovalChanges = (id: string) =>
  apiGet<ApprovalChanges>(`/design-studio/projects/${encodeURIComponent(id)}/approval-changes`)
export const getArtifacts = (id: string) =>
  apiGet<{ catalogue: ArtifactCatalogue | null; manifest: Record<string, unknown> }>(
    `/design-studio/projects/${encodeURIComponent(id)}/artifacts`,
  )
export const getTraceability = (id: string) =>
  apiGet<Traceability>(`/design-studio/projects/${encodeURIComponent(id)}/traceability`)
export const getImpact = (id: string, itemId: string) =>
  apiGet<Impact>(
    `/design-studio/projects/${encodeURIComponent(id)}/impact/${encodeURIComponent(itemId)}`,
  )

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const base = () =>
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

async function failure(response: Response, fallback: string): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as {
    error?: { code?: string; message?: string }
  } | null
  return new ApiError(
    response.status,
    body?.error?.code ?? 'error',
    body?.error?.message ?? fallback,
  )
}

export async function exportApplicationDefinition(
  definition: ApplicationDefinition,
): Promise<void> {
  const response = await fetch(`${base()}/design-studio/application-definition/export`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(definition),
  })
  if (!response.ok) throw await failure(response, 'Review-only export is unavailable')
  download(await response.blob(), 'noordveld-application-mockup.zip')
}

/** Business-aware designs export only from the saved, approved project; the server enforces it. */
export async function exportProject(id: string): Promise<void> {
  const response = await fetch(
    `${base()}/design-studio/projects/${encodeURIComponent(id)}/export`,
    { credentials: 'same-origin' },
  )
  if (!response.ok) throw await failure(response, 'Export failed.')
  download(await response.blob(), 'noordveld-application.zip')
}
