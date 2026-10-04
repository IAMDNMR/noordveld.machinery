import { apiGet, apiPost } from './client'
import type { PartSummary } from './types'

/** Response shapes of the Agentic Shopping API (backend/app/schemas/agent.py). Every value comes from the graph. */
export type AgentStepKey = 'request' | 'understand' | 'machine' | 'part' | 'fitment' | 'availability' | 'fulfilment' | 'compare' | 'recommend'
export type AgentState = 'recommendation' | 'need_part' | 'need_machine' | 'choose_machine' | 'choose_type' | 'need_detail' | 'no_match' | 'out_of_scope'

export interface AgentStep {
  key: AgentStepKey
  label: string
  status: 'done' | 'blocked' | 'skipped'
  message: string
}

export interface AgentEvidence {
  key: 'fit' | 'verified' | 'budget' | 'availability' | 'inventory' | 'supplier' | 'delivery' | 'ranking'
  ok: boolean
  label: string
  detail: string
  data_class: string | null
}

export interface AgentCandidate {
  part: PartSummary
  recommended: boolean
  availability_label: string
  fitment_status: string | null
  fitment_label: string
  inventory: string
  stock_locations: { warehouse: string; city: string | null; available: number }[]
  fulfilment: string
  delivery: string
  supplier_label: string
  suppliers: { name: string; lead_time_days: number | null; primary: boolean }[]
  price_basis: string | null
  order_action: 'add_to_cart' | 'identify' | 'unavailable'
  order_note: string | null
  supplier: string | null
  supplier_lead_days: number | null
  fulfilment_days: number | null
  within_budget: boolean | null
  tradeoffs: string[]
  can_add_to_cart: boolean
}

export interface AgentInterpretation {
  machine: string | null
  part_type: string | null
  preference: 'cheapest' | 'fastest' | 'none'
  delivery_place: string | null
  quantity: number | null
  budget_max: number | null
  budget_currency: string | null
  availability: 'require' | 'prefer' | 'none'
}

export interface AgentResponse {
  request: string
  state: AgentState
  interpretation: AgentInterpretation
  steps: AgentStep[]
  question: string | null
  options: { label: string; refine: string }[]
  candidates: AgentCandidate[]
  recommended: string | null
  reason: string | null
  evidence: AgentEvidence[]
  comparison: string | null
  excluded: { part_number: string; name: string; status_label: string }[]
  delivery: { city: string; warehouse: string; warehouse_city: string | null; standard_days: number | null; express_days: number | null } | null
  /** what the choice was made on: hard requirements, ranking priorities in order, and the outcome in one line */
  decision: { requirements: string[]; priorities: string[]; summary: string } | null
  why: { title: string; detail: string }[]
  how_we_know: { label: string; value: string }[]
  notes: string[]
  disclaimer: string
}

export const askAgent = (request: string, signal?: AbortSignal): Promise<AgentResponse> => apiPost<AgentResponse>('/agent/recommend', { request }, signal)

/** The agent's steps in order, defined by the backend so the interface never invents one. */
export const getAgentPipeline = (signal?: AbortSignal): Promise<{ key: AgentStepKey; label: string }[]> => apiGet<{ key: AgentStepKey; label: string }[]>('/agent/pipeline', {}, signal)

export interface AgentSuggestion {
  request: string
  need: string
  context: string
  action: string
}

export const getAgentSuggestions = (signal?: AbortSignal): Promise<AgentSuggestion[]> => apiGet<AgentSuggestion[]>('/agent/suggestions', {}, signal)
