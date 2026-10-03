/** Response shapes of the Parts Intelligence API (backend/app/schemas/intelligence.py). `null` means the graph holds no value. */
export type DataClass =
  | 'REAL'
  | 'SOURCE_DERIVED'
  | 'DERIVED'
  | 'SYNTHETIC_DEMO'
  | 'USER_PROVIDED'
  | 'TEST_DATA'
  | 'INTERNAL_REFERENCE_ONLY'
  | 'UNKNOWN'
  | 'NOT_CONNECTED'

export type EntityKind = 'PART' | 'MACHINE' | 'SUPPLIER' | 'DEALER' | 'ASSEMBLY' | 'CATEGORY'

export interface Fact {
  label: string
  value: string | null
}

export interface FactGroup {
  label: string
  values: string[]
}

export interface IntelligenceAction {
  kind: 'view_part' | 'parts_store' | 'investigate' | 'identify' | 'ask'
  label: string
  href: string | null
  question: string | null
}

export interface ResultItem {
  kind: 'part' | 'machine' | 'supplier' | 'dealer' | 'assembly' | 'category' | 'relationship' | 'compliance' | 'stock' | 'metric' | 'path'
  key: string
  title: string
  subtitle: string | null
  part_number: string | null
  relationship: string | null
  data_class: DataClass
  facts: Fact[]
  groups: FactGroup[]
}

export interface Evidence {
  entity: string
  entity_kind: string
  relationship: string
  target: string
  target_kind: string
  data_class: DataClass
}

export interface ProvenanceSummary {
  data_class: DataClass
  count: number
}

export interface EntityRef {
  kind: EntityKind
  key: string
  label: string
  detail: string | null
  match: 'exact' | 'alias' | 'partial'
  data_class: DataClass
}

export interface Candidate {
  kind: EntityKind
  key: string
  label: string
  detail: string | null
}

export interface Clarification {
  question: string
  candidates: Candidate[]
  suggestions: string[]
}

export interface QueryResponse {
  question: string
  intent: string
  intent_label: string
  understood_by: 'rules' | 'llm' | 'selection'
  entities: EntityRef[]
  answer: { summary: string; grounded: boolean; source: 'template' | 'gemini' }
  results: ResultItem[]
  total: number
  evidence: Evidence[]
  provenance: ProvenanceSummary[]
  graph_path: string[]
  warnings: string[]
  actions: IntelligenceAction[]
  clarification: Clarification | null
  elapsed_ms: number
}

export interface Suggestion {
  category: string
  question: string
}

export interface PartOverview {
  part_id: string
  part_number: string
  name: string
  description: string | null
  category: string | null
  subcategory: string | null
  manufacturer: string | null
  origin_plant: string | null
  status: { code: 'VERIFIED' | 'IDENTIFICATION_REQUIRED' | 'UNVERIFIED' | 'OTHER'; label: string }
  identification: { model_code: string | null; reason: string | null; needed: string | null }[]
  data_class: DataClass
  source: string | null
  last_updated: string | null
  orderable: boolean | null
  actions: IntelligenceAction[]
}

export interface FitmentItem {
  model_code: string
  name: string | null
  machine_type: string | null
  family: string | null
  fitment_status: string | null
  condition_note: string | null
  data_class: DataClass
}

export interface RelatedItem {
  part_number: string
  name: string
  category: string | null
  relation: string
  relation_label: string
  interchangeability_status: string | null
  data_class: DataClass
}

export interface AssemblyItem {
  assembly_id: string
  name: string | null
  quantity: number | null
  bom_status: string | null
  identified_by: string | null
  component_count: number
  components: { part_number: string; name: string; quantity: number | null }[]
  data_class: DataClass
}

export interface SupplierItem {
  supplier_id: string
  name: string | null
  city: string | null
  country_code: string | null
  relation: string
  is_primary: boolean | null
  lead_time_days: number | null
  categories: string[]
  data_class: DataClass
}

export interface DealerItem {
  dealer_id: string
  name: string | null
  city: string | null
  country_code: string | null
  relation: string
  pickup_allowed: boolean | null
  stocking_status: string | null
  available: number | null
  data_class: DataClass
}

export interface WarehouseItem {
  warehouse_id: string
  name: string | null
  city: string | null
  country_code: string | null
  available: number | null
  stock_status: string | null
  data_class: DataClass
}

export interface InventoryView {
  state: 'CONNECTED' | 'NOT_CONNECTED'
  total_available: number | null
  warehouses: WarehouseItem[]
  dealers: DealerItem[]
  data_class: DataClass
  note: string | null
}

export interface ComplianceItem {
  requirement: string | null
  standard: string | null
  certification: string | null
  certificate_status: string | null
  valid_until: string | null
  covers: string[]
  data_class: DataClass
}

export interface ProvenanceReport {
  classification: DataClass
  source_name: string | null
  source_file: string | null
  source_sheet: string | null
  source_record_id: string | null
  confidence: string | null
  authoritative: boolean
  verification: string
  relationship_sources: { relationship: string; connected_label: string; count: number; data_class: DataClass }[]
  limitations: string[]
  last_updated: string | null
}

export interface Insight {
  key: string
  label: string
  value: number | string | null
  detail: string | null
  state: 'present' | 'gap' | 'not_connected'
}

export interface GraphNode {
  id: string
  label: string
  kind: string
  part_number: string | null
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  data_class: DataClass
}

export interface GraphView {
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
}

export type PartTab = 'overview' | 'fitment' | 'related' | 'assembly' | 'suppliers' | 'dealers' | 'inventory' | 'compliance' | 'graph' | 'provenance' | 'insights' | 'store'
