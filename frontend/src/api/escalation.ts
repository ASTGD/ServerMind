import { apiClient } from "./client"

export type Channel = "email" | "sms" | "telegram" | "slack" | "webhook"
export type Severity = "critical" | "high" | "warning" | "info"

export interface EscalationStep {
  after_minutes: number
  channel: Channel
  target: string
  label: string | null
}

export interface EscalationPolicy {
  id: string
  name: string
  min_severity: Severity
  repeat_minutes: number
  max_repeats: number
  is_default: boolean
  is_active: boolean
  steps: EscalationStep[]
  /** The ladder in plain sentences, built server-side so UI and worker never disagree. */
  summary: string[]
  /** The honest ceiling on how many messages one incident can ever produce. */
  max_notifications: number
  created_at: string | null
}

export interface Incident {
  id: string
  server_id: string | null
  server_name: string | null
  source: string
  title: string
  message: string
  severity: Severity
  status: "open" | "acknowledged" | "resolved"
  notifications_sent: number
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  auto_resolved: boolean
  next_action_at: string | null
  created_at: string | null
}

export interface PagingProvider {
  provider: "twilio" | "telegram"
  configured: boolean
  verified: boolean
  monthly_limit: number | null
  sent_this_month: number
}

export interface StepInput {
  after_minutes: number
  channel: Channel
  target: string
  label?: string | null
}

export interface PolicyInput {
  name: string
  min_severity: Severity
  repeat_minutes: number
  max_repeats: number
  is_default: boolean
  is_active?: boolean
  steps: StepInput[]
}

export async function listPolicies(): Promise<EscalationPolicy[]> {
  const res = await apiClient.get<EscalationPolicy[]>("/api/escalation/policies")
  return res.data
}

export async function createPolicy(body: PolicyInput): Promise<EscalationPolicy> {
  const res = await apiClient.post<EscalationPolicy>("/api/escalation/policies", body)
  return res.data
}

export async function updatePolicy(id: string, body: Partial<PolicyInput>): Promise<EscalationPolicy> {
  const res = await apiClient.put<EscalationPolicy>(`/api/escalation/policies/${id}`, body)
  return res.data
}

export async function deletePolicy(id: string): Promise<void> {
  await apiClient.delete(`/api/escalation/policies/${id}`)
}

/** Send a test page through the policy's first step. */
export async function previewPolicy(id: string): Promise<{ sent: boolean; channel: string; to: string }> {
  const res = await apiClient.post(`/api/escalation/policies/${id}/preview`)
  return res.data
}

export async function listIncidents(status?: "active" | "open" | "resolved"): Promise<Incident[]> {
  const res = await apiClient.get<Incident[]>("/api/incidents", { params: status ? { status } : {} })
  return res.data
}

export async function acknowledgeIncident(id: string): Promise<Incident> {
  const res = await apiClient.post<Incident>(`/api/incidents/${id}/acknowledge`)
  return res.data
}

export async function resolveIncident(id: string): Promise<Incident> {
  const res = await apiClient.post<Incident>(`/api/incidents/${id}/resolve`)
  return res.data
}

export async function listProviders(): Promise<PagingProvider[]> {
  const res = await apiClient.get<PagingProvider[]>("/api/escalation/providers")
  return res.data
}

export async function setProvider(
  provider: "twilio" | "telegram",
  body: {
    account_sid?: string; auth_token?: string; from_number?: string
    bot_token?: string; monthly_limit?: number
  },
): Promise<PagingProvider> {
  const res = await apiClient.put<PagingProvider>(`/api/escalation/providers/${provider}`, body)
  return res.data
}

export async function deleteProvider(provider: "twilio" | "telegram"): Promise<void> {
  await apiClient.delete(`/api/escalation/providers/${provider}`)
}

export async function testProvider(provider: "twilio" | "telegram", to: string): Promise<void> {
  await apiClient.post(`/api/escalation/providers/${provider}/test`, null, { params: { to } })
}

/** The acknowledge link from a page. Unauthenticated by design. */
export async function acknowledgeByToken(token: string): Promise<{
  acknowledged: boolean; title?: string; status?: string; message: string
}> {
  const res = await apiClient.post(`/api/public/ack/${encodeURIComponent(token)}`)
  return res.data
}

export const CHANNEL_LABEL: Record<Channel, string> = {
  email: "Email",
  sms: "Text message",
  telegram: "Telegram",
  slack: "Slack",
  webhook: "Webhook",
}

/** What to ask for, per channel — a phone number and a webhook URL need different hints. */
export const CHANNEL_HINT: Record<Channel, string> = {
  email: "you@company.com",
  sms: "+8801712345678",
  telegram: "Telegram chat ID, e.g. 123456789",
  slack: "https://hooks.slack.com/services/…",
  webhook: "https://your-app.com/hook",
}
