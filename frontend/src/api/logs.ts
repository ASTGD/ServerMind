import { apiClient } from "./client"

/** A log file discovered on the server, labelled in plain language. */
export interface LogFile {
  path: string
  label: string
  category: string
  size_bytes: number
}

export interface LogContent {
  path: string
  content: string
  truncated: boolean
  line_count: number
}

/** Which logs exist on this server. */
export async function listLogs(serverId: string): Promise<LogFile[]> {
  const res = await apiClient.get<LogFile[]>(`/api/servers/${serverId}/logs`)
  return res.data
}

/** Read the tail of one log, optionally filtered by plain text. */
export async function readLog(
  serverId: string,
  path: string,
  lines = 200,
  search?: string,
): Promise<LogContent> {
  const res = await apiClient.get<LogContent>(`/api/servers/${serverId}/logs/read`, {
    params: { path, lines, search: search || undefined },
  })
  return res.data
}
