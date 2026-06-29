import { apiClient } from "./client"
import type { PlaybookAccessInfo } from "@/types"

/** One thing ServerMind installed on a server (from our own run history). */
export interface InstalledItem {
  run_id: string
  playbook_slug: string
  playbook_title: string
  category: string | null
  installed_at: string | null
  access: PlaybookAccessInfo | null
  variables: Record<string, string>
}

/** Live read-only inventory of a server. */
export interface ScanResult {
  supported: boolean
  os: string | null
  web_servers: string[]
  databases: string[]
  runtimes: string[]
  containers: string[]
  panels: string[]
  ports: string[]
}

/** What ServerMind installed here, with re-derived access cards (secrets masked). */
export async function getInstalled(serverId: string): Promise<InstalledItem[]> {
  const { data } = await apiClient.get<{ items: InstalledItem[] }>(
    `/api/servers/${serverId}/installed`,
  )
  return data.items
}

/** Run a live read-only scan of the server for installed software. */
export async function scanServer(serverId: string): Promise<ScanResult> {
  const { data } = await apiClient.post<ScanResult>(`/api/servers/${serverId}/installed/scan`)
  return data
}
