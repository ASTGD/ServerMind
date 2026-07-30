import { apiClient } from "./client"

/** Where the customer wants to be told things — named once, reused everywhere. */
export type ChannelKind = "email" | "slack" | "telegram" | "sms"

export interface NotificationChannel {
  id: string
  kind: ChannelKind
  label: string
  is_active: boolean
  verified_at: string | null
  last_error: string | null
  last_used_at: string | null
  created_at: string | null
  /**
   * Only the parts that are a destination rather than a credential.
   *
   * A Slack webhook URL and a Telegram bot token never come back from the server, so this
   * is empty or partial by design — not a field the UI should try to prefill an edit with.
   */
  details: Record<string, string>
}

export async function listChannels(): Promise<NotificationChannel[]> {
  const res = await apiClient.get<NotificationChannel[]>("/api/channels")
  return res.data
}

export async function createChannel(body: {
  kind: ChannelKind
  label: string
  config: Record<string, string>
}): Promise<NotificationChannel> {
  const res = await apiClient.post<NotificationChannel>("/api/channels", body)
  return res.data
}

export async function testChannel(id: string): Promise<NotificationChannel> {
  const res = await apiClient.post<NotificationChannel>(`/api/channels/${id}/test`)
  return res.data
}

export async function deleteChannel(id: string): Promise<void> {
  await apiClient.delete(`/api/channels/${id}`)
}
