import { apiClient } from "./client"
import type { Playbook, PlaybookDetail, PlaybookRun } from "@/types"

export interface ListPlaybooksParams {
  os_family?: "linux" | "windows" | "both"
  category?: string
  q?: string
}

export async function listPlaybooks(params?: ListPlaybooksParams): Promise<Playbook[]> {
  const query = new URLSearchParams()
  if (params?.os_family) query.set("os_family", params.os_family)
  if (params?.category) query.set("category", params.category)
  if (params?.q) query.set("q", params.q)
  const qs = query.toString()
  const res = await apiClient.get<Playbook[]>(`/api/playbooks${qs ? `?${qs}` : ""}`)
  return res.data
}

export async function listCategories(): Promise<string[]> {
  const res = await apiClient.get<string[]>("/api/playbooks/categories")
  return res.data
}

export async function getPlaybook(id: string): Promise<PlaybookDetail> {
  const res = await apiClient.get<PlaybookDetail>(`/api/playbooks/${id}`)
  return res.data
}

export async function getPlaybookRun(runId: string): Promise<PlaybookRun> {
  const res = await apiClient.get<PlaybookRun>(`/api/playbooks/runs/${runId}`)
  return res.data
}

/** Request cancellation of a running playbook execution. */
export async function cancelPlaybookRun(runId: string): Promise<void> {
  await apiClient.post(`/api/playbooks/runs/${runId}/cancel`)
}

export interface FleetRun {
  run_id: string
  server_id: string
  server_name: string
}

/** Run a playbook on several servers at once — one background run per server. */
export async function runMulti(
  playbookId: string,
  serverIds: string[],
  variables: Record<string, string>,
): Promise<{ runs: FleetRun[] }> {
  const { data } = await apiClient.post<{ runs: FleetRun[] }>(
    `/api/playbooks/${playbookId}/run-multi`,
    { server_ids: serverIds, variables },
  )
  return data
}

export interface RunStatus {
  id: string
  status: string
  server_id: string
}

/** Current status of a batch of runs (for the fleet batch view). */
export async function getRunsStatus(runIds: string[]): Promise<RunStatus[]> {
  const { data } = await apiClient.post<RunStatus[]>("/api/playbooks/runs/status", { run_ids: runIds })
  return data
}
