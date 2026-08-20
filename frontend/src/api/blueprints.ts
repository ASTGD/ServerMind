import { apiClient } from "./client"

/** One step of a blueprint run — the checklist row the screen draws. */
export interface BlueprintStep {
  key: string
  label: string
  state: "pending" | "running" | "done" | "failed" | "skipped" | "waiting"
  note: string
  optional?: boolean
  started_at?: string
  finished_at?: string
}

export interface BlueprintRun {
  id: string
  server_id: string
  server_name: string | null
  key: string
  title: string
  inputs: Record<string, string>
  status: "running" | "done" | "failed" | "stopped"
  current: number
  steps: BlueprintStep[]
  steps_done: number
  steps_total: number
  message: string | null
  found: string[]
  left_for_you: string[]
  source: string
  created_at: string | null
  finished_at: string | null
}

export interface BlueprintInfo {
  key: string
  title: string
  description: string
  needs: { name: string; label: string; required: boolean; choices: string[] }[]
  steps: string[]
  leaves_for_you: string[]
  does_not_do: string[]
}

export async function listBlueprints(): Promise<BlueprintInfo[]> {
  const { data } = await apiClient.get("/api/blueprints")
  return data
}

export async function startBlueprint(
  serverId: string, key: string, inputs: Record<string, string>,
): Promise<BlueprintRun> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/blueprints`, { key, inputs })
  return data
}

export async function listRuns(serverId?: string): Promise<BlueprintRun[]> {
  const { data } = await apiClient.get("/api/blueprints/runs", {
    params: serverId ? { server_id: serverId } : {},
  })
  return data
}

export async function getRun(id: string): Promise<BlueprintRun> {
  const { data } = await apiClient.get(`/api/blueprints/runs/${id}`)
  return data
}

export async function stopRun(id: string): Promise<BlueprintRun> {
  const { data } = await apiClient.post(`/api/blueprints/runs/${id}/stop`)
  return data
}
