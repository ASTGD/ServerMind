import { apiClient } from "./client"

export interface MailFinding {
  key: string
  severity: "critical" | "warning" | "info"
  title: string
  detail: string
  fix: string
}

export interface MailDomain {
  id: string
  domain: string
  verdict: "ok" | "at risk" | "failing" | "unknown"
  score: number
  summary: string | null
  findings: MailFinding[]
  has_mx: boolean
  spf: string | null
  dkim_selector: string | null
  dmarc: string | null
  sending_ip: string | null
  last_checked: string | null
}

export async function listMailHealth(): Promise<{
  domains: MailDomain[]; count: number; failing: number
}> {
  const { data } = await apiClient.get("/api/mail")
  return data
}

/** Start checking domains. Empty list means every website the customer has. */
export async function watchMail(domains: string[] = []): Promise<{
  added: number; message: string
}> {
  const { data } = await apiClient.post("/api/mail/watch", { domains })
  return data
}

export async function checkMailNow(recordId: string): Promise<MailDomain> {
  const { data } = await apiClient.post(`/api/mail/${recordId}/check`)
  return data
}
