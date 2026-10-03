export type PlantId = 'assen' | 'lingen' | 'coevorden'

/** Editorial grouping of the catalogued machine types. The catalog itself only provides the machine type. */
export type MachineFamily = 'Loading' | 'Material handling' | 'Conveying'

export interface Part {
  partNo: string
  name: string
  category: string
  plantId: PlantId
  plantOfOrigin: string
  compatibleModels: readonly string[]
  specNote: string
}

export interface Machine {
  /** Exactly as written in the catalog, e.g. "NV-2100" */
  model: string
  /** URL-safe model, e.g. "nv-2100" */
  slug: string
  /** Machine type exactly as written in the catalog */
  name: string
  family: MachineFamily
  /** Brand / origin without the acquisition note, e.g. "Kessler" */
  brand: string
  /** Brand / origin exactly as written in the catalog */
  origin: string
  /** Year the brand was acquired, where the catalog states it */
  acquired?: number
  plantId: PlantId
  /** Plant exactly as written in the catalog, e.g. "Assen (NL)" */
  plant: string
  /** Short factual description built only from catalog fields */
  description: string
  /** Only fields the catalog provides. No invented technical data. */
  specifications: Record<string, string>
  /** Catalog parts that list this model as compatible */
  relatedParts: readonly Part[]
  /** Names of catalogued attachments compatible with this model */
  attachments: readonly string[]
}

export interface Plant {
  id: PlantId
  city: string
  country: 'Netherlands' | 'Germany'
  countryCode: 'NL' | 'DE'
  brand: string
  acquired?: number
  /** Approximate coordinates, used only to place the schematic map */
  lat: number
  lon: number
}
