import { apiPost } from './client'

/**
 * The Commerce APIs (backend/app/api/routes/commerce.py). Every decision, fact and piece of evidence on the commerce workspace comes from these responses; the browser
 * decides nothing about fitment, stock, a shipment's state or warranty. A refusal is an ApiError: 401 not signed in, 403 not allowed (the same for a record that does not
 * exist and for one that belongs to someone else), 422 a malformed request.
 */
export type Domain = 'DISCOVERY' | 'LOGISTICS' | 'WARRANTY'
export type ViewRole = 'OEM' | 'DEALER' | 'END_CUSTOMER'

export interface Scope {
  user_role?: ViewRole
  dealer_id?: string
}

export interface DataRef {
  entity: string
  id: string | null
  data_status: string | null
  source_type?: string | null
  source_record_id?: string | null
}

export interface EvidenceItem {
  fact: string
  entity: string
  id: string | null
  data_status: string | null
  domain?: Domain
}

export interface PathStep {
  step: number
  entity: string
  id: string | null
  relation_to_next: string | null
  data_status: string | null
}

export interface Decision {
  status: string
  decision: string
  summary: string
  facts: Record<string, unknown>
  reasons: string[]
  evidence: EvidenceItem[]
  source_records: DataRef[]
  missing: string[]
  warnings: string[]
  recommended_next_action: string | null
}

export interface Confidence {
  level: string
  data_status: string
  fact_verified: boolean
  real_world_verified: boolean
  basis: string
}

export interface CommerceContext {
  context_id: string
  context_type: Domain
  generated_at: string
  data_status: string
  source_records: DataRef[]
  evidence: EvidenceItem[]
  confidence: Confidence
  missing: string[]
  warnings: string[]
  decision: Decision
  evidence_path: PathStep[]
  visibility: { role: string; hidden_fields: string[] }
}

export interface PartRow {
  part_id: string
  part_number: string
  name: string
  product_match_status?: string
  fitment?: string
  approved_source?: boolean
  availability?: string
  total_available?: number | null
  price?: { state: string; unit_price?: number; currency?: string; price_status?: string } | null
}

export interface RankingRow {
  rank: number
  part_id: string
  part_number: string
  total_score: number
  components: Record<string, number | null>
  explanation?: { lines: string[] }
}

export interface Clarification {
  question: string
  options: Record<string, unknown>[]
}

export interface DiscoveryContext extends CommerceContext {
  user_request: string
  machine: { resolution: string; machine_id?: string; model?: string; name?: string } | null
  candidate_parts: { part_id: string; part_number: string; name: string; semantic_match?: { status: string }; flags?: Record<string, unknown> }[]
  availability: { part_id: string; state: string; total_available: number | null; warehouses?: unknown[] }[]
  recommended_part: PartRow | null
  compatible_part: PartRow | null
  alternatives: PartRow[]
  ranking: RankingRow[]
  rejection_reasons: Record<string, { code: string; detail: string }[]>
  clarification: Clarification | null
}

/** "Which machine uses this part?" and "Where did this part come from?": one part, read from the fitment and approved-source records. */
export interface PartLookupContext extends CommerceContext {
  lookup: 'PART_FITMENT' | 'PART_ORIGIN'
  part: { part_id: string; part_number: string; name: string } | null
  machines: { machine_id: string; model: string; name: string; fitment_id: string; fitment_rule: string | null }[]
  other_fitments: { model: string; approval_status: string }[]
  sources: { approved_source_id: string; source_id: string; source_kind: string }[]
  catalogue: { manufacturer: string | null; oem_status: string | null; catalogue_status: string | null; data_status: string | null } | null
}

export const isLookup = (c: DiscoveryContext | PartLookupContext): c is PartLookupContext => 'lookup' in c

export interface ShipmentLine {
  order_line_id: string
  part_id: string | null
  part_number: string | null
  name: string | null
  quantity: number | null
}

export interface Leg {
  sequence: number
  transport_mode: string | null
  planned_transit_days: number | null
  origin_location_id?: string | null
  destination_location_id?: string | null
}

export interface RouteOption {
  route_id: string
  transport_mode: string
  planned_transit_days: number | null
  estimated_cost: number | null
  currency: string | null
  days_vs_current?: number | null
  is_current?: boolean
}

export interface LogisticsContext extends CommerceContext {
  order: { order_id: string; status?: string; order_date?: string | null } | null
  order_lines: { order_line_id: string; part_number: string | null; name: string | null; quantity: number | null }[]
  shipment: { shipment_id: string; order_id?: string | null; status?: string; carrier?: string | null; remediation_flags?: string[] } | null
  part: { part_id: string; part_number: string; name: string; quantity?: number } | null
  shipment_lines: ShipmentLine[]
  parts: { part_id: string; part_number: string; name: string }[]
  shipment_kind: 'SINGLE_LINE' | 'MULTI_LINE' | 'NO_LINE_RECORDED' | null
  order_shipments: string[]
  order_split: boolean
  current_status: string | null
  route: { route_id: string; transport_mode: string | null; planned_transit_days: number | null } | null
  route_legs: Leg[]
  completed_legs: Leg[]
  remaining_legs: Leg[]
  planned_eta: { planned_eta: string | null; actual_eta: string | null; days_to_eta: number | null; delivered: boolean } | null
  transport_comparison: { options: RouteOption[] } | null
  tracking_events: { tracking_event_id: string; timestamp: string; event_type: string; location_text?: string | null; description?: string | null }[]
  route_resolution_status: string | null
  requires_review: boolean
  clarification: Clarification | null
}

export interface Factor {
  code: string
  label: string
  status: 'PASS' | 'FAIL' | 'UNKNOWN'
  detail: string
}

export interface WarrantyContext extends CommerceContext {
  machine: { machine_instance_id: string; serial_number?: string } | null
  current_part: { part_id: string; part_number: string; name: string } | null
  installation: { installation_id: string; installation_date: string; validation_status?: string; validation_issues?: string[] } | null
  dealer: { dealer_id: string; name: string; authorized_status?: string } | null
  technician: { technician_id: string; name?: string; certification?: string; specialization?: string } | null
  work_order: { work_order_id: string; service_type?: string; service_date?: string } | null
  coverage_start: string | null
  coverage_end: string | null
  replacement_history: { replacement_id: string; replacement_date: string; reason?: string | null }[]
  prior_claims: { claim_id: string; status: string; claim_date: string }[]
  claim: { claim_id: string; status: string; failure_date?: string } | null
  decision_factors: Factor[]
}

export interface AgentSection {
  domain: Domain
  title: string
  status: string
  decision: string
  headline: string
  lines: string[]
  notes: string[]
}

export interface AgentState {
  shipment_id?: string
  order_id?: string
  claim_id?: string
  machine_instance_id?: string
  part_id?: string
  machine_id?: string
  machine_model?: string
  part_number?: string
  last_request?: string
  last_domains?: Domain[]
  pending_message?: string
}

export interface AgentResponse {
  intent: 'DISCOVERY' | 'LOGISTICS' | 'WARRANTY' | 'MULTI_DOMAIN' | 'CLARIFICATION' | 'UNKNOWN'
  status: 'ANSWERED' | 'PARTIAL' | 'REQUIRES_CLARIFICATION' | 'OUT_OF_SCOPE'
  answer: {
    text: string
    lead: string
    sections: AgentSection[]
    synthetic_notice: string | null
    grounding: { mode: 'TEMPLATE' | 'LLM'; validated: boolean; note?: string }
  }
  steps: { domain: Domain; status: string; decision: string; summary: string; resolution: string[] }[]
  contexts: { DISCOVERY?: DiscoveryContext | PartLookupContext; LOGISTICS?: LogisticsContext; WARRANTY?: WarrantyContext }
  clarification: { domain: Domain | null; question: string; options: Record<string, unknown>[] } | null
  evidence: EvidenceItem[]
  evidence_paths: Partial<Record<Domain, PathStep[]>>
  source_records: DataRef[]
  data_status: string
  confidence: Partial<Record<Domain, Confidence>>
  visibility: Partial<Record<Domain, { role: string; hidden_fields: string[] }>>
  warnings: string[]
  missing: string[]
  state: AgentState
  understanding: { intent: string; domains: Domain[]; source: string; focus: string[]; references: Record<string, string>; reasons: string[] }
}

export const askCommerceAgent = (message: string, state: AgentState, scope: Scope = {}, signal?: AbortSignal): Promise<AgentResponse> =>
  apiPost<AgentResponse>('/commerce/agent', { message, state, ...scope }, signal)
