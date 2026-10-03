import type { Availability } from '../types/store'
import { allParts, availabilityMeta, searchScore, storeCategories, type StorePart } from './store'

export type SortKey = 'featured' | 'price-asc' | 'price-desc' | 'name' | 'availability'

export interface Filters {
  q: string
  /** Category name, or empty for all */
  cat: string
  /** Machine model code, or empty for all */
  fit: string
  av: readonly Availability[]
  orderable: boolean
  /** Id of a price band, or empty */
  price: string
  sort: SortKey
}

export const PRICE_BANDS = [
  { id: 'u100', label: 'Under €100', test: (p: number) => p < 100 },
  { id: '100-500', label: '€100 to €500', test: (p: number) => p >= 100 && p < 500 },
  { id: '500-1500', label: '€500 to €1,500', test: (p: number) => p >= 500 && p < 1500 },
  { id: '1500', label: '€1,500 and above', test: (p: number) => p >= 1500 },
] as const

export const SORTS: readonly { key: SortKey; label: string }[] = [
  { key: 'featured', label: 'Featured' },
  { key: 'price-asc', label: 'Price, low to high' },
  { key: 'price-desc', label: 'Price, high to low' },
  { key: 'name', label: 'Name, A to Z' },
  { key: 'availability', label: 'Availability' },
]

const AVAILABILITY: readonly Availability[] = ['IN_STOCK', 'LIMITED', 'BACKORDER']
const categoryOrder = new Map(storeCategories.map((c, i) => [c.name, i]))

export const parseFilters = (params: URLSearchParams): Filters => {
  const sort = params.get('sort') as SortKey | null
  return {
    q: params.get('q') ?? '',
    cat: storeCategories.some((c) => c.name === params.get('cat')) ? (params.get('cat') as string) : '',
    fit: params.get('fit') ?? '',
    av: (params.get('av') ?? '').split(',').filter((a): a is Availability => AVAILABILITY.includes(a as Availability)),
    orderable: params.get('ord') === '1',
    price: PRICE_BANDS.some((b) => b.id === params.get('price')) ? (params.get('price') as string) : '',
    sort: SORTS.some((s) => s.key === sort) ? (sort as SortKey) : 'featured',
  }
}

export const toParams = (f: Filters): URLSearchParams => {
  const p = new URLSearchParams()
  if (f.q.trim()) p.set('q', f.q.trim())
  if (f.cat) p.set('cat', f.cat)
  if (f.fit) p.set('fit', f.fit)
  if (f.av.length) p.set('av', f.av.join(','))
  if (f.orderable) p.set('ord', '1')
  if (f.price) p.set('price', f.price)
  if (f.sort !== 'featured') p.set('sort', f.sort)
  return p
}

/** Number of narrowing filters in use (search and sort are not counted). */
export const activeFilterCount = (f: Filters): number => (f.cat ? 1 : 0) + (f.fit ? 1 : 0) + f.av.length + (f.orderable ? 1 : 0) + (f.price ? 1 : 0)

/** Applies the filters. `skip` leaves one group out, which is how each group's facet counts are worked out. */
export const applyFilters = (f: Filters, skip?: 'cat' | 'fit' | 'av' | 'price' | 'orderable'): StorePart[] => {
  const band = PRICE_BANDS.find((b) => b.id === f.price)
  return allParts.filter(
    (p) =>
      (skip === 'cat' || !f.cat || p.category === f.cat) &&
      (skip === 'fit' || !f.fit || p.fits.includes(f.fit)) &&
      (skip === 'av' || !f.av.length || f.av.includes(p.availability)) &&
      (skip === 'orderable' || !f.orderable || p.orderable) &&
      (skip === 'price' || !band || band.test(p.price)) &&
      searchScore(p, f.q) > 0,
  )
}

export const sortParts = (list: StorePart[], f: Filters): StorePart[] => {
  const out = [...list]
  switch (f.sort) {
    case 'price-asc':
      return out.sort((a, b) => a.price - b.price)
    case 'price-desc':
      return out.sort((a, b) => b.price - a.price)
    case 'name':
      return out.sort((a, b) => a.name.localeCompare(b.name))
    case 'availability':
      return out.sort((a, b) => availabilityMeta[a.availability].rank - availabilityMeta[b.availability].rank || a.name.localeCompare(b.name))
    default:
      if (f.q.trim()) return out.sort((a, b) => searchScore(b, f.q) - searchScore(a, f.q))
      return out.sort((a, b) => (categoryOrder.get(a.category) ?? 0) - (categoryOrder.get(b.category) ?? 0) || a.no.localeCompare(b.no))
  }
}
