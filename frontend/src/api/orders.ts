import { apiGet, apiPost, apiPut } from './client'

/** The demo session and the order workflow (backend/app/api/routes/accounts.py and orders.py). The role always comes from the backend. */
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

export type OrderStatus = 'NEW' | 'CONFIRMED' | 'PROCESSING' | 'ALLOCATED' | 'SHIPPED' | 'DELIVERED'
export type Queue = 'pending_review' | 'needs_fulfilment' | 'ready_to_ship' | 'shipped' | 'completed'

export interface OrderRow {
  order_id: string
  order_date: string | null
  status: OrderStatus
  status_label: string
  parts: string[]
  fits: string[]
  total: number | null
  currency: string
  fulfilment: string
  data_status: string | null
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
  unit_price_eur: number | null
  line_total_eur: number | null
  fitment: { model_code: string; name: string | null; status: string | null }[]
  availability_state: string | null
  in_stock_units: number
  fulfilment: string
  allocation_status: string | null
  /** processor only */
  part_status?: string | null
  orderable?: boolean | null
  price?: { list_price_ex_vat: number; currency: string; data_status: string | null } | null
  warehouses?: { warehouse_id: string; name: string; city: string | null; available: number | null; data_status: string | null }[]
  suppliers?: { name: string; lead_time_days: number | null; primary: boolean | null; data_status: string | null }[]
  evidence?: { fitment: string; inventory: string | null; price: string | null; line: string | null }
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
  shipments: { shipment_id: string; status: string | null; tracking_ref: string | null; dispatched_from: string | null; carrier: string | null; data_status: string | null;
               events: { event_seq: number | null; event_status: string | null; event_date: string | null; event_location: string | null }[] }[]
  history: { sequence: number | null; status: string | null; status_label: string | null; previous_status: string | null; action: string | null; occurred_at: string | null; by: string | null; role: string | null; recorded: string | null }[]
  payment: string
  /** processor only */
  customer?: { customer_id: string; name: string; city: string | null; country_code: string | null }
  delivery_address?: { city: string | null; country_code: string | null } | null
  next?: { status: OrderStatus; label: string; allowed: boolean; reason: string | null } | null
}

export const getMe = (signal?: AbortSignal) => apiGet<Me>('/me', {}, signal)
export const getDemoUsers = (signal?: AbortSignal) => apiGet<DemoUser[]>('/auth/demo-users', {}, signal)
export const signIn = (userId: string) => apiPost<Me>('/auth/login', { user_id: userId })
export const signOut = () => apiPost<{ signed_out: boolean }>('/auth/logout', {})

export const getOrders = (signal?: AbortSignal) => apiGet<OrderRow[]>('/orders', {}, signal)
export const getOrder = (id: string, signal?: AbortSignal) => apiGet<OrderDetail>(`/orders/${encodeURIComponent(id)}`, {}, signal)
export const updateStatus = (id: string, status: OrderStatus, expected: OrderStatus) =>
  apiPost<OrderDetail>(`/orders/${encodeURIComponent(id)}/status`, { status, expected_status: expected })
export const submitRequest = (items: { part_id: string; quantity: number }[], key: string) => apiPost<OrderDetail>('/requests', { items, idempotency_key: key })

export const getMyCart = (signal?: AbortSignal) => apiGet<{ partId: string; qty: number }[]>('/me/cart', {}, signal)
export const putMyCart = (lines: { part_id: string; quantity: number }[]) => apiPut<{ partId: string; qty: number }[]>('/me/cart', { lines })
