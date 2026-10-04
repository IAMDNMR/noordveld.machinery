/** The only place the store talks to the network. Everything else calls the typed functions in this folder. */
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  get notFound(): boolean {
    return this.status === 404
  }
}

type Query = Record<string, string | number | boolean | readonly string[] | null | undefined>

const toQuery = (query: Query): string => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (typeof value === 'object') value.forEach((v) => params.append(key, v))
    else params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network', 'The parts service could not be reached.')
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null
    throw new ApiError(response.status, body?.error?.code ?? 'error', body?.error?.message ?? 'The parts service returned an error.')
  }
  return (await response.json()) as T
}

export const apiGet = <T>(path: string, query: Query = {}, signal?: AbortSignal): Promise<T> =>
  request<T>(`${path}${toQuery(query)}`, { signal, headers: { Accept: 'application/json' } })

export const apiPost = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  request<T>(path, { method: 'POST', signal, headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const apiPut = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  request<T>(path, { method: 'PUT', signal, headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const isAbort = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError'
