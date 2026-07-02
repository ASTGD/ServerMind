import { apiClient } from "./client"

/** One note Ally saved (server fact, user preference, or lesson). */
export interface AllyMemory {
  id: string
  server_id: string | null
  kind: "fact" | "preference" | "lesson" | string
  content: string
  created_at: string
  updated_at: string
}

/** What Ally remembers about me (user-scoped notes). */
export async function listMyMemories(): Promise<AllyMemory[]> {
  const res = await apiClient.get<AllyMemory[]>("/api/memories")
  return res.data
}

/** What Ally remembers about one server. */
export async function listServerMemories(serverId: string): Promise<AllyMemory[]> {
  const res = await apiClient.get<AllyMemory[]>(`/api/servers/${serverId}/memories`)
  return res.data
}

/** Forget one note. */
export async function deleteMemory(memoryId: string): Promise<void> {
  await apiClient.delete(`/api/memories/${memoryId}`)
}
