import { apiClient } from "./client"

/** Request cancellation of a running AI-chat command execution (durable path). */
export async function cancelCommand(logId: string): Promise<void> {
  await apiClient.post(`/api/commands/${logId}/cancel`)
}

export { apiClient }
