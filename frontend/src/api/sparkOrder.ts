import { apiPost } from './client'

export type OrderSlots = Record<string, string | number | boolean | null | Record<string, string>>
export type OrderChoice = {
  label: string
  patch: OrderSlots
  detail: string | null
  recommended: boolean
  confirm: boolean
}
export type OrderField = {
  name: string
  label: string
  type: string
  value: string
  required: boolean
}
export type OrderAsk = {
  field: string | null
  kind: 'choice' | 'number' | 'date' | 'form' | 'confirm'
  question: string
  choices: OrderChoice[]
  fields: OrderField[]
}
type Cost = { part_cost: number | null; transport_cost: number | null; total: number | null }
export type FulfilmentOption = {
  route_id: string
  depot: string
  city: string
  option_name: string | null
  mode: string | null
  service_level: string | null
  estimated_days: number | null
  arrives_by: string | null
  total: number | null
  cost: Cost
  stock: { part_number: string; available: number | null; state: string }[]
  meets_date: boolean | null
  within_budget: boolean | null
  /** days after the requested date (0 = on time); null when no date was given */
  days_late: number | null
  /** euros above the budget (0 = within); null when no budget was given */
  over_budget: number | null
  recommended: boolean
}
export type DeliveryAlternative = {
  title: string
  route_id: string
  label: string
  arrives: string
  total: number | null
  gap: string
  patch: OrderSlots
}
/** What the delivery choice is decided on: the user's limits, whether any option meets them all, and the closest trade-offs. */
export type DeliveryDecision = {
  status: 'met' | 'none' | 'open'
  limits: string[]
  headline: string
  question: string
  feasible: number
  total: number
  alternatives: DeliveryAlternative[]
  actions: OrderChoice[]
}
export type OrderSummary = {
  part: { part_number: string; name: string }
  quantity: number
  machine: string | null
  destination: {
    city: string
    street: string
    postal_code: string
    country_code: string
    receiving_hours: string | null
  }
  depot: { name: string; city: string }
  transport: {
    name: string | null
    mode?: string | null
    service_level?: string | null
    estimated_days: number | null
    arrives_by: string | null
  }
  dealer: { name: string; city: string }
  dealer_installation: boolean
  contact: Record<string, string>
  cost: Cost
  total: number | null
  cost_note: string
  checks: {
    needed_by: string | null
    timing: string | null
    meets_date?: boolean | null
    budget_eur?: number | null
    within_budget?: boolean | null
  }
  why?: string | null
  compared?: number
}
export type OrderCard = {
  part_number: string
  name: string
  category: string | null
  price: { amount: number; currency: string } | null
  part_status: string | null
  availability_state: string | null
  depot_stock_total: number | null
  fits: { model_code: string; name: string }[]
  supplier: { name: string; lead_time_days: number | null } | null
}
export type OrderResponse = {
  stage: string
  message: string
  blocked: boolean
  handled: boolean
  stages: { id: string; label: string; state: 'done' | 'current' | 'todo' }[]
  part: OrderCard | null
  ask: OrderAsk | null
  options: FulfilmentOption[] | null
  hidden_options: number
  explanation: string | null
  decision?: DeliveryDecision | null
  alternatives: { part_id: string; part_number: string; name: string; note: string }[]
  reasons: string[]
  summary: OrderSummary | null
  order: {
    order_id: string
    status?: string | null
    status_label: string | null
    cost: Cost
  } | null
  warnings: string[]
  prefilled: string[]
  profile_offer: Record<string, string> | null
  slots: OrderSlots
  /** the user said yes to the summary they were shown: the client confirms with that summary's total */
  confirm_ready?: boolean
  /** the server's seal on the summary shown; Place order sends it back, and any change to the order voids it */
  confirmation?: string | null
}
export type OrderTurnBody = {
  slots: OrderSlots
  patch?: OrderSlots
  message?: string
  confirm?: boolean
  reviewed_total?: number | null
  confirmation?: string | null
  idempotency_key?: string
  /** reopen a completed step to change it; every other choice is kept */
  revisit?: 'fulfilment' | 'details'
}

export const orderTurn = (body: OrderTurnBody, signal?: AbortSignal) =>
  apiPost<OrderResponse>('/spark/order', body, signal)
