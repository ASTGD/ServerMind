import { apiClient } from "./client"

export interface SiteUptime {
  monitor_id: string
  status: string | null
  last_checked: string | null
  response_ms: number | null
  error: string | null
  cert_days_left: number | null
  cert_state: string | null
  /** The domain does not resolve. Classified server-side so nothing here matches a sentence. */
  unresolved?: boolean
  /** Whether this domain has EVER answered. What separates "never pointed here" from "it broke". */
  ever_up?: boolean
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

export async function listServerSites(
  serverId: string,
): Promise<{ sites: Site[]; count: number; stale_because?: string | null }> {
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

/**
 * Where a site's files live, who owns them, which PHP it runs, how big it is.
 *
 * Every field is optional because every one of them is something the server might not be
 * able to answer — a static site has no PHP, an unreadable folder has no size. A missing
 * field is shown as unknown; it is never filled with a plausible default.
 */
export interface SiteFacts {
  reachable: boolean
  config_path?: string | null
  server_path?: string | null
  public_path?: string | null
  system_user?: string | null
  size_kb?: number | null
  php_version?: string | null
}

/** Read live from the server, because all of it changes without us. */
export async function getSiteFacts(siteId: string): Promise<SiteFacts> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/details`)
  return data
}

/** Put an application onto a site that already exists. */
export async function installOnSite(
  siteId: string,
  body: {
    site_type: string
    variables: Record<string, string>
    /** Delete what is on the site first. Needs `confirm` to be the site's own domain. */
    replace?: boolean
    confirm?: string
  },
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

export async function removeSite(
  siteId: string,
  body: { confirm_domain: string; drop_database: boolean },
): Promise<{ run_id: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/remove`, body)
  return data
}

export interface SiteLogFile {
  path: string
  label: string
  category: string
  size_bytes: number
}

export async function getSiteLogs(siteId: string): Promise<{ logs: SiteLogFile[]; reachable: boolean; server_id: string }> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/logs`)
  return data
}

export interface SiteCronJob {
  raw: string
  schedule: string
  command: string
  description: string
  note: string | null
  parsed: boolean
  user: string
  /** The crontab as it was when we read it, so an edit made behind our back is refused. */
  fingerprint?: string
}

/** The job this application needs and does not have. Absent once something is doing it. */
export interface SiteCronSuggestion {
  schedule: string
  command: string
  title: string
  why: string
}

export interface SiteCronList {
  jobs: SiteCronJob[]
  reachable: boolean
  server_id: string
  suggested: SiteCronSuggestion | null
}

/** What a database we just made looks like. The password is here ONCE and nowhere else. */
/** A database on the server named after this site — evidence, not proof. */
export interface NamedAfterSite {
  engine: string
  name: string
}

export interface NewSiteDatabase {
  engine: string
  name: string
  user: string
  password: string
  host: string
}

export async function createSiteDatabase(
  siteId: string,
  body: { engine?: string; name?: string; user?: string; password?: string } = {},
): Promise<NewSiteDatabase> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/database`, body)
  return data
}

export async function getSiteCron(siteId: string): Promise<SiteCronList> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/cron`)
  return data
}

/** Schedule a job for this site. Which account runs it is decided on the server. */
export async function addSiteCron(
  siteId: string,
  body: { schedule: string; command: string; note?: string; expect?: string | null },
): Promise<{ user: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/cron`, body)
  return data
}

export async function removeSiteCron(
  siteId: string,
  body: { user: string; raw_line: string; expect?: string | null },
): Promise<unknown> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/cron/remove`, body)
  return data
}

/**
 * The application running on a site — WordPress today, whatever the registry gains next.
 *
 * `app` is null when there is nothing we have tools for, which is how the menu knows not to
 * offer a section rather than offering an empty one.
 */
export interface WpPlugin {
  name: string
  title: string
  status: string
  version: string
  update_available: boolean
  update_version: string
}

export interface WpTheme {
  name: string
  status: string
  version: string
  update_available: boolean
  update_version: string
}

/** Laravel's state: not what is installed, but what condition the deployment is in. */
export interface LaravelState {
  version?: string
  php_version?: string
  environment?: string
  debug?: boolean
  /** The one that matters most — a debug page prints the database password to visitors. */
  debug_in_production?: boolean
  pending_migrations?: number
  /** False when we could not reach the database; not the same as "none pending". */
  migrations_known?: boolean
  cache_config?: boolean
  cache_routes?: boolean
  cache_events?: boolean
  storage_link?: boolean
  queue_worker?: boolean
  scheduler?: boolean
}

/** What PHP a site actually runs under, read through the site's own pool. */
export interface PhpState {
  version?: string
  sapi?: string
  cli_version?: string
  settings?: { name: string; label: string; value: string }[]
  extensions?: string[]
}

/** The long-running program behind a domain — Node, Next.js, Python, Go. */
export interface WebAppState {
  runtime?: string
  command?: string
  user?: string
  directory?: string
  active?: boolean
  state?: string
  enabled?: boolean
  restarts?: number
  memory_mb?: number | null
  pid?: string
  port?: string
  /** null when there is no port to check. */
  listening?: boolean | null
  proxy_port?: string
  unit?: string
  log?: string
  /** Why the site is not working, even when the program is "running". */
  problems?: { level: string; text: string }[]
}

export interface SiteApp extends LaravelState, PhpState, WebAppState {
  app: string | null
  label?: string
  ok?: boolean
  reason?: string
  /** False when the files are there but nobody finished the WordPress setup. */
  set_up?: boolean
  path?: string
  runs_as?: string
  cli?: string
  core_version?: string
  core_update?: string
  core_update_known?: boolean
  title?: string
  site_url?: string
  plugins?: WpPlugin[]
  themes?: WpTheme[]
  admins?: { id: string; login: string; email: string; name: string }[]
  maintenance?: boolean
  debug?: boolean
  updates_waiting?: number
}

export async function getSiteApp(siteId: string): Promise<SiteApp> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/app`)
  return data
}

/** One named action. The caller never composes a command. */
export async function runSiteAppAction(
  siteId: string,
  action: string,
  target = "",
): Promise<{ output: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/app/action`, { action, target })
  return data
}

/**
 * Deploying code to a site.
 *
 * A site has at most one repository connected: "deploy my code here" is one question about
 * one website, and two targets pointing at the same folder would be two things fighting
 * over one symlink.
 */
export interface SiteDeployTarget {
  id: string
  repo: string
  branch: string
  path: string
  web_dir: string
  auto_deploy: boolean
  /** Whether the web server has actually been pointed at the deployed code. */
  serving: boolean
  current_release: string | null
  last_status: string | null
  last_deployed_at: string | null
  served_from: string
}

export interface SiteDeployInfo {
  target: SiteDeployTarget | null
  /** Worked out from the site, so the form does not ask what we already know. */
  suggested?: { path: string; web_dir: string }
  can_deploy: boolean
}

export async function getSiteDeploy(siteId: string): Promise<SiteDeployInfo> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/deploy`)
  return data
}

export async function connectSiteDeploy(
  siteId: string,
  body: {
    repo: string; branch: string; web_dir: string
    build_commands?: string[]; after_commands?: string[]; shared_paths?: string[]
  },
): Promise<{ id: string; path: string; served_from: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/deploy`, body)
  return data
}

/** Point the web server at the deployed code. The one step a visitor can see. */
export async function serveSiteFromDeploy(
  siteId: string,
): Promise<{ serving: boolean; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/deploy/serve`)
  return data
}

/**
 * The database this site uses.
 *
 * There is no password in this shape and there cannot be: the probe reads one on the
 * server to make the connection attempt and returns a single word.
 */
export interface SiteDatabase {
  ok: boolean
  reason?: string
  name?: string
  user?: string
  host?: string
  /** Whether the site could actually connect. Only meaningful when `tested`. */
  reachable?: boolean
  /** False when there was no client to test with — not the same as failing. */
  tested?: boolean
  tables?: number | null
  size_mb?: number | null
  /** Only when the site's own settings name no database: one on the server that shares
   *  this site's name. Evidence it is this site's, not proof — the settings decide. */
  named_after_site?: NamedAfterSite | null
}

export async function getSiteDatabase(siteId: string): Promise<SiteDatabase> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/database`)
  return data
}

/** Which PHP runs this site, and what else this server has. */
export interface SitePhp {
  ok: boolean
  reason?: string
  version?: string | null
  config?: string
  versions: string[]
  running?: string[]
  cli_default?: string | null
}

export async function getSitePhp(siteId: string): Promise<SitePhp> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/php`)
  return data
}

/** Change which PHP serves this site. The config to rewrite is resolved on the server. */
export async function switchSitePhp(
  siteId: string, version: string,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/php`, { version })
  return data
}

/** A process kept running for this site. */
export interface SiteDaemon {
  unit: string
  name: string
  running: boolean
  state: string
  at_boot: boolean
  description: string
  command: string
}

export interface SiteDaemonSuggestion {
  name: string
  command: string
  title: string
  why: string
}

export async function getSiteDaemons(siteId: string): Promise<{
  daemons: SiteDaemon[]; suggested: SiteDaemonSuggestion | null; working_dir: string
}> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/daemons`)
  return data
}

export async function addSiteDaemon(
  siteId: string, body: { name: string; command: string; description?: string },
): Promise<{ ok: boolean; unit: string; message: string; log?: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/daemons`, body)
  return data
}

export async function actOnSiteDaemon(
  siteId: string, unit: string, action: "start" | "stop" | "restart" | "remove",
): Promise<{ ok: boolean; output: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/daemons/action`, { unit, action })
  return data
}

/** A redirect on one site. `type` is nginx's own rewrite flag, which is what it becomes. */
export interface SiteRedirectRule {
  id: string
  from: string
  to: string
  type: "redirect" | "permanent"
  type_label: string
  /** Whether it is really in the web server's configuration, not just recorded here. */
  is_applied: boolean
}

export async function listSiteRedirects(siteId: string): Promise<{
  ok: boolean; reason: string | null; redirects: SiteRedirectRule[]
}> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/redirects`)
  return data
}

export async function addSiteRedirect(
  siteId: string,
  body: { redirect_from: string; redirect_to: string; redirect_type: string },
): Promise<SiteRedirectRule> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/redirects`, body)
  return data
}

export async function removeSiteRedirect(
  siteId: string, redirectId: string,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await apiClient.delete(`/api/sites/${siteId}/redirects/${redirectId}`)
  return data
}

/** This site's own web-server configuration file, as it is on the machine. */
export async function getSiteVhost(siteId: string): Promise<{
  ok: boolean; reason?: string; path?: string; content?: string
}> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/vhost`)
  return data
}

export async function saveSiteVhost(
  siteId: string, content: string,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/vhost`, { content })
  return data
}


export interface SiteAliases {
  domain: string
  aliases: string[]
}

export async function getSiteAliases(siteId: string): Promise<SiteAliases> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/aliases`)
  return data
}

export async function addSiteAlias(
  siteId: string, alias: string,
): Promise<{ aliases: string[]; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/aliases`, { alias })
  return data
}

export async function removeSiteAlias(
  siteId: string, alias: string,
): Promise<{ aliases: string[]; message: string }> {
  const { data } = await apiClient.delete(
    `/api/sites/${siteId}/aliases/${encodeURIComponent(alias)}`)
  return data
}


export interface SiteAuth {
  users: string[]
  enabled: boolean
  /** Empty means the whole site is behind the password. */
  path: string
}

export async function getSiteAuth(siteId: string): Promise<SiteAuth> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/auth`)
  return data
}

export async function setSiteAuth(
  siteId: string, body: { name: string; password: string; path?: string },
): Promise<SiteAuth & { message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/auth`, body)
  return data
}

export async function removeSiteAuth(
  siteId: string, name: string,
): Promise<SiteAuth & { message: string }> {
  const { data } = await apiClient.delete(
    `/api/sites/${siteId}/auth/${encodeURIComponent(name)}`)
  return data
}


export interface SuspendCode { value: number; label: string; note: string }

export interface SiteSuspend {
  suspended: boolean
  message: string
  reason: string
  code: number
  codes: SuspendCode[]
}

export async function getSiteSuspend(siteId: string): Promise<SiteSuspend> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/suspend`)
  return data
}

export async function setSiteSuspend(
  siteId: string,
  body: { suspended: boolean; message?: string; reason?: string; code?: number },
): Promise<{ suspended: boolean; code: number; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/suspend`, body)
  return data
}


export async function resetSitePermissions(siteId: string): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/reset-permissions`)
  return data
}


export interface SiteCache {
  enabled: boolean
  supported: boolean
  reason: string
}

export async function getSiteCache(siteId: string): Promise<SiteCache> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/cache`)
  return data
}

export async function setSiteCache(
  siteId: string, enabled: boolean,
): Promise<{ enabled: boolean; message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/cache`, { enabled })
  return data
}

export async function purgeSiteCache(siteId: string): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/cache/purge`)
  return data
}


/** Where this site can be copied to, and what a copy leaves behind. */
export interface CloneOptions {
  domain: string
  server_id: string
  servers: { id: string; name: string; host: string; same: boolean }[]
  /** Both wordings — which applies depends on the server picked, which only the form knows. */
  database_note: { same: string | null; other: string | null }
}

export interface CloneStarted {
  id: string
  domain: string
  run_id: string
  size: string
  files: number
  database_note: string | null
}

export async function getSiteCloneOptions(siteId: string): Promise<CloneOptions> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/clone`)
  return data
}

export async function cloneSite(
  siteId: string, domain: string, serverId: string,
): Promise<CloneStarted> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/clone`,
                                        { domain, server_id: serverId })
  return data
}


/** A Laravel site's `.env` — every credential the application owns. */
export interface SiteEnv {
  path: string
  content: string
  settings: { key: string; value: string; secret: boolean; critical: boolean }[]
  exists: boolean
  owner: string
  mode: string
  bytes: number
  config_cached: boolean
  web_readable: boolean
  web_status: string
  /** Present only when the file is downloadable from the internet. Show it first. */
  warning: string | null
}

export async function getSiteEnv(siteId: string): Promise<SiteEnv> {
  const { data } = await apiClient.get(`/api/sites/${siteId}/env`)
  return data
}

export async function saveSiteEnv(
  siteId: string, content: string,
): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/api/sites/${siteId}/env`, { content })
  return data
}
