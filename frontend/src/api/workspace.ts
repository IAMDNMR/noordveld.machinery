import { apiDelete, apiGet, apiPost } from './client'

/** The signed-in user's workspace, computed by the server from the organization directory. The browser only displays it. */
export type AppStatus = 'operational' | 'in_design' | 'planned'
export type WorkspaceApp = {
  id: string
  name: string
  description: string
  domain: string
  status: AppStatus
  route: string | null
  launchable: boolean
  your_roles: string[]
  reason: string | null
  can_manage_users?: boolean
}
export type Organization = { id: string; name: string; roles: string[] }
export type Workspace = {
  user: { id: string; name: string; email: string }
  directory_configured: boolean
  platform_roles: string[]
  organizations: Organization[]
  active_organization: string | null
  permissions: string[]
  applications: WorkspaceApp[]
  activity: { at: string; actor: string; action: string; detail: string }[]
  onboarding: string[]
  journeys?: { business_user: boolean }
  /** Combinable profiles shown to the person; display only: the server enforces access independently. */
  profiles?: string[]
  can_administer?: boolean
}

export const getWorkspace = (org?: string | null, signal?: AbortSignal) =>
  apiGet<Workspace>('/workspace', { org }, signal)
export type AppGrant = { app_id: string; app_role: string }
export type InviteRequest = {
  email: string
  role?: string | null
  app_grants?: AppGrant[]
  team_id?: string | null
}
export type InvitationPreview = {
  organization: { id: string; name: string }
  email_hint: string
  role: string | null
  app_grants: AppGrant[]
  team: string | null
  expires_at: string
}
export type InvitationRow = {
  id: string
  email: string
  role: string | null
  invited_by: string
  expires_at: string
  app_grants: AppGrant[]
  status: 'pending' | 'accepted' | 'revoked' | 'expired'
}
export type Accepted = {
  org_id: string
  role: string | null
  app_grants: AppGrant[]
}

const organizationPath = (org: string) => `/workspace/organizations/${encodeURIComponent(org)}`
export const inviteMember = (org: string, request: InviteRequest) =>
  apiPost<{ token: string; expires_in_days: number }>(
    `${organizationPath(org)}/invitations`,
    request,
  )
export const previewInvitation = (token: string, signal?: AbortSignal) =>
  apiGet<InvitationPreview>('/workspace/invitations/preview', { token }, signal)
export const acceptInvitation = (token: string) =>
  apiPost<Accepted>('/workspace/invitations/accept', { token })
export const listInvitations = (org: string, signal?: AbortSignal) =>
  apiGet<InvitationRow[]>(`${organizationPath(org)}/invitations`, {}, signal)
export const revokeInvitation = (org: string, id: string) =>
  apiDelete<{ revoked: true }>(`${organizationPath(org)}/invitations/${encodeURIComponent(id)}`)
export type AuditRow = { at: string; actor: string; action: string; detail: string }
export const getAudit = (org: string, signal?: AbortSignal) =>
  apiGet<AuditRow[]>(`${organizationPath(org)}/audit`, { limit: 25 }, signal)

export const ROLE_LABEL: Record<string, string> = {
  org_admin: 'Organization administrator',
  project_owner: 'Project owner',
  business_analyst: 'Business analyst',
  process_owner: 'Process owner',
  business_approver: 'Business approver',
  designer: 'Designer',
  developer: 'Developer',
  reviewer: 'Read-only reviewer',
  platform_admin: 'Platform administrator',
  solution_architect: 'Solution architect',
  ux_designer: 'UI/UX designer',
  implementation_engineer: 'Implementation engineer',
  support_operator: 'Support operator',
}
export const STATUS_LABEL: Record<AppStatus, string> = {
  operational: 'Available',
  in_design: 'In design',
  planned: 'Planned',
}
