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
  /** The customer's OTHER servers. A database user can be allowed from one of these and
   *  nowhere else — the same rule the database-server firewall follows. */
  own_servers: { name: string; host: string }[]
}

export async function getDatabases(serverId: string): Promise<DatabaseOverview> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/databases`)
  return data
}

export async function createDatabase(
  serverId: string,
  body: {
    engine: string; name: string; user: string; password: string
    /** Which machine may sign in as this user. "localhost" means this server only. */
    host?: string
  },
): Promise<{ engine: string; name: string; user: string; host: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/databases`, body)
  return data
}

export async function dropDatabase(
  serverId: string,
  body: {
    engine: string; name: string; confirm_name: string; drop_user?: string | null
    /** In MySQL the host is part of a user's identity, so removal needs the one it was
     *  created with. */
    host?: string
  },
): Promise<{ name: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/databases/drop`, body)
  return data
}
