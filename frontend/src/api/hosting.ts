import { apiClient } from "./client"

// ── Types ──────────────────────────────────────────────────────────────────

export interface Website {
  domain: string
  state: string | null
  php: string | null
  admin: string | null
  type: string | null
  id: number | string | null
}

export interface HostingDatabase {
  db_name: string | null
  size: number | string | null
}

export interface EmailAccount {
  email: string | null
  domain: string | null
}

export interface ActionResult {
  status: string
  detail: Record<string, unknown> | null
}

export interface CreateWebsiteBody {
  domain: string
  email?: string | null
  package?: string | null
  php?: string | null
}

export interface CreateDatabaseBody {
  domain?: string | null
  db_name: string
  db_user?: string | null
  db_password?: string | null
}

export interface CreateEmailBody {
  user: string
  domain: string
  password: string
}

// ── API functions ──────────────────────────────────────────────────────────

const base = (serverId: string) => `/api/servers/${serverId}/hosting`

export async function listWebsites(serverId: string): Promise<Website[]> {
  const res = await apiClient.get<Website[]>(`${base(serverId)}/websites`)
  return res.data
}

export async function createWebsite(serverId: string, body: CreateWebsiteBody): Promise<ActionResult> {
  const res = await apiClient.post<ActionResult>(`${base(serverId)}/websites`, body)
  return res.data
}

export async function deleteWebsite(serverId: string, domain: string): Promise<ActionResult> {
  const res = await apiClient.delete<ActionResult>(`${base(serverId)}/websites/${encodeURIComponent(domain)}`)
  return res.data
}

export async function issueSsl(serverId: string, domain: string): Promise<ActionResult> {
  const res = await apiClient.post<ActionResult>(`${base(serverId)}/websites/${encodeURIComponent(domain)}/ssl`)
  return res.data
}

export async function listDatabases(serverId: string): Promise<HostingDatabase[]> {
  const res = await apiClient.get<HostingDatabase[]>(`${base(serverId)}/databases`)
  return res.data
}

export async function createDatabase(serverId: string, body: CreateDatabaseBody): Promise<ActionResult> {
  const res = await apiClient.post<ActionResult>(`${base(serverId)}/databases`, body)
  return res.data
}

export async function listEmail(serverId: string, domain?: string): Promise<EmailAccount[]> {
  const res = await apiClient.get<EmailAccount[]>(`${base(serverId)}/email`, {
    params: domain ? { domain } : {},
  })
  return res.data
}

export async function createEmail(serverId: string, body: CreateEmailBody): Promise<ActionResult> {
  const res = await apiClient.post<ActionResult>(`${base(serverId)}/email`, body)
  return res.data
}
