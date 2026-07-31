import { apiClient } from "./client"

/** One database on the server, with what it costs in disk. */
export interface DatabaseRow {
  name: string
  size_mb: number
  tables: number | null
}

export interface DatabaseUser {
  name: string
  host: string
}

export interface DatabaseEngine {
  engine: "mysql" | "postgres"
  label: string
  version: string | null
  /** False when the engine is installed but we could not sign in — not the same as empty. */
  readable: boolean
  databases: DatabaseRow[]
  users: DatabaseUser[]
}

export interface DatabaseOverview {
  engines: DatabaseEngine[]
  reachable: boolean
}

export async function getDatabases(serverId: string): Promise<DatabaseOverview> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/databases`)
  return data
}

export async function createDatabase(
  serverId: string,
  body: { engine: string; name: string; user: string; password: string },
): Promise<{ engine: string; name: string; user: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/databases`, body)
  return data
}

export async function dropDatabase(
  serverId: string,
  body: { engine: string; name: string; confirm_name: string; drop_user?: string | null },
): Promise<{ name: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/databases/drop`, body)
  return data
}
