import { apiClient } from "./client"

export interface Branding {
  company_name: string | null
  logo_url: string | null
  primary_color: string | null
  support_url: string | null
  support_email: string | null
  footer_text: string | null
  hide_serverally_branding: boolean
}

/** The branding a VISITOR receives — `show_credit` is already resolved for us. */
export interface PublicBranding {
  company_name: string | null
  logo_url: string | null
  primary_color: string | null
  support_url: string | null
  support_email: string | null
  footer_text: string | null
  show_credit: boolean
  app_name: string
}

export interface ClientReport {
  server_name: string
  period_days: number
  period_start: string
  period_end: string
  tone: "good" | "warn" | "bad"
  headline: string
  summary: string[]
  uptime: {
    percentage: number | null
    outages: number
    monitored: boolean
    monitors: { name: string; uptime: number; checked: number }[]
  }
  security: {
    grade: string | null
    score: number | null
    scanned_at: string | null
    threat_verdict: string | null
  }
  backups: { configured: boolean; runs: number; successful: number; healthy: boolean | null }
  work: { completed: { goal: string; verified: boolean }[]; completed_count: number; commands_run: number }
  branding: PublicBranding
  generated_at: string
}

export async function getBranding(): Promise<Branding> {
  const res = await apiClient.get<Branding>("/api/branding")
  return res.data
}

export async function updateBranding(body: Partial<Branding>): Promise<Branding> {
  const res = await apiClient.put<Branding>("/api/branding", body)
  return res.data
}

export async function getClientReport(serverId: string, days = 30): Promise<ClientReport> {
  const res = await apiClient.get<ClientReport>(`/api/servers/${serverId}/client-report`, {
    params: { days },
  })
  return res.data
}
