import { apiClient } from "./client"

export type RunbookMode = "guide" | "mission"
export type OsFamily = "any" | "linux" | "windows"

export interface Runbook {
  id: string
  title: string
  slug: string
  description: string | null
  triggers: string[]
  os_family: OsFamily
  mode: RunbookMode
  body: string
  budget: number | null
  priority: number
  is_active: boolean
  times_used: number
  last_used_at: string | null
  created_at: string | null
  /** The built-in procedure this one takes over from, if any. */
  shadows: string | null
}

export interface RunbookLibrary {
  runbooks: Runbook[]
  limit: number
  body_limit: number
  modes: RunbookMode[]
  os_families: OsFamily[]
  /** False for operators and viewers — a runbook needs the highest permission to write. */
  can_edit: boolean
}

export interface MatchPreview {
  matched: { slug: string; title: string; is_custom: boolean; is_mission: boolean } | null
  explanation: string
}

export type RunbookInput = {
  title: string
  description?: string | null
  triggers: string[]
  body: string
  mode: RunbookMode
  os_family: OsFamily
  budget?: number | null
  priority?: number
  is_active?: boolean
}

export async function listRunbooks(): Promise<RunbookLibrary> {
  const res = await apiClient.get<RunbookLibrary>("/api/runbooks")
  return res.data
}

export async function createRunbook(body: RunbookInput): Promise<Runbook> {
  const res = await apiClient.post<Runbook>("/api/runbooks", body)
  return res.data
}

export async function updateRunbook(id: string, body: Partial<RunbookInput>): Promise<Runbook> {
  const res = await apiClient.put<Runbook>(`/api/runbooks/${id}`, body)
  return res.data
}

export async function deleteRunbook(id: string): Promise<void> {
  await apiClient.delete(`/api/runbooks/${id}`)
}

/** Which procedure would this message use? Free — pure trigger matching, no AI call. */
export async function previewMatch(message: string, osType?: string | null): Promise<MatchPreview> {
  const res = await apiClient.post<MatchPreview>("/api/runbooks/preview-match", null, {
    params: { message, ...(osType ? { os_type: osType } : {}) },
  })
  return res.data
}

export async function builtInProcedures(): Promise<{
  procedures: { slug: string; title: string; is_mission: boolean; triggers: string[] }[]
}> {
  const res = await apiClient.get("/api/runbooks/built-in")
  return res.data
}
