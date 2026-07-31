import { apiClient } from "./client"

export interface CronJob {
  /** The exact line, which is what a removal matches on. */
  raw: string
  schedule: string
  command: string
  /** Plain English, or empty when the schedule is unusual enough that we won't guess. */
  description: string
  note: string | null
  /** False for a line we could not read; still shown, because it is still a job. */
  parsed: boolean
}

export interface CronUser {
  user: string
  jobs: CronJob[]
  /** Identifies the crontab this list came from; sent back with any change. */
  fingerprint: string
}

export interface CronPreset {
  id: string
  label: string
  blurb: string
  schedule: string
  command: string
  needs_path: string
}

export interface CronOverview {
  users: CronUser[]
  reachable: boolean
  presets: CronPreset[]
}

export async function getCron(serverId: string): Promise<CronOverview> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/cron`)
  return data
}

export async function addCronJob(
  serverId: string,
  body: { user: string; schedule: string; command: string; note?: string; expect?: string },
): Promise<{ description: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/cron`, body)
  return data
}

export async function removeCronJob(
  serverId: string,
  body: { user: string; raw_line: string; expect?: string },
): Promise<{ removed: string }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/cron/remove`, body)
  return data
}
