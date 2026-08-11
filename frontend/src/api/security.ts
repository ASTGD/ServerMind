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

// ── Threat scan (indicators of compromise) ──────────────────────────────────

export type Verdict = "clean" | "suspicious" | "at_risk" | "compromised" | "unknown"

export interface ThreatFinding {
  id: string
  title: string
  severity: Severity
  detail: string | null
  recommendation: string | null
  evidence: string | null
}

export interface SkippedCheck {
  id: string
  title: string
  reason: string
}

export interface ThreatScan {
  id: string
  server_id: string
  verdict: Verdict
  status: string
  error: string | null
  duration_ms: number | null
  counts: ScanCounts
  findings: ThreatFinding[]
  /** What the scan could read — root | sudo | none. Null on scans predating this. */
  privilege?: string | null
  /** Checks that did not run, and why. Empty means nothing was skipped. */
  skipped?: SkippedCheck[]
  /** One sentence for the customer. Null when there is nothing to say. */
  note?: string | null
  created_at: string
}

/** Threat scan history (newest first). */
export async function listThreatScans(serverId: string, limit = 10): Promise<ThreatScan[]> {
  const res = await apiClient.get<ThreatScan[]>(`/api/servers/${serverId}/security/threats`, {
    params: { limit },
  })
  return res.data
}

/** Run a fresh read-only threat scan; persists and returns it. */
export async function runThreatScan(serverId: string): Promise<ThreatScan> {
  const res = await apiClient.post<ThreatScan>(`/api/servers/${serverId}/security/threat-scan`)
  return res.data
}
