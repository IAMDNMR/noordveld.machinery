/** The only place the store talks to the network. Everything else calls the typed functions in this folder. */
const BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** structured, safe-to-show facts about a refused business rule (a field name, the reasons a depot cannot supply) */
  readonly details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
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

let activeOrganization: string | null = null
/** The organization the signed-in person is working in. Sent only to organization-scoped routes; the server checks membership itself. */
export const setActiveOrganization = (id: string | null): void => {
  if (id === activeOrganization) return
  activeOrganization = id
  // Anything that shows organization-dependent things (the navigation) follows the organization the person is working in.
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('active-organization'))
}
export const getActiveOrganization = (): string | null => activeOrganization
// The workspace and business applications are organization-scoped: the server checks the person's access in THIS organization.
const ORG_SCOPED = /^\/(workspace|agent|intelligence|spark|orders|cart|checkout)(\/|\?|$)/

/** A request that has not answered by then has hung (a Spark answer takes well under a minute); the caller is told instead of waiting forever. */
export const REQUEST_TIMEOUT_MS = 90_000

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  // the caller's own signal still cancels the request; the timeout is a second reason to stop
  const stop = new AbortController()
  const outer = init.signal
  const cancel = () => stop.abort()
  outer?.addEventListener('abort', cancel)
  if (outer?.aborted) stop.abort()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    stop.abort()
  }, REQUEST_TIMEOUT_MS)
  try {
    const scoped =
      activeOrganization && ORG_SCOPED.test(path)
        ? {
            ...init,
            headers: {
              ...(init.headers as Record<string, string> | undefined),
              'X-Org-Id': activeOrganization,
            },
          }
        : init
    response = await fetch(`${BASE}${path}`, { ...scoped, signal: stop.signal })
  } catch (error) {
    if (timedOut) throw new ApiError(0, 'timeout', 'The server took too long to answer.')
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network', 'The server could not be reached.')
  } finally {
    clearTimeout(timer)
    outer?.removeEventListener('abort', cancel)
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: unknown }
    } | null
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'error',
      body?.error?.message ?? 'The server returned an error.',
      body?.error?.details,
    )
  }
  return (await response.json()) as T
}

export const apiGet = <T>(path: string, query: Query = {}, signal?: AbortSignal): Promise<T> =>
  request<T>(`${path}${toQuery(query)}`, { signal, headers: { Accept: 'application/json' } })

export const apiPost = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  request<T>(path, {
    method: 'POST',
    signal,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const apiPut = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  request<T>(path, {
    method: 'PUT',
    signal,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const apiDelete = <T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> =>
  request<T>(path, {
    method: 'DELETE',
    signal,
    headers: {
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const isAbort = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError'
