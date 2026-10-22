import {
  getFilters,
  searchParts,
  type CatalogueFilters,
  type PartQuery,
  type PartSummary,
} from '../../api'
import { useApi } from '../../hooks/useApi'
import { partImageUrl } from '../../lib/assets'

/**
 * The catalogue the Parts & Services page shows, read once from the existing parts API (it pages at most 60 items, so the page reads every page).
 * Nothing here is business data: parts, categories, fitment, prices and availability all come from the backend.
 */
const query = (offset: number): PartQuery => ({
  q: '',
  category: '',
  machine: '',
  availability: [],
  orderable: false,
  sort: 'relevance',
  offset,
  limit: 60,
})

export async function loadCatalogue(
  signal: AbortSignal,
): Promise<{ parts: PartSummary[]; total: number; filters: CatalogueFilters }> {
  const [first, filters] = await Promise.all([searchParts(query(0), signal), getFilters(signal)])
  const parts = [...first.items]
  for (
    let offset = first.items.length;
    offset < first.total && first.items.length > 0;
    offset += 60
  )
    parts.push(...(await searchParts(query(offset), signal)).items)
  return { parts, total: first.total, filters }
}

export const useCatalogue = () => useApi(loadCatalogue, 'aftersales-catalogue')

export const withImage = (parts: PartSummary[]): PartSummary[] =>
  parts.filter((p) => partImageUrl(p.part_number))

/** Plain-language labels for the backend's codes (never a new value). */
export const label = (code: string | null | undefined): string =>
  (code ?? 'not recorded').replace(/_/g, ' ').toLowerCase()
export const sentence = (code: string | null | undefined): string =>
  label(code).replace(/^./, (c) => c.toUpperCase())

/** Whether a price is demonstration data: every price in the dataset is labelled as such by its data status. */
export const priceText = (p: PartSummary): string | null =>
  p.price
    ? `${p.price.amount.toFixed(2)} ${p.price.currency}${p.price.data_status === 'SYNTHETIC_DEMO' ? ' · demo price' : ''}`
    : null
