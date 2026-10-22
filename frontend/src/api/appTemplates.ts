import { apiGet, apiPost } from './client'

/** One application template, exactly as the backend validates it (backend/app/design_studio/templates/models.py). */
export type ThemePreset = {
  id: string
  label: string
  direction: string
  colors: Record<
    | 'primary'
    | 'primary_text'
    | 'accent'
    | 'background'
    | 'surface'
    | 'surface_alt'
    | 'text'
    | 'muted'
    | 'border'
    | 'nav_background'
    | 'nav_text'
    | 'success'
    | 'warning'
    | 'danger',
    string
  >
  font_heading: 'grotesk' | 'humanist' | 'serif' | 'mono' | 'system'
  font_body: 'grotesk' | 'humanist' | 'serif' | 'system'
  density: 'compact' | 'comfortable' | 'spacious'
  radius: number
  shadow: 'none' | 'soft' | 'crisp'
  card_style: 'flat' | 'outlined' | 'elevated'
  table_style: 'lined' | 'striped' | 'dense'
  touch: boolean
}

export type TemplateComponent = {
  type:
    | 'metric_strip'
    | 'product_grid'
    | 'data_table'
    | 'detail_panel'
    | 'status_board'
    | 'timeline'
    | 'task_queue'
    | 'comparison_table'
    | 'alert_panel'
    | 'record_form'
    | 'schedule_week'
    | 'filter_bar'
  title: string
  role: string | null
  fields: string[]
  group_by: string | null
  span: 1 | 2 | 3
}

export type TemplatePage = {
  id: string
  title: string
  icon: string
  layout: string
  purpose: string
  users: string[]
  components: TemplateComponent[]
}

export type TemplateModule = {
  id: string
  name: string
  status: 'supported' | 'configurable' | 'requires_integration'
  keywords: string[]
  note: string
}

export type SampleRow = Record<string, string | number | boolean>

export type AppTemplate = {
  id: string
  version: string
  name: string
  category: string
  summary: string
  description: string
  status: 'stable' | 'preview'
  domain_ids: string[]
  app_type: string
  users: string[]
  keywords: string[]
  theme: ThemePreset
  nav_style: 'sidebar' | 'dark_sidebar' | 'topbar' | 'rail' | 'bottom_tabs'
  entity_roles: { id: string; label: string; matches: string[]; fields: string[] }[]
  pages: TemplatePage[]
  modules: TemplateModule[]
  limitations: string[]
  sample: Record<string, SampleRow[]>
}

export type CoverageStatus = 'supported' | 'configurable' | 'requires_integration' | 'unsupported'

export type TemplateRecommendation = {
  template: { id: string; name: string; version: string }
  score: number
  fit: 'strong' | 'partial' | 'weak'
  reasons: string[]
  entity_mapping: { role: string; label: string; entity_id: string; entity: string }[]
  coverage: {
    requirement_id: string
    statement: string
    status: CoverageStatus
    module: string | null
    note: string
  }[]
}

export type TemplateSelection = { template_id: string; version: string; selected_at: string }

export const listAppTemplates = (signal?: AbortSignal) =>
  apiGet<{ templates: AppTemplate[]; categories: string[] }>(
    '/design-studio/app-templates',
    {},
    signal,
  )

export const getTemplateRecommendations = (projectId: string, signal?: AbortSignal) =>
  apiGet<{ selected: TemplateSelection | null; recommendations: TemplateRecommendation[] }>(
    `/design-studio/projects/${encodeURIComponent(projectId)}/app-templates/recommendations`,
    {},
    signal,
  )

export const selectAppTemplate = (
  projectId: string,
  expectedRevision: number,
  templateId: string,
) =>
  apiPost<{ revision: number; template: TemplateSelection }>(
    `/design-studio/projects/${encodeURIComponent(projectId)}/app-template`,
    { expected_revision: expectedRevision, template_id: templateId },
  )
