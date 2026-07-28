import { apiClient } from "./client"

/** A service we watch on a server — nginx, MySQL, a queue worker. */
export interface ServiceMonitor {
  id: string
  server_id: string
  server_name: string | null
  unit: string
  label: string
  is_active: boolean
  status: "up" | "down" | "unknown"
  state: string | null
  last_checked: string | null
  last_error: string | null
  auto_restart: boolean
  max_restarts: number
  restart_window_seconds: number
  restart_count: number
  /** True once we've stopped trying to restart — something keeps killing it. */
  gave_up: boolean
  last_restart_at: string | null
  failure_threshold: number
}

/** A service found on the server, offered for watching. */
export interface DiscoveredService {
  label: string
  unit: string
  state: string
  running: boolean
  watched: boolean
}

export interface MonitorInput {
  unit: string
  label: string
  failure_threshold?: number
  auto_restart?: boolean
  max_restarts?: number
  restart_window_seconds?: number
  is_active?: boolean
}

export async function listServiceMonitors(): Promise<{
  monitors: ServiceMonitor[]; count: number; down: number
}> {
  const { data } = await apiClient.get("/api/service-monitors")
  return data
}

export async function listForServer(serverId: string): Promise<{
  monitors: ServiceMonitor[]; count: number
}> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/service-monitors`)
  return data
}

/** Read-only look at what's installed. Nothing is changed on the server. */
export async function discoverServices(serverId: string): Promise<{
  server: string; services: DiscoveredService[]; count: number
}> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/services/discover`)
  return data
}

export async function watchService(
  serverId: string, body: MonitorInput,
): Promise<ServiceMonitor> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/service-monitors`, body)
  return data
}

export async function updateServiceMonitor(
  id: string, body: MonitorInput,
): Promise<ServiceMonitor> {
  const { data } = await apiClient.put(`/api/service-monitors/${id}`, body)
  return data
}

/** Clear a give-up after fixing whatever kept crashing the service. */
export async function resetServiceMonitor(id: string): Promise<ServiceMonitor> {
  const { data } = await apiClient.post(`/api/service-monitors/${id}/reset`)
  return data
}

export async function deleteServiceMonitor(id: string): Promise<void> {
  await apiClient.delete(`/api/service-monitors/${id}`)
}
