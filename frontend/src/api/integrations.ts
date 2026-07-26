import { apiClient } from "./client"

export interface ApiKey {
  id: string
  name: string
  /** The visible start of the key, so several keys can be told apart. */
  prefix: string
  scopes: string[]
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
  created_at: string | null
}

/** Only the create response carries the full key — it is never retrievable again. */
export interface NewApiKey extends ApiKey {
  key: string
  warning: string
}

export interface WebhookEndpoint {
  id: string
  name: string
  url: string
  events: string[]
  is_active: boolean
  failure_count: number
  disabled_reason: string | null
  last_delivery_at: string | null
  last_status: string | null
  created_at: string | null
}

export interface WebhookDelivery {
  id: string
  event: string
  status: string
  attempts: number
  http_status: number | null
  error: string | null
  delivered_at: string | null
  created_at: string | null
}

export interface WebhookInfo {
  events: string[]
  signature: { header: string; format: string; how_to_verify: string }
  delivery: {
    retries: number
    backoff_minutes: number[]
    expects: string
    disabled_after: number
  }
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await apiClient.get<ApiKey[]>("/api/api-keys")
  return res.data
}

export async function createApiKey(body: {
  name: string; scopes: string[]; expires_in_days?: number | null
}): Promise<NewApiKey> {
  const res = await apiClient.post<NewApiKey>("/api/api-keys", body)
  return res.data
}

export async function revokeApiKey(id: string): Promise<ApiKey> {
  const res = await apiClient.delete<ApiKey>(`/api/api-keys/${id}`)
  return res.data
}

export async function listWebhooks(): Promise<WebhookEndpoint[]> {
  const res = await apiClient.get<WebhookEndpoint[]>("/api/webhooks")
  return res.data
}

export async function webhookInfo(): Promise<WebhookInfo> {
  const res = await apiClient.get<WebhookInfo>("/api/webhooks/events")
  return res.data
}

export async function createWebhook(body: {
  name: string; url: string; events: string[]
}): Promise<WebhookEndpoint & { secret: string }> {
  const res = await apiClient.post<WebhookEndpoint & { secret: string }>("/api/webhooks", body)
  return res.data
}

export async function updateWebhook(
  id: string, body: Partial<Pick<WebhookEndpoint, "name" | "url" | "events" | "is_active">>,
): Promise<WebhookEndpoint> {
  const res = await apiClient.put<WebhookEndpoint>(`/api/webhooks/${id}`, body)
  return res.data
}

export async function deleteWebhook(id: string): Promise<void> {
  await apiClient.delete(`/api/webhooks/${id}`)
}

export async function testWebhook(id: string): Promise<{ sent: boolean; http_status: number }> {
  const res = await apiClient.post(`/api/webhooks/${id}/test`)
  return res.data
}

export async function webhookSecret(id: string): Promise<string> {
  const res = await apiClient.get<{ secret: string }>(`/api/webhooks/${id}/secret`)
  return res.data.secret
}

export async function webhookDeliveries(id: string): Promise<WebhookDelivery[]> {
  const res = await apiClient.get<WebhookDelivery[]>(`/api/webhooks/${id}/deliveries`)
  return res.data
}

/** Plain-language names for the events, so the picker doesn't read like a database. */
export const EVENT_LABEL: Record<string, string> = {
  "incident.opened": "Something needs attention",
  "incident.acknowledged": "Someone took an incident",
  "incident.resolved": "An incident was resolved",
  "uptime.down": "A site went down",
  "uptime.up": "A site came back",
  "threat.detected": "A server looks compromised",
  "playbook.finished": "A playbook finished",
  "mission.finished": "Ally finished a mission",
  "backup.failed": "A backup failed",
  "certificate.expiring": "An HTTPS certificate is expiring",
}
