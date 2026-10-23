import { ApiError, apiGet, apiPost, setActiveOrganization, getActiveOrganization } from './client'
import { getWorkspace } from './workspace'
import type {
  Analysis,
  ApplicationDefinition,
  ApprovalRecord,
  BusinessDefinition,
  Change,
  KnowledgeDomain,
  WorkflowDefinition,
} from './applicationDefinition'

/** What the server returns: the optional sections of the stored definition are always present. */
export type StudioDefinition = ApplicationDefinition & {
  business: BusinessDefinition
  workflow_definitions: WorkflowDefinition[]
  approvals: ApprovalRecord[]
  revision: number
}

/** Design Studio's voice-first workspace. The server owns the specification; these types describe what it returns. */
export type StageKey =
  'brief' | 'knowledge' | 'workflow' | 'data' | 'screen' | 'rules' | 'roles' | 'checks' | 'export'
export const STAGES: readonly (readonly [StageKey, string])[] = [
  ['brief', 'Requirements'],
  ['knowledge', 'Domain Knowledge'],
  ['workflow', 'Business Process'],
  ['data', 'Data Model'],
  ['screen', 'Screens & UI'],
  ['rules', 'Rules & Logic'],
  ['roles', 'Roles & Permissions'],
  ['checks', 'Validation'],
  ['export', 'Generate Application'],
]
export type StageStatus =
  'not_started' | 'in_progress' | 'needs_input' | 'ready_for_review' | 'completed' | 'blocked'
export const STATUS_LABEL: Record<StageStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  needs_input: 'Needs input',
  ready_for_review: 'Ready for review',
  completed: 'Completed',
  blocked: 'Blocked',
}
export type StageInfo = { status: StageStatus; reason: string; counts: Record<string, number> }
export type OpenQuestion = { id: string; topic: string; text: string }
export type PackInfo = {
  usage?: 'blueprint' | 'source_reference'
  quality?: {
    pack_version: string
    status: string
    configuration_required?: { integration_id: string; status: string; note: string }[]
    counts: { rules: number; executable_rules: number; tasks: number }
    findings: { code: string; item: string; detail: string }[]
  }
  role_names?: string[]
  id: string
  title: string
  description: string
  domain_id: string | null
  version: string
  synthetic: boolean
  adopted: boolean
  counts: Record<string, number>
}
export type DomainMatch = {
  domain_id: string
  name: string
  score: number
  matched_keywords: string[]
  pack_ids: string[]
}
export type ProviderState = {
  capability: string
  enabled: boolean
  provider: string | null
  reason: string
  credential_present: boolean
}
export type CompileSummary = {
  status: 'generated' | 'blocked'
  files: number
  checks_passed: number
  checks_failed: number
  reason: string | null
}
export type ApprovalState = { state: 'none' | 'valid' | 'stale'; record: ApprovalRecord | null }

export type StudioState = {
  intake?: IntakeState | null
  definition: StudioDefinition
  revision: number
  base_sha256: string
  stages: Record<StageKey, StageInfo>
  next: { stage: StageKey; label: string; status: StageStatus; text: string }
  flow?: { active: StageKey; reviewed: StageKey[]; ready: boolean } | null
  questions: OpenQuestion[]
  analysis: { process: Analysis; design: Analysis }
  execution_gaps?: {
    item: string
    category: string
    text: string
    detail: string
    decision: string | null
  }[]
  approval: { process: ApprovalState; design: ApprovalState }
  domain: {
    process_library?: {
      id: string
      pack_id: string
      pack_version: string
      workflow_id: string
      name: string
      family_id?: string | null
      variant?: string
      region?: string
      source_system?: string | null
      domain_id: string | null
      layer: string
      company: string | null
      source: string
      verification: string
      synthetic: boolean
      steps: number
      decisions: number
      exceptions: number
    }[]
    source?: 'local' | 'neo4j'
    matches: DomainMatch[]
    packs: PackInfo[]
    domains: KnowledgeDomain[]
  }
  compile: CompileSummary | null
  assistant: ProviderState
}

export type IntakeState = {
  catalog_version: string
  selected: {
    region: string | null
    industry_id: string | null
    skipped: string[]
    catalog_version: string
  }
  questions: {
    id: 'region' | 'industry'
    text: string
    optional: boolean
    options: { id: string; name: string }[]
  }[]
  coverage: { systems: number; industries: number; regions: number }
  systems: {
    id: string
    name: string
    blueprint_id: string
    blueprint_version: string
    status: string
    source: { kind: string; reference: string; verification: string }
    variants: { id: string; name: string; design_guidance: string; status: string }[]
    processes: {
      workflow_id: string
      name: string
      activities: { id: string; name: string; role_id: string | null }[]
    }[]
  }[]
  regional_guidance: {
    id: string
    name: string
    guidance: string[]
    sources: { title: string; url: string; checked_on: string | null; scope: string }[]
  } | null
  note: string
}

export type AppliedChange = {
  area: string
  kind: 'added' | 'changed' | 'removed' | 'note'
  item_id: string
  summary: string
}
export type Proposal = {
  id: string
  summary: string
  changes: AppliedChange[]
  actions: Record<string, unknown>[]
  base_sha256: string
  candidate_sha256: string
  reasons: string[]
  approvals_made_stale: string[]
  validation: {
    before: { error: number; warning: number; info: number }
    after: { error: number; warning: number; info: number }
  }
  diff: Change[]
}
export type Generation = {
  state: string
  message: string
  focus?: StageKey
  client_action?: 'compile' | 'frontend' | 'continue'
}
export type Turn = {
  mode: 'language_model' | 'local_rules' | 'direct'
  degraded: string | null
  reply: string
  applied: AppliedChange[]
  previous_revision: number
  revision: number
  approvals_made_stale: string[]
  proposal: Proposal | null
  rejected: { type: string; reason: string }[]
  asked_question_id: string | null
  focus: StageKey | null
  focus_item: string | null
  generation: Generation | null
  client_action: 'compile' | 'frontend' | 'continue' | null
  input_mode: 'text' | 'voice'
  /** What the saved change means: applied to the specification, not yet generated or tested, recorded but not executable. From the server, never the model. */
  notes?: string[]
}
export type TurnResult = { turn: Turn; state: StudioState }
export type HistoryItem = { role: 'user' | 'assistant'; text: string }

/** The workspace page has no site navigation, which is what normally tells the API client which organization the person works in. This does the same, once. */
let organization: Promise<void> | null = null
export const ensureOrganization = (): Promise<void> =>
  (organization ??= getWorkspace(null, undefined, true).then(
    (result) => setActiveOrganization(result.active_organization),
    () => undefined,
  ))
/** Forget it when the person signs out, so the next person is not placed in the previous person's organization. */
export const forgetOrganization = (): void => {
  organization = null
}

/** What the signed-in person may do in one project, and why not where they may not. Computed by the server; the interface only displays it. */
export type StudioAccess = {
  organization: string | null
  studio_roles: string[]
  studio_role_labels: string[]
  org_roles: string[]
  project_capabilities: string[]
  creator: boolean
  policy: 'assigned' | 'org' | null
  can: {
    edit: boolean
    generate: boolean
    review: boolean
    approve: boolean
    launch: boolean
    manage_access: boolean
  }
  denied: Partial<Record<keyof StudioAccess['can'], string>>
}
export const getStudioAccess = (id: string, signal?: AbortSignal) =>
  apiGet<StudioAccess>(
    `/design-studio/projects/${encodeURIComponent(id)}/studio/access`,
    {},
    signal,
  )

const root = (id: string) => `/design-studio/projects/${encodeURIComponent(id)}/studio`

export const getStudioState = (id: string, compile = false, signal?: AbortSignal) =>
  apiGet<StudioState>(`${root(id)}/state`, compile ? { compile: true } : {}, signal)
export const studioTurn = (
  id: string,
  body: {
    guided?: boolean
    stage?: StageKey
    message: string
    expected_revision: number
    history: HistoryItem[]
    asked_question_id: string | null
    selected: string | null
    input_mode: 'text' | 'voice'
  },
  signal?: AbortSignal,
) => apiPost<TurnResult>(`${root(id)}/turn`, body, signal)
export const studioAct = (
  id: string,
  expected_revision: number,
  actions: Record<string, unknown>[],
  reply = '',
) => apiPost<TurnResult>(`${root(id)}/act`, { expected_revision, actions, reply })
export const studioApply = (id: string, proposal: Proposal, expected_revision: number) =>
  apiPost<{
    changes: AppliedChange[]
    previous_revision: number
    approvals_made_stale: string[]
    notes?: string[]
    state: StudioState
  }>(`${root(id)}/apply`, {
    expected_revision,
    base_sha256: proposal.base_sha256,
    candidate_sha256: proposal.candidate_sha256,
    actions: proposal.actions,
  })
export const studioRevert = (id: string, expected_revision: number, to_revision: number) =>
  apiPost<{ state: StudioState; restored_from: number }>(`${root(id)}/revert`, {
    expected_revision,
    to_revision,
  })

/** Settle every validation finding whose fix follows from the design itself. No language model; no policy is decided. */
export const studioResolve = (id: string, expected_revision: number) =>
  apiPost<{ state: StudioState; changes: string[]; stale: string[] }>(`${root(id)}/resolve`, {
    expected_revision,
  })

/** Where the "Open live demo" link points: it signs a link (valid for a week) to this project's live demo and redirects to it. */
export const liveDemoUrl = (id: string) =>
  `${base()}/design-studio/projects/${encodeURIComponent(id)}/live-demo`

// ── voice ──
export type VoiceStatus = { assistant: ProviderState; speech: ProviderState }
export const getVoiceStatus = (signal?: AbortSignal) =>
  apiGet<VoiceStatus>('/design-studio/voice/status', {}, signal)

const base = () =>
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

async function fail(response: Response, fallback: string): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as {
    error?: { code?: string; message?: string }
  } | null
  return new ApiError(
    response.status,
    body?.error?.code ?? 'error',
    body?.error?.message ?? fallback,
  )
}

/** The recording leaves the browser once, to be transcribed, and is not kept. The text is shown to the person before it is used. */
export async function transcribeAudio(
  audio: Blob,
  signal?: AbortSignal,
): Promise<{ text: string; confidence: number | null }> {
  let response: Response
  try {
    response = await fetch(`${base()}/design-studio/voice/transcribe`, {
      method: 'POST',
      credentials: 'same-origin',
      signal,
      headers: { 'Content-Type': audio.type || 'audio/webm' },
      body: audio,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'network', 'The speech service could not be reached. Type instead.')
  }
  if (!response.ok) throw await fail(response, 'Speech recognition failed. Type instead.')
  return response.json() as Promise<{ text: string; confidence: number | null }>
}

export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
  let response: Response
  try {
    response = await fetch(`${base()}/design-studio/voice/speak`, {
      method: 'POST',
      credentials: 'same-origin',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'network', 'The speech service could not be reached.')
  }
  if (!response.ok) throw await fail(response, 'The reply could not be spoken.')
  return response.blob()
}

// ── the generated application, run on this computer ──
export type RuntimeStatus = {
  running: boolean
  available?: boolean
  reason?: string
  url?: string
  port?: number
  revision?: number
  stale?: boolean
  started_seconds_ago?: number
}
export type RuntimeTest = {
  release_id?: string
  run_id?: string
  revision: number
  passed: boolean
  ran: number
  passed_count?: number
  failed_count?: number
  skipped_count?: number
  seconds: number
  cases: string[]
  output_tail: string
  output?: string
  output_truncated?: boolean
}
export type StudioRelease = {
  id: string
  revision: number
  created: string
  archive_sha256: string
  actor: string
  tests: { id: string; status: string; started: string; result: RuntimeTest | null }[]
}
const releasesRoot = (id: string) => `/design-studio/projects/${encodeURIComponent(id)}/releases`
export const getReleases = (id: string, signal?: AbortSignal) =>
  apiGet<StudioRelease[]>(releasesRoot(id), {}, signal)
export const retainRelease = (id: string, expected_revision: number) =>
  apiPost<StudioRelease>(releasesRoot(id), { expected_revision })
export const releaseArchiveUrl = (id: string, release: string) =>
  `${(import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'}${releasesRoot(id)}/${encodeURIComponent(release)}/archive${getActiveOrganization() ? `?${new URLSearchParams({ org: getActiveOrganization()! })}` : ''}`
const runtime = (id: string) => `/design-studio/projects/${encodeURIComponent(id)}/runtime`
export const getRuntime = (id: string, signal?: AbortSignal) =>
  apiGet<RuntimeStatus>(runtime(id), {}, signal)
export const testRuntime = (id: string) => apiPost<RuntimeTest>(`${runtime(id)}/test`, {})
export const launchRuntime = (id: string) => apiPost<RuntimeStatus>(`${runtime(id)}/launch`, {})
export const stopRuntime = (id: string) => apiPost<{ stopped: boolean }>(`${runtime(id)}/stop`, {})

export const continueStudio = (id: string, expected_revision: number, stage: StageKey) =>
  apiPost<TurnResult>(`${root(id)}/continue`, { expected_revision, stage })

export const startGuidedStudio = (id: string, expected_revision: number) =>
  apiPost<StudioState>(`${root(id)}/start-guided`, { expected_revision })
