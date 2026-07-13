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
