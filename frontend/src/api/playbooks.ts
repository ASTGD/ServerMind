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
