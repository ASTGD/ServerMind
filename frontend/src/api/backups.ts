import { apiClient } from "./client"

// ── Types ──────────────────────────────────────────────────────────────────

export type BackupType = "files" | "mysql" | "postgres"

export interface Backup {
  id: string
  server_id: string
  name: string
  backup_type: BackupType
  source: string
  dest_dir: string
  db_user: string | null
  has_db_cred: boolean
  retention: number
  cron_expression: string | null
  human_schedule: string | null
  is_active: boolean
  last_run: string | null
  last_status: string | null
  next_run: string | null
  destination_id: string | null
  destination_name: string | null
  keep_local: boolean
  created_at: string
}

export interface BackupRun {
  id: string
  backup_id: string
  server_id: string
  action: "backup" | "restore"
  status: "success" | "failed" | "running"
  artifact_path: string | null
  size_bytes: number | null
  output: string | null
  remote_key: string | null
  offsite_status: "uploaded" | "failed" | "skipped" | null
  started_at: string
  completed_at: string | null
}

export interface BackupCreateBody {
  name: string
  backup_type: BackupType
  source: string
  dest_dir?: string
  db_user?: string | null
  db_password?: string | null
  retention?: number
  cron_expression?: string | null
  human_schedule?: string | null
  is_active?: boolean
  destination_id?: string | null
  keep_local?: boolean
}

/** An offsite destination — an S3-compatible bucket. The secret key is never returned. */
export interface BackupDestination {
  id: string
  name: string
  provider: string
  bucket: string
  region: string | null
  endpoint_url: string | null
  prefix: string | null
  access_key_id: string
  last_status: "ok" | "failed" | null
  last_error: string | null
  last_checked: string | null
  created_at: string
}

export interface DestinationBody {
  name: string
  provider: string
  bucket: string
  region?: string | null
  endpoint_url?: string | null
  prefix?: string | null
  access_key_id: string
  secret_key?: string
}

export type BackupUpdateBody = Partial<BackupCreateBody>

// ── API functions ──────────────────────────────────────────────────────────

export async function listBackups(serverId: string): Promise<Backup[]> {
  const res = await apiClient.get<Backup[]>(`/api/servers/${serverId}/backups`)
  return res.data
}

export async function createBackup(serverId: string, body: BackupCreateBody): Promise<Backup> {
  const res = await apiClient.post<Backup>(`/api/servers/${serverId}/backups`, body)
  return res.data
}

export async function updateBackup(backupId: string, body: BackupUpdateBody): Promise<Backup> {
  const res = await apiClient.put<Backup>(`/api/backups/${backupId}`, body)
  return res.data
}

export async function deleteBackup(backupId: string): Promise<void> {
  await apiClient.delete(`/api/backups/${backupId}`)
}

export async function runBackup(backupId: string): Promise<BackupRun> {
  const res = await apiClient.post<BackupRun>(`/api/backups/${backupId}/run`)
  return res.data
}

export async function backupHistory(backupId: string, limit = 50): Promise<BackupRun[]> {
  const res = await apiClient.get<BackupRun[]>(`/api/backups/${backupId}/history`, {
    params: { limit },
  })
  return res.data
}

export async function restoreBackup(backupId: string, runId?: string): Promise<BackupRun> {
  const res = await apiClient.post<BackupRun>(`/api/backups/${backupId}/restore`, {
    run_id: runId ?? null,
  })
  return res.data
}


// ── Offsite destinations ───────────────────────────────────────────────────

export async function listDestinations(): Promise<BackupDestination[]> {
  const res = await apiClient.get<BackupDestination[]>("/api/backup-destinations")
  return res.data
}

/** Creates the destination — the server verifies it can WRITE to the bucket first. */
export async function createDestination(body: DestinationBody): Promise<BackupDestination> {
  const res = await apiClient.post<BackupDestination>("/api/backup-destinations", body)
  return res.data
}

export async function updateDestination(id: string, body: Partial<DestinationBody>): Promise<BackupDestination> {
  const res = await apiClient.put<BackupDestination>(`/api/backup-destinations/${id}`, body)
  return res.data
}

/** Re-check a destination now (keys rotate, buckets get deleted). */
export async function testDestination(id: string): Promise<BackupDestination> {
  const res = await apiClient.post<BackupDestination>(`/api/backup-destinations/${id}/test`)
  return res.data
}

export async function deleteDestination(id: string): Promise<void> {
  await apiClient.delete(`/api/backup-destinations/${id}`)
}
