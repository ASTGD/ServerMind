import { apiClient } from "./client"

export interface SetupStep {
  label: string
  slug: string
  optional: boolean
  state: "pending" | "running" | "done" | "skipped" | "failed"
  note?: string
}

export interface SetupOption {
  key: string
  title: string
  description: string
  minutes: number
  steps: { label: string; optional: boolean }[]
}

export interface Setup {
  id: string
  purpose: string
  status: "running" | "done" | "failed" | "stopped"
  steps: SetupStep[]
  current: number
  failed_step: string | null
  message: string | null
  progress: { done: number; total: number; percent: number }
  started_at: string | null
  finished_at: string | null
}

export interface SetupStatus {
  options: SetupOption[]
  /** Why this server cannot be set up — empty when it can. */
  blocked: string
  already_set_up: boolean
  latest: Setup | null
}

export async function getSetupStatus(serverId: string): Promise<SetupStatus> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/setup`)
  return data
}

export async function startSetup(
  serverId: string,
  body: { purpose: string; timezone?: string; monitoring?: boolean; force?: boolean },
): Promise<Setup> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/setup`, body)
  return data
}

export async function stopSetup(serverId: string): Promise<Setup> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/setup/stop`)
  return data
}
