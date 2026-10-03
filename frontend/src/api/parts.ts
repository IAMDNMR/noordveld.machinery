import { apiGet } from './client'
import type { PartDetail, PartPage, PartQuery } from './types'

export const searchParts = (query: PartQuery, signal?: AbortSignal): Promise<PartPage> =>
  apiGet<PartPage>(
    '/parts',
    {
      q: query.q.trim(),
      category: query.category,
      machine: query.machine,
      availability: query.availability,
      orderable: query.orderable ? true : undefined,
      sort: query.sort,
      offset: query.offset,
      limit: query.limit,
    },
    signal,
  )

/** `key` is the unified part number or the part id. */
export const getPart = (key: string, signal?: AbortSignal): Promise<PartDetail> => apiGet<PartDetail>(`/parts/${encodeURIComponent(key)}`, {}, signal)
