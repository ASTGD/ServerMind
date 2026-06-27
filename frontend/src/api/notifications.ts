import { apiClient } from "./client"

export interface Notification {
  id: string
  type: string
  title: string
  body: string | null
  status: string | null
  server_id: string | null
  ref_id: string | null
  read: boolean
  created_at: string
}

export interface NotificationList {
  items: Notification[]
  unread: number
}

export async function getNotifications(): Promise<NotificationList> {
  const { data } = await apiClient.get<NotificationList>("/api/notifications")
  return data
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiClient.post("/api/notifications/read-all")
}
