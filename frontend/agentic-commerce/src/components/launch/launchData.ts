/**
 * The records the launch film shows, loaded at runtime from the backend (GET /api/v1/showcase/launch-film), which reads them
 * from the Noordveld graph. Nothing here is hardcoded: change the graph and the film changes. Synthetic demo records keep
 * their "(demo)" names. `filmData` is set by `loadFilmData()` before the film's acts are loaded (see LaunchFilm.tsx).
 */
export interface FilmStock {
  id: string
  kind: 'warehouse' | 'dealer'
  name: string
  city: string
  available: number
  pickup: boolean
  /** City-centre coordinates for the schematic map; null when the city has no map position */
  lat: number | null
  lon: number | null
}

export interface FilmData {
  counts: { machines: number; parts: number; fitments: number; specifications: number }
  machine: { model: string; name: string; type: string; plant: string; country: string; partsFitted: number; inStock: number; legacyMapped: number; slug: string; services: string[]; serviceInterval: number[] }
  part: {
    id: string; no: string; name: string; category: string; subcategory: string; legacyNo: string; legacyBusiness: string; plant: string; fits: string[]; specNote: string
    priceExVat: number; weightKg: number; status: string; availability: string; usedInService: boolean
  }
  siblings: { no: string; name: string }[]
  supplier: { id: string; name: string; city: string; leadDays: number; partNo: string; lat: number; lon: number }
  stock: FilmStock[]
  customer: { id: string; name: string; city: string; lat: number; lon: number }
  pickupDealer: string | null
  delivery: { from: string; km: number; standard: { price: number; days: number }; express: { price: number; days: number } }
  provenance: string
}

// eslint-disable-next-line import/no-mutable-exports -- assigned once, before the modules that read it are loaded
export let filmData: FilmData

const API = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

/** Fetches the film's records. Rejects with a readable message when the graph does not hold what the story needs. */
export async function loadFilmData(signal?: AbortSignal): Promise<FilmData> {
  const response = await fetch(`${API}/showcase/launch-film`, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`The film data could not be loaded (${response.status}).`)
  const data = (await response.json()) as Partial<FilmData>
  const missing = (['machine', 'part', 'supplier', 'customer', 'delivery'] as const).filter((k) => !data[k])
  if (missing.length) throw new Error(`The graph does not hold the film's ${missing.join(', ')} record${missing.length > 1 ? 's' : ''}.`)
  if (data.supplier!.lat == null || data.customer!.lat == null) throw new Error('The film map has no position for the supplier or customer city.')
  filmData = data as FilmData
  return filmData
}
