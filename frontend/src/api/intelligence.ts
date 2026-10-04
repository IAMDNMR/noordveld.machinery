import { apiGet, apiPost } from './client'
import type {
  AssemblyItem,
  ComplianceItem,
  EntityDetail,
  DealerItem,
  FitmentItem,
  GraphView,
  Insight,
  InventoryView,
  PartOverview,
  ProvenanceReport,
  QueryResponse,
  RelatedItem,
  SupplierItem,
  Suggestion,
} from './intelligenceTypes'

const part = (key: string, tail = '') => `/intelligence/parts/${encodeURIComponent(key)}${tail}`

export const askQuestion = (question: string, selected: { kind: string; key: string }[] = [], limit = 12, signal?: AbortSignal): Promise<QueryResponse> =>
  apiPost<QueryResponse>('/intelligence/query', { question, selected, limit }, signal)

export const getSuggestions = (signal?: AbortSignal): Promise<Suggestion[]> => apiGet<Suggestion[]>('/intelligence/suggestions', {}, signal)

export const getPartOverview = (key: string, signal?: AbortSignal): Promise<PartOverview> => apiGet<PartOverview>(part(key), {}, signal)
export const getPartFitment = (key: string, signal?: AbortSignal): Promise<FitmentItem[]> => apiGet<FitmentItem[]>(part(key, '/fitment'), {}, signal)
export const getPartRelated = (key: string, signal?: AbortSignal): Promise<RelatedItem[]> => apiGet<RelatedItem[]>(part(key, '/relationships'), {}, signal)
export const getPartAssemblies = (key: string, signal?: AbortSignal): Promise<AssemblyItem[]> => apiGet<AssemblyItem[]>(part(key, '/assemblies'), {}, signal)
export const getPartSuppliers = (key: string, signal?: AbortSignal): Promise<SupplierItem[]> => apiGet<SupplierItem[]>(part(key, '/suppliers'), {}, signal)
export const getPartDealers = (key: string, signal?: AbortSignal): Promise<DealerItem[]> => apiGet<DealerItem[]>(part(key, '/dealers'), {}, signal)
export const getPartInventory = (key: string, signal?: AbortSignal): Promise<InventoryView> => apiGet<InventoryView>(part(key, '/inventory'), {}, signal)
export const getPartCompliance = (key: string, signal?: AbortSignal): Promise<ComplianceItem[]> => apiGet<ComplianceItem[]>(part(key, '/compliance'), {}, signal)
export const getPartProvenance = (key: string, signal?: AbortSignal): Promise<ProvenanceReport> => apiGet<ProvenanceReport>(part(key, '/provenance'), {}, signal)
export const getPartInsights = (key: string, signal?: AbortSignal): Promise<Insight[]> => apiGet<Insight[]>(part(key, '/insights'), {}, signal)
export const getPartGraph = (key: string, signal?: AbortSignal): Promise<GraphView> => apiGet<GraphView>(part(key, '/graph'), {}, signal)

/** Detail of a graph node that is not a part. */
export const getEntity = (kind: string, id: string, signal?: AbortSignal): Promise<EntityDetail> =>
  apiGet<EntityDetail>(`/intelligence/entities/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, {}, signal)
