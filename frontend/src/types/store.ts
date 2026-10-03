export type PartStatus = 'VERIFIED' | 'UNVERIFIED' | 'IDENTIFICATION_REQUIRED' | 'AMBIGUOUS'
export type Availability = 'IN_STOCK' | 'LIMITED' | 'BACKORDER'

export interface StoreWarehouse {
  id: string
  name: string
  city: string
  country: string
}

export interface StoreCategory {
  id: string
  name: string
  count: number
  subs: readonly { id: string; name: string; count: number }[]
}

export interface StoreCompliance {
  requirement: string
  standard: string
  certification: string
  status: string
  validUntil: string
}

export interface StoreShippingRate {
  band: string
  fromKm: number
  toKm: number
  method: 'STANDARD' | 'EXPRESS'
  price: number
  days: number
}

export interface StoreCountry {
  code: string
  name: string
  vat: number
}

export interface StoreSpec {
  group: string
  name: string
  value: string
  unit: string
}

/** One catalogue part exactly as generated from the workbook. */
export interface StorePartRaw {
  id: string
  no: string
  name: string
  desc: string
  category: string
  categoryId: string
  subcategory: string
  type: string
  legacyNo: string
  legacyBusiness: string
  plant: string
  brand: string
  status: PartStatus
  statusReason: string
  orderable: boolean
  availability: Availability
  /** Demo list price, EUR, excluding VAT */
  price: number
  weightKg: number
  warrantyMonths: number
  returnDays: number
  specNote: string
  specs: readonly StoreSpec[]
  notes: readonly string[]
  /** Model codes the catalogue states the part fits. The store never adds to this. */
  fits: readonly string[]
  /** Units available per warehouse id */
  stock: Readonly<Record<string, number>>
  dealers: number
  compliance: readonly string[]
  related: readonly { id: string; kind: 'together' | 'family' }[]
  ident: readonly { model: string; variants: readonly { name: string; from: string; to: string }[] }[]
  backorder: { qty: number; days: number } | null
  aliases: readonly string[]
}
