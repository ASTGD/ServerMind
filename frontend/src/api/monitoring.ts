import { apiClient } from "./client"
import type { Alert } from "@/types"

// ── Types ──────────────────────────────────────────────────────────────────

export interface MetricPoint {
  id: string
  server_id: string
  cpu_percent: number | null
  ram_percent: number | null
  ram_used_mb: number | null
  ram_total_mb: number | null
  disk_percent: number | null
  disk_used_gb: number | null
  disk_total_gb: number | null
  load_1: number | null
  load_5: number | null
  load_15: number | null
  uptime_seconds: number | null
  recorded_at: string
}

export interface AlertCreateBody {
  metric: "cpu" | "ram" | "disk"
  condition: "gt" | "gte" | "lt" | "lte"
  threshold: number
  channel: "email" | "webhook" | "slack"
  channel_target: string
}

// ── Metrics ────────────────────────────────────────────────────────────────

export async function getMetricsHistory(
  serverId: string,
  hours = 24
): Promise<MetricPoint[]> {
  const res = await apiClient.get<MetricPoint[]>(
    `/api/servers/${serverId}/metrics/history`,
    { params: { hours } }
  )
  return res.data
}

// ── Alerts ─────────────────────────────────────────────────────────────────

export async function listAlerts(serverId: string): Promise<Alert[]> {
  const res = await apiClient.get<Alert[]>(`/api/servers/${serverId}/alerts`)
  return res.data
}

export async function createAlert(
  serverId: string,
  body: AlertCreateBody
): Promise<Alert> {
  const res = await apiClient.post<Alert>(`/api/servers/${serverId}/alerts`, body)
  return res.data
}

export async function updateAlert(
  alertId: string,
  body: AlertCreateBody
): Promise<Alert> {
  const res = await apiClient.put<Alert>(`/api/alerts/${alertId}`, body)
  return res.data
}

export async function deleteAlert(alertId: string): Promise<void> {
  await apiClient.delete(`/api/alerts/${alertId}`)
}

export async function toggleAlert(alertId: string): Promise<Alert> {
  const res = await apiClient.post<Alert>(`/api/alerts/${alertId}/toggle`)
  return res.data
}

export async function testAlert(alertId: string): Promise<void> {
  await apiClient.post(`/api/alerts/${alertId}/test`)
}
