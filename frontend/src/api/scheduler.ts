import { apiClient } from "./client"
import type { ScheduledTask } from "@/types"

// ── Request bodies ─────────────────────────────────────────────────────────

export interface ScheduledTaskCreateBody {
  title: string
  task_type: "command" | "playbook" | "user_script"
  payload: Record<string, string>
  cron_expression?: string | null
  human_schedule?: string | null
}

export interface ParseScheduleResult {
  cron_expression: string
  human_description: string
}

// ── API functions ──────────────────────────────────────────────────────────

export async function listSchedules(serverId: string): Promise<ScheduledTask[]> {
  const res = await apiClient.get<ScheduledTask[]>(`/api/servers/${serverId}/schedules`)
  return res.data
}

export async function createSchedule(
  serverId: string,
  body: ScheduledTaskCreateBody
): Promise<ScheduledTask> {
  const res = await apiClient.post<ScheduledTask>(`/api/servers/${serverId}/schedules`, body)
  return res.data
}

export async function updateSchedule(
  taskId: string,
  body: ScheduledTaskCreateBody
): Promise<ScheduledTask> {
  const res = await apiClient.put<ScheduledTask>(`/api/schedules/${taskId}`, body)
  return res.data
}

export async function deleteSchedule(taskId: string): Promise<void> {
  await apiClient.delete(`/api/schedules/${taskId}`)
}

export async function toggleSchedule(taskId: string): Promise<ScheduledTask> {
  const res = await apiClient.post<ScheduledTask>(`/api/schedules/${taskId}/toggle`)
  return res.data
}

export async function runNow(taskId: string): Promise<ScheduledTask> {
  const res = await apiClient.post<ScheduledTask>(`/api/schedules/${taskId}/run-now`)
  return res.data
}

export async function parseSchedule(input: string): Promise<ParseScheduleResult> {
  const res = await apiClient.post<ParseScheduleResult>("/api/parse-schedule", { input })
  return res.data
}
