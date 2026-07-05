import { apiClient } from "./client"

export type FleetSeverity = "critical" | "high" | "medium" | "low" | "info"

export interface FleetAction {
  kind: "chat" | "page"
  label: string
  seed?: string
  path?: string
}

export interface FleetFinding {
  id: string
  severity: FleetSeverity
  title: string
  detail: string
  penalty: number
  action: FleetAction
}

export interface ServerHealth {
  server_id: string
  name: string
  score: number
  grade: string
  status: string
  headline: string
  findings: FleetFinding[]
  needs_attention: boolean
}

export interface FleetSummary {
  total: number
  needs_attention: number
  critical_findings: number
  worst_grade: string
}

export interface FleetHealth {
  servers: ServerHealth[]
  summary: FleetSummary
}

export async function getFleetHealth(): Promise<FleetHealth> {
  const { data } = await apiClient.get<FleetHealth>("/api/fleet/health")
  return data
}
