import { apiGet, apiPost } from './client'
import type { ApplicationDefinition } from './applicationDefinition'

export const generateFrontend = (id: string, revision: number, designBrief: string) =>
  apiPost<{ definition: ApplicationDefinition; checks: string[] }>(
    `/design-studio/projects/${encodeURIComponent(id)}/frontend/generate`,
    { expected_revision: revision, design_brief: designBrief },
  )

/** A project's interface: the schema-driven screens ("baseline") unless a model-generated interface replaces them. */
export type FrontendPreview = {
  html: string
  current: boolean
  revision: number
  checks: string[]
  kind: 'baseline' | 'generated'
  screens?: { workflows: number; records: number; roles: number; steps: number }
}

export const getFrontendPreview = (id: string, signal?: AbortSignal) =>
  apiGet<FrontendPreview>(
    `/design-studio/projects/${encodeURIComponent(id)}/frontend/preview`,
    {},
    signal,
  )

export const getFrontendProgress = (id: string, signal?: AbortSignal) =>
  apiGet<{
    progress: { phase: string; file?: string; attempt?: number; round?: number } | null
    result?: {
      status: 'saved' | 'failed'
      revision: number
      message?: string
      diagnostics?: string
      design_brief?: string
    } | null
  }>(`/design-studio/projects/${encodeURIComponent(id)}/frontend/progress`, {}, signal)

export type ApplicationBlueprint = {
  revision: number
  modules: { id: string; title: string; surface_ids: string[] }[]
  surfaces: { id: string; title: string; kind: string; entity_ids: string[]; step_ids: string[] }[]
  requirements: {
    id: string
    statement: string
    status: 'planned' | 'needs_design'
    resolution: string | null
  }[]
}

export const getApplicationBlueprint = (id: string, signal?: AbortSignal) =>
  apiGet<ApplicationBlueprint>(
    `/design-studio/projects/${encodeURIComponent(id)}/frontend/blueprint`,
    {},
    signal,
  )
