import { apiClient } from "./client"
import type { Server, ServerMetrics } from "@/types"

export interface ServerCreateBody {
  name: string
  host: string
  port: number
  username: string
  auth_type: "password" | "key"
  connection_type: "ssh" | "winrm" | "hosting" | "rdp"
  panel_type?: string | null
  category?: string | null
  credential: string
  tags?: string[] | null
  notes?: string | null
}

export interface ServerUpdateBody {
  name?: string
  tags?: string[] | null
  notes?: string | null
  category?: string | null
  host?: string
  port?: number
  username?: string
  auth_type?: "password" | "key"
  credential?: string
}

export interface TestConnectionResult {
  ok: boolean
  latency_ms: number
  error: string | null
  host_key_changed?: boolean
}

export interface TrustKeyResult {
  ok: boolean
  fingerprint: string | null
  error: string | null
}

export interface DetectOsResult {
  os_type: string
  os_version: string
  arch: string
  pretty_name: string
}

export async function listServers(): Promise<Server[]> {
  const { data } = await apiClient.get<Server[]>("/api/servers")
  return data
}

export async function createServer(body: ServerCreateBody): Promise<Server> {
  const { data } = await apiClient.post<Server>("/api/servers", body)
  return data
}

export async function getServer(id: string): Promise<Server> {
  const { data } = await apiClient.get<Server>(`/api/servers/${id}`)
  return data
}

export async function updateServer(id: string, body: ServerUpdateBody): Promise<Server> {
  const { data } = await apiClient.put<Server>(`/api/servers/${id}`, body)
  return data
}

export async function deleteServer(id: string): Promise<void> {
  await apiClient.delete(`/api/servers/${id}`)
}

export async function testConnection(id: string): Promise<TestConnectionResult> {
  const { data } = await apiClient.post<TestConnectionResult>(`/api/servers/${id}/test`)
  return data
}

/** Trust the server's current host key (after a legitimate rebuild) — re-pins it. */
export async function trustKey(id: string): Promise<TrustKeyResult> {
  const { data } = await apiClient.post<TrustKeyResult>(`/api/servers/${id}/trust-key`)
  return data
}

export async function detectOs(id: string): Promise<DetectOsResult> {
  const { data } = await apiClient.post<DetectOsResult>(`/api/servers/${id}/detect`)
  return data
}

export async function getMetrics(id: string): Promise<ServerMetrics> {
  const { data } = await apiClient.get<ServerMetrics>(`/api/servers/${id}/metrics`)
  return data
}

export interface ActiveRun {
  id: string
  playbook_id: string | null
  user_script_id: string | null
  started_at: string | null
}

/** Playbook/script runs still in progress on a server (so a window can rejoin one). */
export async function getActiveRuns(serverId: string): Promise<ActiveRun[]> {
  const { data } = await apiClient.get<ActiveRun[]>(`/api/servers/${serverId}/active-runs`)
  return data
}

export interface ActiveRunSummary {
  id: string
  server_id: string
  server_name: string
  title: string
  playbook_id: string | null
  user_script_id: string | null
  started_at: string | null
}

/** All of the user's in-progress installs across every server (dashboard panel). */
export async function getAllActiveRuns(): Promise<ActiveRunSummary[]> {
  const { data } = await apiClient.get<ActiveRunSummary[]>("/api/active-runs")
  return data
}

/**
 * What ServerAlly is to one server: its control panel, or the thing watching a real one.
 *
 * Derived on the server from what is actually installed, never stored — see
 * `server_role.py`. `can_choose` is only true while the machine is still clean.
 */
export interface ServerRole {
  applies: boolean
  role: "undecided" | "serverally" | "panel" | null
  can_choose: boolean
  panel: string | null
  panel_label: string | null
  why: string | null
  /** The control-panel installers this deployment actually ships. */
  panels: { id: string; slug: string; title: string; description: string | null }[]
  /** A live look at the machine. Null when we could not reach it. */
  found: {
    os: string | null
    web_servers: string[]
    databases: string[]
    containers: string[]
    runtimes: string[]
    panels: string[]
  } | null
  /** Nothing on it that either path would fight with. Null when the look failed. */
  is_clean: boolean | null
  scan_failed?: boolean
}

export async function getServerRole(serverId: string): Promise<ServerRole> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/setup/role`)
  return data
}
