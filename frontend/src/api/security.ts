import { apiClient } from "./client"

// ── Types ──────────────────────────────────────────────────────────────────

export type Severity = "critical" | "high" | "medium" | "low" | "pass" | "info" | "unknown"
export type FindingStatus = "pass" | "fail" | "warn" | "info" | "unknown"

export interface Finding {
  id: string
  title: string
  category: string
  severity: Severity
  status: FindingStatus
  description: string
  detail: string | null
  recommendation: string | null
  fix_command: string | null
}

export interface ScanCounts {
  critical: number
  high: number
  medium: number
  low: number
  pass: number
  info: number
}

export interface SecurityScan {
  id: string
  server_id: string
  score: number
  grade: string
  status: string // "completed" | "failed"
  error: string | null
  duration_ms: number | null
  counts: ScanCounts
  findings: Finding[]
  created_at: string
}

// ── API functions ──────────────────────────────────────────────────────────

/** List recent security scans for a server (most recent first). */
export async function listSecurityScans(
  serverId: string,
  limit = 20
): Promise<SecurityScan[]> {
  const res = await apiClient.get<SecurityScan[]>(
    `/api/servers/${serverId}/security`,
    { params: { limit } }
  )
  return res.data
}

/** Run a fresh security audit. Read-only probes; persists and returns the scan. */
export async function runSecurityScan(serverId: string): Promise<SecurityScan> {
  const res = await apiClient.post<SecurityScan>(
    `/api/servers/${serverId}/security/scan`
  )
  return res.data
}
