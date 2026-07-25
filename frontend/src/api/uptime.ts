import { apiClient } from "./client"

/** A URL we probe from ServerAlly (not from the server — that is the point). */
export interface UptimeMonitor {
  id: string
  server_id: string | null
  name: string
  url: string
  method: string
  expected_status: number
  expected_keyword: string | null
  interval_seconds: number
  timeout_seconds: number
  failure_threshold: number
  is_active: boolean
  current_status: "up" | "down" | "unknown"
  last_checked: string | null
  last_status_change: string | null
  last_response_ms: number | null
  last_error: string | null
  channel: string | null
  channel_target: string | null
  created_at: string
  uptime_24h: number
  uptime_30d: number
  /** HTTPS certificate expiry, refreshed daily. Null for a plain-http monitor. */
  cert_state: "ok" | "warning" | "critical" | "expired" | "unknown" | null
  cert_days_left: number | null
  cert_expires_at: string | null
  cert_issuer: string | null
}

export interface UptimeCheck {
  id: string
  status: "up" | "down"
  http_status: number | null
  response_ms: number | null
  error: string | null
  checked_at: string
}

export interface MonitorBody {
  name: string
  url: string
  server_id?: string | null
  method?: string
  expected_status?: number
  expected_keyword?: string | null
  interval_seconds?: number
  timeout_seconds?: number
  failure_threshold?: number
  is_active?: boolean
  channel?: string | null
  channel_target?: string | null
}

export async function listMonitors(serverId?: string): Promise<UptimeMonitor[]> {
  const res = await apiClient.get<UptimeMonitor[]>("/api/uptime/monitors", {
    params: serverId ? { server_id: serverId } : undefined,
  })
  return res.data
}

/** Creates and immediately probes, so the user sees a real result at once. */
export async function createMonitor(body: MonitorBody): Promise<UptimeMonitor> {
  const res = await apiClient.post<UptimeMonitor>("/api/uptime/monitors", body)
  return res.data
}

export async function updateMonitor(id: string, body: Partial<MonitorBody>): Promise<UptimeMonitor> {
  const res = await apiClient.put<UptimeMonitor>(`/api/uptime/monitors/${id}`, body)
  return res.data
}

export async function deleteMonitor(id: string): Promise<void> {
  await apiClient.delete(`/api/uptime/monitors/${id}`)
}

/** Probe right now. */
export async function checkMonitorNow(id: string): Promise<UptimeMonitor> {
  const res = await apiClient.post<UptimeMonitor>(`/api/uptime/monitors/${id}/check`)
  return res.data
}

export async function monitorHistory(id: string, limit = 100): Promise<UptimeCheck[]> {
  const res = await apiClient.get<UptimeCheck[]>(`/api/uptime/monitors/${id}/history`, {
    params: { limit },
  })
  return res.data
}
