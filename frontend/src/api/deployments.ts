import { apiClient } from "./client"

export interface DeployTarget {
  id: string
  server_id: string
  server_name: string | null
  name: string
  repo: string
  branch: string
  path: string
  environment: string
  shared_paths: string[]
  build_commands: string[]
  after_commands: string[]
  auto_deploy: boolean
  keep_releases: number
  current_release: string | null
  last_status: string | null
  last_deployed_at: string | null
  webhook_url: string
  /** Only ever present on create, or from the deliberate "reveal" call. */
  webhook_secret?: string
}

export interface DeployRun {
  id: string
  release: string | null
  kind: string
  trigger: string
  status: string
  failed_step: string | null
  log: string | null
  started_at: string | null
  finished_at: string | null
}

export interface TargetInput {
  name: string
  repo: string
  branch: string
  path: string
  environment: string
  shared_paths: string[]
  build_commands: string[]
  after_commands: string[]
  auto_deploy: boolean
  keep_releases: number
}

export async function listDeployTargets(): Promise<{ targets: DeployTarget[]; count: number }> {
  const { data } = await apiClient.get("/api/deploy/targets")
  return data
}

export async function createDeployTarget(
  serverId: string, body: TargetInput,
): Promise<DeployTarget> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/deploy/targets`, body)
  return data
}

export async function updateDeployTarget(
  id: string, body: TargetInput,
): Promise<DeployTarget> {
  const { data } = await apiClient.put(`/api/deploy/targets/${id}`, body)
  return data
}

export async function deleteDeployTarget(id: string): Promise<void> {
  await apiClient.delete(`/api/deploy/targets/${id}`)
}

export async function revealWebhookSecret(id: string): Promise<{ webhook_secret: string }> {
  const { data } = await apiClient.get(`/api/deploy/targets/${id}/secret`)
  return data
}

export async function listReleases(
  id: string,
): Promise<{ releases: string[]; current: string | null }> {
  const { data } = await apiClient.get(`/api/deploy/targets/${id}/releases`)
  return data
}

export async function deployNow(id: string): Promise<{ run_id: string; status: string }> {
  const { data } = await apiClient.post(`/api/deploy/targets/${id}/deploy`)
  return data
}

export async function rollback(id: string): Promise<{ run_id: string; status: string }> {
  const { data } = await apiClient.post(`/api/deploy/targets/${id}/rollback`)
  return data
}

export async function listDeployRuns(id: string): Promise<{ runs: DeployRun[]; count: number }> {
  const { data } = await apiClient.get(`/api/deploy/targets/${id}/runs`)
  return data
}

export async function getDeployRun(runId: string): Promise<DeployRun> {
  const { data } = await apiClient.get(`/api/deploy/runs/${runId}`)
  return data
}
