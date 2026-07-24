import { apiClient } from "./client"

/** The MCP endpoint a customer connects their own AI client to (docs/MCP-SERVER-PLAN.md). */
export interface McpInfo {
  /** The full MCP URL to add in Claude Code / Desktop / ChatGPT. */
  url: string
  /** Whether the MCP feature (OAuth-protected) is on. */
  enabled: boolean
}

/** One connected AI client (an OAuth grant). Credential-free. */
export interface McpConnection {
  grant_id: string
  client_id: string
  client_name: string | null
  scopes: string[]
  connected_at: string
  last_active: string
}

export async function getMcpInfo(): Promise<McpInfo> {
  const res = await apiClient.get<McpInfo>("/api/mcp/info")
  return res.data
}

export async function listMcpConnections(): Promise<McpConnection[]> {
  const res = await apiClient.get<McpConnection[]>("/api/mcp/connections")
  return res.data
}

/** Revoke a connection — the client loses access immediately. */
export async function revokeMcpConnection(grantId: string): Promise<void> {
  await apiClient.delete(`/api/mcp/connections/${grantId}`)
}

/** One action a connected AI took over MCP. `status` runs running → ok|blocked|error. */
export interface McpActivityItem {
  id: string
  client_name: string
  tool: string
  server_name: string | null
  status: "running" | "ok" | "blocked" | "error"
  label: string
  command: string | null
  exit_code: number | null
  detail: string | null
  started_at: string
  finished_at: string | null
}

/** Recent MCP actions, newest first. Poll (~2s) to watch activity live. */
export async function listMcpActivity(): Promise<McpActivityItem[]> {
  const res = await apiClient.get<McpActivityItem[]>("/api/mcp/activity")
  return res.data
}
