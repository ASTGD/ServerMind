import { apiClient } from "./client"

// ── Types ──────────────────────────────────────────────────────────────────

export type Role = "viewer" | "operator" | "admin"

export interface TeamMember {
  id: string
  owner_id: string
  member_id: string | null
  role: Role | null
  invited_email: string | null
  invite_token: string | null
  invite_accepted: boolean
  created_at: string
}

export interface ServerAccess {
  id: string
  server_id: string
  can_execute: boolean
  can_view_logs: boolean
}

export interface ServerAccessItem {
  server_id: string
  can_execute: boolean
  can_view_logs: boolean
}

// ── API functions ──────────────────────────────────────────────────────────

export async function listTeam(): Promise<TeamMember[]> {
  const res = await apiClient.get<TeamMember[]>("/api/team")
  return res.data
}

export async function inviteMember(email: string, role: Role): Promise<TeamMember> {
  const res = await apiClient.post<TeamMember>("/api/team/invite", { email, role })
  return res.data
}

export async function updateMemberRole(memberId: string, role: Role): Promise<TeamMember> {
  const res = await apiClient.put<TeamMember>(`/api/team/${memberId}`, { role })
  return res.data
}

export async function removeMember(memberId: string): Promise<void> {
  await apiClient.delete(`/api/team/${memberId}`)
}

export async function getMemberAccess(memberId: string): Promise<ServerAccess[]> {
  const res = await apiClient.get<ServerAccess[]>(`/api/team/${memberId}/access`)
  return res.data
}

export async function setMemberAccess(
  memberId: string,
  items: ServerAccessItem[]
): Promise<ServerAccess[]> {
  const res = await apiClient.put<ServerAccess[]>(`/api/team/${memberId}/access`, { items })
  return res.data
}

export async function acceptInvite(token: string): Promise<{ message: string; owner_id: string; role: string | null }> {
  const res = await apiClient.post(`/api/team/accept/${token}`)
  return res.data
}
