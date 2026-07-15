import { apiClient } from "./client"

/** One AI-chat command log — the full record behind an activity feed entry. */
export interface CommandLog {
  id: string
  server_id: string
  user_input: string
  ai_plan: Record<string, unknown> | null
  commands: { cmd?: string; description?: string; risk_level?: string }[] | null
  output: string | null
  status: string | null
  ai_explanation: string | null
  risk_level: string | null
  execution_ms: number | null
  created_at: string
}

/** Fetch the full command log (request, plan, commands, output, explanation). */
export async function getCommand(logId: string): Promise<CommandLog> {
  const { data } = await apiClient.get<CommandLog>(`/api/commands/${logId}`)
  return data
}

/** Request cancellation of a running AI-chat command execution (durable path). */
export async function cancelCommand(logId: string): Promise<void> {
  await apiClient.post(`/api/commands/${logId}/cancel`)
}

export { apiClient }
