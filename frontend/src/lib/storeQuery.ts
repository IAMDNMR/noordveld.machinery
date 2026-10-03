import type { PartQuery, SortKey } from '../api'

export const STORE_ROUTE = '/parts-store'
export const CHECKOUT_ROUTE = `${STORE_ROUTE}/checkout`
export const PAGE_SIZE = 24

export const partPath = (partNumber: string): string => `${STORE_ROUTE}/${encodeURIComponent(partNumber)}`

/** Browse links: the catalogue state lives in the URL, so every list is shareable. */
export const categoryPath = (name: string): string => `${STORE_ROUTE}?${new URLSearchParams({ category: name })}`
export const machinePath = (modelCode: string): string => `${STORE_ROUTE}?${new URLSearchParams({ machine: modelCode })}`

export const SORTS: readonly { key: SortKey; label: string }[] = [
  { key: 'relevance', label: 'Relevance' },
  { key: 'name', label: 'Name A–Z' },
  { key: 'price_asc', label: 'Price: low to high' },
  { key: 'price_desc', label: 'Price: high to low' },
]

const isSort = (value: string | null): value is SortKey => SORTS.some((s) => s.key === value)

export const parseQuery = (params: URLSearchParams): PartQuery => {
  const sort = params.get('sort')
  const page = Number(params.get('page'))
  return {
    q: params.get('q') ?? '',
    category: params.get('category') ?? '',
    machine: params.get('machine') ?? '',
    availability: params.getAll('availability'),
    orderable: params.get('orderable') === '1',
    sort: isSort(sort) ? sort : 'relevance',
    offset: Number.isInteger(page) && page > 1 ? (page - 1) * PAGE_SIZE : 0,
    limit: PAGE_SIZE,
  }
}

export const toParams = (query: Partial<Omit<PartQuery, 'limit' | 'offset'>> & { page?: number }): URLSearchParams => {
  const params = new URLSearchParams()
  if (query.q?.trim()) params.set('q', query.q.trim())
  if (query.category) params.set('category', query.category)
  if (query.machine) params.set('machine', query.machine)
  query.availability?.forEach((a) => params.append('availability', a))
  if (query.orderable) params.set('orderable', '1')
  if (query.sort && query.sort !== 'relevance') params.set('sort', query.sort)
  if (query.page && query.page > 1) params.set('page', String(query.page))
  return params
}

export const activeFilterCount = (query: PartQuery): number =>
  (query.category ? 1 : 0) + (query.machine ? 1 : 0) + query.availability.length + (query.orderable ? 1 : 0)
