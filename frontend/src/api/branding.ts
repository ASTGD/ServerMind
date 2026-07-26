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

/** A monthly recipient — an agency's client who gets this server's report by email. */
export interface ReportRecipient {
  id: string
  server_id: string
  recipient_email: string
  recipient_name: string | null
  send_day: number
  period_days: number
  is_active: boolean
  last_sent: string | null
  last_status: string | null
}

export async function listReportRecipients(): Promise<ReportRecipient[]> {
  const res = await apiClient.get<ReportRecipient[]>("/api/client-reports")
  return res.data
}

export async function addReportRecipient(body: {
  server_id: string
  recipient_email: string
  recipient_name?: string | null
  send_day?: number
  period_days?: number
}): Promise<ReportRecipient> {
  const res = await apiClient.post<ReportRecipient>("/api/client-reports", body)
  return res.data
}

export async function updateReportRecipient(
  id: string, body: Partial<Pick<ReportRecipient, "recipient_email" | "recipient_name" | "send_day" | "period_days" | "is_active">>,
): Promise<ReportRecipient> {
  const res = await apiClient.put<ReportRecipient>(`/api/client-reports/${id}`, body)
  return res.data
}

export async function deleteReportRecipient(id: string): Promise<void> {
  await apiClient.delete(`/api/client-reports/${id}`)
}

/** Send this recipient their report now. Does not consume the month's scheduled send. */
export async function sendReportNow(id: string): Promise<{ sent: boolean; to: string }> {
  const res = await apiClient.post<{ sent: boolean; to: string }>(`/api/client-reports/${id}/send`)
  return res.data
}

/** Turn the client report into Markdown — for an agency that pastes it elsewhere. */
export function clientReportToMarkdown(r: ClientReport): string {
  const company = r.branding.company_name
  const out: string[] = []
  if (company) out.push(`# ${company}`, "")
  out.push(`## ${r.server_name} — ${r.period_days}-day report`)
  out.push(`_${r.period_start} to ${r.period_end}_`, "")
  out.push(`**${r.headline}**`, "")
  for (const line of r.summary) out.push(`- ${line}`)

  out.push("", "### The numbers", "")
  out.push(`| | |`, `|---|---|`)
  out.push(`| Uptime | ${r.uptime.monitored && r.uptime.percentage !== null ? `${r.uptime.percentage}%` : "not monitored"} |`)
  out.push(`| Failed checks | ${r.uptime.outages} |`)
  out.push(`| Security score | ${r.security.score !== null ? `${r.security.score}/100 (${r.security.grade})` : "no scan yet"} |`)
  out.push(`| Malware scan | ${r.security.threat_verdict ?? "not run"} |`)
  out.push(`| Backups | ${r.backups.configured ? `${r.backups.successful} of ${r.backups.runs} succeeded` : "not configured"} |`)

  if (r.work.completed.length) {
    out.push("", "### What we did", "")
    for (const w of r.work.completed) out.push(`- ${w.goal}${w.verified ? " ✓ verified" : ""}`)
  }

  out.push("", "---", "")
  if (r.branding.footer_text) out.push(r.branding.footer_text)
  else if (company) out.push(company)
  if (r.branding.show_credit) out.push(`Monitored by ${r.branding.app_name}`)
  return out.join("\n")
}

export function clientReportFilename(serverName: string, ext: string): string {
  const safe = serverName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "server"
  return `${safe}-report.${ext}`
}
