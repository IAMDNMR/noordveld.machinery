/** Shapes the website components render. Every value is built from the backend's /site/overview response (src/data/site.ts). */

/** Lower-case plant city, also the key of the plant photo in src/assets/plants */
export type PlantId = string

export interface Part {
  partNo: string
  name: string
  category: string
  specNote: string
}

export interface Machine {
  /** Model code exactly as stored in the graph */
  model: string
  /** URL-safe model code (also the key of the machine images) */
  slug: string
  /** Machine type as stored in the graph */
  name: string
  /** Machine family from the graph (MEMBER_OF_FAMILY) */
  family: string
  brand: string
  acquired?: number
  plantId: PlantId
  /** Plant name as stored in the graph, e.g. "Assen (NL)" */
  plant: string
  /** Short sentence built only from graph fields */
  description: string
  /** Only fields the graph provides. No invented technical data. */
  specifications: Record<string, string>
  /** Parts recorded as fitting this machine (FITS) */
  relatedParts: readonly Part[]
  /** Names of fitting parts in the Attachments category */
  attachments: readonly string[]
  /** Synthetic demo profile from the graph; shown with a demo label */
  application: { text: string; context: string | null; introduced: number | null } | null
}

export interface Plant {
  id: PlantId
  city: string
  country: string
  countryCode: string
  brand: string
  acquired?: number
  machineCount: number
  /** City-centre coordinates from the backend's map reference, only to place the schematic map */
  lat: number | null
  lon: number | null
}

export interface SiteData {
  machines: readonly Machine[]
  plants: readonly Plant[]
  families: readonly string[]
  /** The machine with the most recorded parts: featured on the home page */
  featured: Machine | null
  partCount: number
  partCategories: readonly { name: string; count: number }[]
}
