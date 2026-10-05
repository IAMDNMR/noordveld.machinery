import { apiGet, apiPost, apiPut } from './client'

/** The demo session, checkout and the order workflow (backend/app/api/routes/accounts.py, checkout.py, orders.py). The role always comes from the backend,
 *  and so does every order's state: nothing about an order is remembered in the browser. */
export type Role = 'END_USER' | 'ORDER_PROCESSOR'

export interface Me {
  id: string
  name: string
  email: string
  role: Role
  customer: string | null
  permissions: string[]
}

export interface DemoUser {
  id: string
  name: string
  role: Role
  customer: string | null
}

export type OrderStatus =
  | 'NEW' | 'CONFIRMED' | 'PROCESSING' | 'ALLOCATED' | 'SHIPPED' | 'DELIVERED'
  | 'FULFILMENT_PENDING' | 'FULFILLING' | 'READY_TO_SHIP' | 'COMPLETED'
  | 'REJECTED' | 'ALLOCATION_FAILED' | 'ALLOCATION_RELEASED' | 'CANCELLED' | 'SHIPMENT_EXCEPTION' | 'DELIVERY_FAILED' | 'SERVICE_CANCELLED'
export type Queue = 'pending_review' | 'needs_fulfilment' | 'ready_to_ship' | 'shipped' | 'completed' | 'exceptions'
export const DIRECT_ORDER = 'DIRECT_ORDER'

export interface OrderRow {
  order_id: string
  order_date: string | null
  status: OrderStatus
  status_label: string
  parts: string[]
  fits: string[]
  total: number | null
  currency: string
  channel?: string | null
  fulfilment: string
  data_status: string | null
  /** direct orders */
  dealer?: string | null
  depot?: string | null
  /** processor only */
  customer?: string
  queue?: Queue
}

export interface OrderLine {
  line_no: number | null
  part_id: string
  part_number: string
  name: string
  quantity: number
  machine?: string | null
  unit_price_eur: number | null
  line_total_eur: number | null
  fitment: { model_code: string; name: string | null; status: string | null }[]
  availability_state: string | null
  in_stock_units: number
  stock_unknown_depots?: number
  fulfilment: string
  allocation_status: string | null
  reserved_quantity?: number | null
  /** processor only */
  part_status?: string | null
  orderable?: boolean | null
  price?: { list_price_ex_vat: number; currency: string; data_status: string | null } | null
  warehouses?: { warehouse_id: string; name: string; city: string | null; available: number | null; stock_status?: string | null; data_status: string | null }[]
  suppliers?: { name: string; lead_time_days: number | null; primary: boolean | null; data_status: string | null }[]
  evidence?: { fitment: string; inventory: string | null; price: string | null; line: string | null }
}

export interface TrackingEvent {
  event_seq: number | null
  event_status: string | null
  event_date: string | null
  event_location: string | null
  data_status?: string | null
}

export interface Shipment {
  shipment_id: string
  status: string | null
  tracking_ref: string | null
  tracking_basis?: string | null
  dispatched_from: string | null
  carrier: string | null
  data_status: string | null
  mode?: string | null
  option?: string | null
  estimated_days?: number | null
  destination?: { city: string | null; country_code: string | null } | null
  events: TrackingEvent[]
}

export interface Stage {
  stage: string
  state: 'done' | 'current' | 'pending' | 'exception' | 'skipped'
}

export interface OrderAction {
  action: string
  label: string
  allowed: boolean
  reason: string | null
  to_status: OrderStatus | null
  note: string | null
}

export interface DealerService {
  service_id: string
  service_status: 'CREATED' | 'PART_RECEIVED' | 'STARTED' | 'INSTALLED' | 'COMPLETED' | 'CANCELLED'
  created_at: string | null
  part_received_at: string | null
  started_at: string | null
  installed_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  dealer: string | null
  data_status: string | null
}

export interface Freight {
  amount: number
  currency: string
  data_status: string | null
  label: string
}

export interface OrderDetail {
  order_id: string
  order_date: string | null
  status: OrderStatus
  status_label: string
  channel: string | null
  currency: string
  data_status: string | null
  totals: { subtotal_ex_vat: number | null; shipping_ex_vat: number | null; vat_amount: number | null; total_incl_vat: number | null; note: string | null }
  lines: OrderLine[]
  shipments: Shipment[]
  history: { sequence: number | null; status: string | null; status_label: string | null; previous_status: string | null; action: string | null; occurred_at: string | null; by: string | null; role: string | null; recorded: string | null }[]
  payment: string
  /** direct orders: what the customer entered at checkout, and the lifecycle as recorded in the graph */
  requester?: { name: string | null; email: string | null; phone: string | null; company: string | null }
  delivery?: { ship_to_id: string | null; street: string | null; city: string | null; postal_code: string | null; country_code: string | null }
  receiver?: { name: string | null; phone: string | null }
  dealer?: { dealer_id: string; name: string; city: string | null; country_code: string | null; dealer_type: string | null } | null
  dealer_service_required?: boolean
  fulfilment?: {
    depot: { warehouse_id: string; name: string; city: string | null; country_code: string | null } | null
    allocation_status: string | null
    allocation_updated_at: string | null
    lines: { part_number: string; quantity: number; reserved_quantity: number | null; allocation_status: string | null; machine: string | null }[]
  }
  transport?: {
    route_id: string | null
    option_code: string | null
    mode: string | null
    distance_km: number | null
    estimated_days: number | null
    estimate_basis: string | null
    data_status: string | null
    freight_estimate: Freight | null
  }
  cost?: { part_cost: number | null; transport_cost: number | null; total: number | null; currency: string; status: string; note: string }
  service?: DealerService | null
  provenance?: { order: string | null; transport: string | null; tracking: string; inventory: string }
  stages?: Stage[]
  actions?: OrderAction[]
  /** processor only */
  customer?: { customer_id: string | null; name: string | null; city: string | null; country_code: string | null }
  delivery_address?: { city: string | null; country_code: string | null } | null
  next?: { status: OrderStatus; label: string; allowed: boolean; reason: string | null } | null
}

// ── checkout ─────────────────────────────────────────────────────────────────────────────────────
export interface CartItem {
  part_id: string
  quantity: number
  machine?: string | null
}

export interface Destination {
  ship_to_id: string
  street: string | null
  city: string | null
  postal_code: string | null
  country_code: string
  receiving_hours: string | null
  vehicle_restrictions: string | null
  data_status: string | null
}

export interface DealerRow {
  dealer_id: string
  name: string
  city: string | null
  country_code: string | null
  dealer_type: string | null
  data_status: string | null
}

export interface TransportOption {
  route_id: string
  option_id: string | null
  option_code: string | null
  option_name: string | null
  mode: string | null
  service_level: string | null
  origin_depot_id: string
  destination_shipto_id: string | null
  distance_km: number | null
  estimated_days: number | null
  estimate_basis: string
  legs: number | null
  data_status: string
  freight: Freight | null
}

export interface DepotPlan {
  depot_id: string
  name: string | null
  city: string | null
  country_code: string | null
  lines: { part_id: string; part_number: string; quantity: number; state: 'IN_STOCK' | 'LOW_STOCK' | 'ON_ORDER' | 'OUT_OF_STOCK' | 'UNKNOWN'; available: number | null; can_supply: boolean }[]
  selectable: boolean
  reasons: string[]
  options: TransportOption[]
  recommended_route_id: string | null
  recommended: boolean
}

export interface CheckoutReview {
  lines: { line_no: number; part_id: string; part_number: string; part_name: string; quantity: number; machine: string | null }[]
  destination: { ship_to_id: string; street: string | null; city: string | null; postal_code: string | null; country_code: string }
  depots: DepotPlan[]
  can_order: boolean
  cost: { part_cost: number | null; transport_cost: number | null; total: number | null; currency: string; status: string; note: string }
}

export interface PlaceOrderBody {
  items: CartItem[]
  requester: { name: string; email: string; phone: string; company: string }
  delivery: { ship_to_id: string; receiver_name: string; receiver_phone: string }
  dealer_id: string
  dealer_service_required: boolean
  depot_id: string
  route_id: string
  confirmed: boolean
  idempotency_key: string
}

export const getMe = (signal?: AbortSignal) => apiGet<Me>('/me', {}, signal)
export const getDemoUsers = (signal?: AbortSignal) => apiGet<DemoUser[]>('/auth/demo-users', {}, signal)
export const signIn = (userId: string) => apiPost<Me>('/auth/login', { user_id: userId })
export const signOut = () => apiPost<{ signed_out: boolean }>('/auth/logout', {})

export const getOrders = (signal?: AbortSignal) => apiGet<OrderRow[]>('/orders', {}, signal)
export const getOrder = (id: string, signal?: AbortSignal) => apiGet<OrderDetail>(`/orders/${encodeURIComponent(id)}`, {}, signal)
/** Earlier-channel orders only. */
export const updateStatus = (id: string, status: OrderStatus, expected: OrderStatus) =>
  apiPost<OrderDetail>(`/orders/${encodeURIComponent(id)}/status`, { status, expected_status: expected })
/** One lifecycle action on a direct order. The server decides whether it is valid now. */
export const orderAction = (id: string, action: string, expected: OrderStatus) =>
  apiPost<OrderDetail>(`/orders/${encodeURIComponent(id)}/actions`, { action, expected_status: expected })

export const getCountries = (signal?: AbortSignal) => apiGet<{ country_code: string; destinations: number }[]>('/checkout/countries', {}, signal)
export const getDestinations = (country: string, signal?: AbortSignal) => apiGet<Destination[]>('/checkout/destinations', { country }, signal)
export const getDealers = (country: string | null, signal?: AbortSignal) => apiGet<DealerRow[]>('/checkout/dealers', { country }, signal)
export const reviewCheckout = (items: CartItem[], shipToId: string, signal?: AbortSignal) => apiPost<CheckoutReview>('/checkout/review', { items, ship_to_id: shipToId }, signal)
export const placeOrder = (body: PlaceOrderBody) => apiPost<OrderDetail>('/orders', body)

export interface ServerCartLine {
  partId: string
  partNumber: string | null
  partName: string | null
  qty: number
  machine: string | null
}
export const getMyCart = (signal?: AbortSignal) => apiGet<ServerCartLine[]>('/me/cart', {}, signal)
export const putMyCart = (lines: { part_id: string; quantity: number; machine?: string | null }[]) => apiPut<ServerCartLine[]>('/me/cart', { lines })
