import { apiClient } from "./client"
import type { PublicBranding } from "./branding"

export interface StatusPageItem {
  monitor_id: string
  display_name: string | null
  monitor_name: string
}

export interface StatusPage {
  id: string
  slug: string
  title: string
  description: string | null
  support_url: string | null
  is_public: boolean
  items: StatusPageItem[]
  created_at: string
}

export interface StatusPageBody {
  slug: string
  title: string
  description?: string | null
  support_url?: string | null
  is_public?: boolean
  items?: { monitor_id: string; display_name?: string | null }[]
}

/** What a VISITOR sees — deliberately contains no URL, server or error detail. */
export interface PublicStatus {
  branding: PublicBranding
  title: string
  description: string | null
  support_url: string | null
  status: "up" | "down" | "unknown"
  message: string
  items: {
    name: string
    status: "up" | "down" | "unknown"
    uptime_24h: number
    uptime_window: number
    history: { date: string; status: "up" | "down" | "none" }[]
  }[]
  history_days: number
  checked_at: string
}

export async function listStatusPages(): Promise<StatusPage[]> {
  const res = await apiClient.get<StatusPage[]>("/api/status-pages")
  return res.data
}

export async function createStatusPage(body: StatusPageBody): Promise<StatusPage> {
  const res = await apiClient.post<StatusPage>("/api/status-pages", body)
  return res.data
}

export async function updateStatusPage(id: string, body: Partial<StatusPageBody>): Promise<StatusPage> {
  const res = await apiClient.put<StatusPage>(`/api/status-pages/${id}`, body)
  return res.data
}

export async function deleteStatusPage(id: string): Promise<void> {
  await apiClient.delete(`/api/status-pages/${id}`)
}

/** Fetch a public page. No auth — used by the public route. */
export async function getPublicStatus(slug: string): Promise<PublicStatus> {
  const res = await apiClient.get<PublicStatus>(`/api/public/status/${slug}`)
  return res.data
}
