import { apiClient } from "./client"
import type { UserScript, GenerateScriptResult } from "@/types"

export interface GenerateScriptRequest {
  request: string
  os_family: "linux" | "windows" | "both"
  save?: boolean
  user_language?: string
}

export interface UserScriptCreateBody {
  title: string
  description?: string | null
  script_type: string
  script_content: string
  variables?: unknown[] | null
  tags?: string[] | null
}

export async function generateScript(body: GenerateScriptRequest): Promise<GenerateScriptResult> {
  const res = await apiClient.post<GenerateScriptResult>("/api/scripts/generate", body)
  return res.data
}

export async function listScripts(): Promise<UserScript[]> {
  const res = await apiClient.get<UserScript[]>("/api/scripts")
  return res.data
}

export async function getScript(id: string): Promise<UserScript> {
  const res = await apiClient.get<UserScript>(`/api/scripts/${id}`)
  return res.data
}

export async function createScript(body: UserScriptCreateBody): Promise<UserScript> {
  const res = await apiClient.post<UserScript>("/api/scripts", body)
  return res.data
}

export async function updateScript(id: string, body: UserScriptCreateBody): Promise<UserScript> {
  const res = await apiClient.put<UserScript>(`/api/scripts/${id}`, body)
  return res.data
}

export async function deleteScript(id: string): Promise<void> {
  await apiClient.delete(`/api/scripts/${id}`)
}
