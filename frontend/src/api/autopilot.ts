import { apiClient } from "./client"

/** How far Ally may go on its own. */
export type AutopilotPolicy = "report_only" | "safe_fixes" | "full"

/** A standing instruction: a goal, a schedule, and a policy. */
export interface AutopilotTask {
  id: string
  server_id: string | null
  name: string
  goal: string
  policy: AutopilotPolicy
  policy_label: string
  cron_expression: string
  human_schedule: string | null
  is_active: boolean
  channel: string | null
  channel_target: string | null
  notify_on_change_only: boolean
  last_run: string | null
  last_status: string | null
  next_run: string | null
  created_at: string
}

export interface AutopilotBody {
  name: string
  goal: string
  server_id?: string | null
  policy?: AutopilotPolicy
  cron_expression: string
  human_schedule?: string | null
  is_active?: boolean
  channel?: string | null
  channel_target?: string | null
  notify_on_change_only?: boolean
}

export async function listAutopilotTasks(): Promise<AutopilotTask[]> {
  const res = await apiClient.get<AutopilotTask[]>("/api/autopilot/tasks")
  return res.data
}

export async function createAutopilotTask(body: AutopilotBody): Promise<AutopilotTask> {
  const res = await apiClient.post<AutopilotTask>("/api/autopilot/tasks", body)
  return res.data
}

export async function updateAutopilotTask(
  id: string,
  body: Partial<AutopilotBody>,
): Promise<AutopilotTask> {
  const res = await apiClient.put<AutopilotTask>(`/api/autopilot/tasks/${id}`, body)
  return res.data
}

export async function deleteAutopilotTask(id: string): Promise<void> {
  await apiClient.delete(`/api/autopilot/tasks/${id}`)
}

/** Run now — so you can watch what it does before trusting it nightly. */
export async function runAutopilotTask(id: string): Promise<AutopilotTask> {
  const res = await apiClient.post<AutopilotTask>(`/api/autopilot/tasks/${id}/run`)
  return res.data
}
