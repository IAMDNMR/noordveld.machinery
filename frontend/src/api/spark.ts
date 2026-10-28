import { apiGet, apiPost, ApiError, getActiveOrganization } from './client'
import type { AgentResponse } from './agent'
import type { AgentResponse as AccountResponse } from './commerce'
import type { QueryResponse } from './index'

export interface SparkTable {
  columns: string[]
  rows: { key: string; title: string; part_number: string | null; cells: (string | null)[] }[]
}
export interface SparkChart {
  metric: string
  rows: { name: string; value: number }[]
}
/** How each part of a reply is shown, chosen by the server from the request and the verified records. Text is the default. */
export interface SparkPresentation {
  intelligence: 'text' | 'table' | 'cards' | 'chart' | 'graph' | 'choices' | null
  shopping: 'text' | 'product' | 'compare' | null
  account: 'text' | 'detail' | null
  table: SparkTable | null
  chart: SparkChart | null
  note: string | null
}
export interface SparkResponse {
  message: string
  context: string
  view: 'answer' | 'compare' | 'chart' | 'graph'
  /** absent on replies saved before adaptive presentation: those keep the classic layout */
  presentation?: SparkPresentation
  intelligence: QueryResponse | null
  shopping: AgentResponse | null
  account: AccountResponse | null
  sign_in_required: boolean
  /** consented profile details Spark used for this request */
  profile_used?: string[]
  /** the user asked to order this offered part: start the guided order with it */
  order_part?: {
    part_id: string
    label: string
    /** details the user already gave (machine, quantity, budget, priority); the order re-validates them */
    patch?: Record<string, string | number>
  } | null
  warnings: string[]
  steps: {
    label: string
    status: 'completed' | 'failed' | 'sign_in_required' | 'access_denied'
    ms: number
  }[]
}
export const askSpark = (
  message: string,
  context: string | null,
  selected: { kind: string; key: string }[] = [],
  limit = 12,
  signal?: AbortSignal,
  orderPart: { part_id: string; label: string } | null = null,
) =>
  apiPost<SparkResponse>(
    '/spark/conversation',
    { message, context, selected, limit, order_part: orderPart },
    signal,
  )

export const sparkVoiceStatus = (signal?: AbortSignal) =>
  apiGet<{ enabled: boolean; reason: string; mode?: 'hands_free' | 'dictate' }>(
    '/spark/voice/status',
    {},
    signal,
  )

async function audioRequest(
  path: string,
  body: BodyInit,
  contentType: string,
  signal?: AbortSignal,
) {
  const org = getActiveOrganization()
  const response = await fetch(`/api/v1/spark/voice/${path}`, {
    method: 'POST',
    body,
    signal,
    headers: { 'Content-Type': contentType, ...(org ? { 'X-Org-Id': org } : {}) },
  })
  if (!response.ok)
    throw new ApiError(
      response.status,
      'speech_unavailable',
      'Voice is unavailable right now. You can keep typing.',
    )
  return response
}
export const sparkTranscribe = async (
  blob: Blob,
  signal?: AbortSignal,
): Promise<{ text: string; confidence: number | null }> =>
  (await audioRequest('transcribe', blob, blob.type, signal)).json()
export const sparkSpeak = async (text: string, signal?: AbortSignal) =>
  (await audioRequest('speak', JSON.stringify({ text }), 'application/json', signal)).blob()
