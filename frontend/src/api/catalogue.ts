import { apiGet } from './client'
import type { CatalogueFilters } from './types'

/** Categories, machines and availability states with live part counts. */
export const getFilters = (signal?: AbortSignal): Promise<CatalogueFilters> => apiGet<CatalogueFilters>('/catalogue/filters', {}, signal)
