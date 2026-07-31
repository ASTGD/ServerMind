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

/** What can be installed on a server, served by the backend so the list has one home. */
export interface SiteTypeField {
  name: string
  label: string
  default: string
  required: boolean
  /** A password or token — the form must not show it in clear text. */
  secret: boolean
}

export interface SiteType {
  id: string
  group: string
  label: string
  blurb: string
  /** One of the few offered before "show all". Decided by the backend. */
  popular: boolean
  est_seconds: number | null
  fields: SiteTypeField[]
}

export interface SiteCatalogue {
  groups: { id: string; label: string; blurb: string }[]
  types: SiteType[]
}

export async function getSiteCatalogue(): Promise<SiteCatalogue> {
  const res = await apiClient.get<SiteCatalogue>("/api/site-types")
  return res.data
}

export async function createSite(
  serverId: string,
  body: { domain: string; site_type: string; variables: Record<string, string> },
): Promise<Site & { run_id: string }> {
  const res = await apiClient.post<Site & { run_id: string }>(
    `/api/servers/${serverId}/sites`, body,
  )
  return res.data
}

export interface Site {
  id: string
  domain: string
  aliases: string[]
  server_id: string | null
  server_name: string | null
  doc_root: string | null
  source: string
  app_type: string
  app_version: string | null
  has_ssl: boolean
  is_present: boolean
  /** installing | live | failed — a site is now created, not only discovered. */
  status?: string
  /** Why the install failed, in words the customer can act on. */
  install_error?: string | null
  /** What was ASKED for, as opposed to what a scan concluded is there. */
  requested_type?: string | null
  first_seen: string | null
  last_seen: string | null
  /** From the uptime monitor watching this domain, if one exists. */
  uptime: SiteUptime | null
  /** Whether this domain's email will actually arrive, if it is being checked. */
  mail?: SiteMail | null
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

/** The last mail-health result for a site, joined into the list server-side. */
export interface SiteMail {
  id: string
  verdict: "ok" | "at risk" | "failing" | "unknown"
  score: number
  summary: string | null
  findings: { key: string; severity: string; title: string; detail: string; fix: string }[]
  checked: string | null
}

export interface SiteDetail extends Site {
  server: {
    id: string
    name: string
    connection_type: string
    panel_type: string | null
  }
}

/** One site, read by id so the page works from a link or a bookmark. */
export async function getSite(siteId: string): Promise<SiteDetail> {
  const { data } = await apiClient.get(`/api/sites/${siteId}`)
  return data
}

/** Put an application onto a site that already exists. */
export async function installOnSite(
  siteId: string,
  body: { site_type: string; variables: Record<string, string> },
): Promise<{ run_id: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/install`, body)
  return data
}

export interface SslReadiness {
  ready: boolean
  has_ssl: boolean
  points_to: string[]
  server_addresses: string[]
  record: { type: string; name: string; value: string }
  reason: string | null
  /** Plain-English why-not, with the fix. Null when it is ready. */
  message: string | null
}

export async function getSslReadiness(siteId: string): Promise<SslReadiness> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/ssl-readiness`)
  return data
}

export async function turnOnSsl(siteId: string): Promise<{ run_id: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/ssl`)
  return data
}
