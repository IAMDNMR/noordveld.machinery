/** Response shapes of the Noordveld catalogue API (backend/app/schemas). `null` means the graph holds no value. */
export type DataStatus = string

export interface Money {
  amount: number
  currency: string
  data_status: DataStatus | null
}

export interface Availability {
  state: string | null
  orderable: boolean | null
  part_status: string | null
  total_available: number | null
  data_status: DataStatus | null
}

export interface FitmentBrief {
  model_code: string
  fitment_status: string | null
}

export interface PartSummary {
  part_id: string
  part_number: string
  name: string
  category: string | null
  subcategory: string | null
  fitment: FitmentBrief[]
  price: Money | null
  availability: Availability | null
}

export interface PartPage {
  items: PartSummary[]
  total: number
  offset: number
  limit: number
}

export interface MachineOption {
  machine_id: string
  model_code: string
  name: string
  machine_type: string | null
  origin_plant: string | null
  country: string | null
  part_count: number
}

export interface CategoryOption {
  category_id: string
  name: string
  part_count: number
}

export interface AvailabilityOption {
  state: string
  part_count: number
  data_status: DataStatus | null
}

export interface CatalogueFilters {
  categories: CategoryOption[]
  machines: MachineOption[]
  availability: AvailabilityOption[]
}

export interface PartCore {
  part_id: string
  part_number: string
  name: string
  category: string | null
  subcategory: string | null
  brand: string | null
  origin_plant: string | null
  note: string | null
  confidence: string | null
  data_status: DataStatus | null
  source_sheet: string | null
  source_record_id: string | null
}

export interface Fitment {
  machine_id: string
  model_code: string
  name: string
  machine_type: string | null
  origin_plant: string | null
  fitment_status: string | null
  condition_note: string | null
  data_status: DataStatus | null
}

export interface Specification {
  group: string | null
  name: string
  value: string | null
  unit: string | null
  source_text: string | null
  data_status: DataStatus | null
}

export interface LegacyReference {
  legacy_part_number: string | null
  legacy_business: string | null
  legacy_plant: string | null
  mapping_type: string | null
  note: string | null
  mapping_confidence: string | null
  data_status: DataStatus | null
}

export interface PriceInfo {
  amount: number
  currency: string
  valid_from: string | null
  valid_to: string | null
  price_status: string | null
  data_status: DataStatus | null
}

export interface Profile {
  availability_state: string | null
  orderable: boolean | null
  part_status: string | null
  status_reason: string | null
  weight_kg: number | null
  warranty_months: number | null
  return_window_days: number | null
  data_status: DataStatus | null
}

export interface WarehouseStock {
  warehouse_id: string
  name: string | null
  city: string | null
  country_code: string | null
  available: number | null
  stock_status: string | null
  data_status: DataStatus | null
}

export interface DealerStock {
  dealer_id: string
  name: string | null
  city: string | null
  country_code: string | null
  pickup_allowed: boolean | null
  available: number | null
  stocking_status: string | null
  data_status: DataStatus | null
}

export interface SupplierInfo {
  supplier_id: string
  name: string | null
  city: string | null
  country_code: string | null
  is_primary: boolean | null
  lead_time_days: number | null
  min_order_qty: number | null
  supplier_part_number: string | null
  data_status: DataStatus | null
}

export interface Compliance {
  requirement: string | null
  standard: string | null
  certification: string | null
  certificate_status: string | null
  valid_until: string | null
  data_status: DataStatus | null
}

export interface AssemblyLink {
  assembly_id: string
  name: string | null
  quantity: number | null
  bom_status: string | null
  data_status: DataStatus | null
}

export type RelationKind = 'SAME_NAME_GROUP_AS' | 'RELATED_COMPONENT' | 'CO_ORDERED_WITH'

export interface RelatedPart {
  part_id: string
  part_number: string
  name: string
  category: string | null
  relation: RelationKind
  interchangeability_status: string | null
  data_status: DataStatus | null
}

export interface Identification {
  model_code: string | null
  reason: string | null
  identification_needed: string | null
  variants: { variant_name: string | null; serial_from: string | null; serial_to: string | null }[]
  data_status: DataStatus | null
}

export interface PartDetail {
  part: PartCore
  fitment: Fitment[]
  specifications: Specification[]
  legacy_references: LegacyReference[]
  price: PriceInfo | null
  profile: Profile | null
  warehouses: WarehouseStock[]
  dealers: DealerStock[]
  suppliers: SupplierInfo[]
  compliance: Compliance[]
  assemblies: AssemblyLink[]
  related: RelatedPart[]
  identification: Identification[]
}

export interface QuoteLine {
  part: PartSummary
  quantity: number
  line_total: Money | null
}

export interface Quote {
  lines: QuoteLine[]
  unknown_part_ids: string[]
  subtotal: Money | null
  unpriced_part_ids: string[]
  order_placement_available: boolean
  note: string
}

export type SortKey = 'relevance' | 'name' | 'price_asc' | 'price_desc'

/** What the catalogue page can ask the API for. */
export interface PartQuery {
  q: string
  category: string
  machine: string
  availability: string[]
  orderable: boolean
  sort: SortKey
  offset: number
  limit: number
}
