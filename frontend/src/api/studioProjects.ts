import { apiGet, apiPost } from './client'
import type { StageKey } from './studio'

export type ProjectStatus = 'active' | 'archived' | 'trashed'
export type ProjectAction = 'rename' | 'archive' | 'trash' | 'restore' | 'delete'
export type DashboardProject = {
  release?: { id: string; revision: number; created: string; test_status: string } | null
  design_reviewed?: boolean
  runtime?: { running: boolean; url?: string; stale?: boolean; revision?: number }
  id: string
  name: string
  description: string
  domain: string
  revision: number
  status: ProjectStatus
  stage: StageKey
  stage_label: string
  reviewed: number
  stage_count: number
  errors: number
  warnings: number
  design_approval: 'none' | 'valid' | 'stale'
  screens: number
  entities: number
  updated_at: string
  can_edit: boolean
  can_delete?: boolean
}
export type DashboardData = {
  can_create?: boolean
  projects: DashboardProject[]
  counts: {
    reviewed?: number
    active: number
    archived: number
    trashed: number
    needs_attention: number
    approved: number
  }
  activity: {
    project_id: string
    project_name: string
    revision: number
    actor: string
    operation: string
    at: string
  }[]
}
export const getProjectDashboard = (signal?: AbortSignal) =>
  apiGet<DashboardData>('/design-studio/project-dashboard', {}, signal)
export const manageProject = (project: DashboardProject, action: ProjectAction, name?: string) =>
  apiPost<{ id: string; revision: number; status: ProjectStatus | 'deleted' }>(
    `/design-studio/projects/${encodeURIComponent(project.id)}/manage`,
    { expected_revision: project.revision, action, ...(name ? { name } : {}) },
  )
