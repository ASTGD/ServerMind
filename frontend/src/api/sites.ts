import { apiClient } from "./client"

export interface SiteUptime {
  monitor_id: string
  status: string | null
  last_checked: string | null
  response_ms: number | null
  error: string | null
  cert_days_left: number | null
  cert_state: string | null
}

export interface Site {
  id: string
  domain: string
  aliases: string[]
  server_id: string
  server_name: string | null
  doc_root: string | null
  source: string
  app_type: string
  app_version: string | null
  has_ssl: boolean
  is_present: boolean
  first_seen: string | null
  last_seen: string | null
  /** From the uptime monitor watching this domain, if one exists. */
  uptime: SiteUptime | null
}

export interface SiteList {
  sites: Site[]
  count: number
  servers_scanned: number
  /** SSH servers with no scan yet — so the page can say "scan these" rather than "no sites". */
  never_scanned: { id: string; name: string }[]
}

export interface ScanResult {
  server: string
  found: number
  added: number
  updated: number
  gone: number
  truncated: boolean
  note: string | null
}

export async function listSites(params: {
  q?: string; server_id?: string; include_gone?: boolean
} = {}): Promise<SiteList> {
  const res = await apiClient.get<SiteList>("/api/sites", { params })
  return res.data
}

export async function scanServerSites(serverId: string): Promise<ScanResult> {
  const res = await apiClient.post<ScanResult>(`/api/servers/${serverId}/sites/scan`)
  return res.data
}

export async function listServerSites(serverId: string): Promise<{ sites: Site[]; count: number }> {
  const res = await apiClient.get(`/api/servers/${serverId}/sites`)
  return res.data
}

export const APP_LABEL: Record<string, string> = {
  wordpress: "WordPress",
  laravel: "Laravel",
  php: "PHP",
  static: "Static files",
  unknown: "Unknown",
}

/** Track a website the customer owns — optionally one on a host we do not manage. */
export async function addSite(
  body: { domain: string; server_id?: string | null; watch?: boolean },
): Promise<{ site: Site; watching: boolean; message: string }> {
  const { data } = await apiClient.post("/api/sites", body)
  return data
}

/** Start checking sites we already know about. Empty list means "all of them". */
export async function watchSites(
  siteIds: string[] = [],
): Promise<{ watching: number; message: string }> {
  const { data } = await apiClient.post("/api/sites/watch", { site_ids: siteIds })
  return data
}

export async function forgetSite(siteId: string): Promise<void> {
  await apiClient.delete(`/api/sites/${siteId}`)
}
