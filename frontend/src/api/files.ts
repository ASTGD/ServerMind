import { apiClient } from "./client"

// ── Types ──────────────────────────────────────────────────────────────────

export interface FileEntry {
  name: string
  path: string
  type: "file" | "dir" | "link"
  size: number | null
  permissions: string
  modified: string | null
  is_binary: boolean
}

export interface DirectoryListing {
  path: string
  parent_path: string | null
  entries: FileEntry[]
}

export interface FileContent {
  path: string
  content: string
  is_binary: boolean
  size: number
}

// ── API functions ──────────────────────────────────────────────────────────

export async function listDirectory(
  serverId: string,
  path = "/",
  showHidden = false
): Promise<DirectoryListing> {
  const res = await apiClient.get<DirectoryListing>(`/api/servers/${serverId}/files`, {
    params: { path, show_hidden: showHidden },
  })
  return res.data
}

export async function readFile(serverId: string, path: string): Promise<FileContent> {
  const res = await apiClient.get<FileContent>(`/api/servers/${serverId}/files/read`, {
    params: { path },
  })
  return res.data
}

export async function writeFile(
  serverId: string,
  path: string,
  content: string
): Promise<void> {
  await apiClient.post(`/api/servers/${serverId}/files/write`, { path, content })
}

export async function makeDirectory(serverId: string, path: string): Promise<void> {
  await apiClient.post(`/api/servers/${serverId}/files/mkdir`, { path })
}

export async function deletePath(serverId: string, path: string): Promise<void> {
  await apiClient.delete(`/api/servers/${serverId}/files`, { params: { path } })
}

export async function renamePath(
  serverId: string,
  oldPath: string,
  newPath: string
): Promise<void> {
  await apiClient.post(`/api/servers/${serverId}/files/rename`, {
    old_path: oldPath,
    new_path: newPath,
  })
}

export async function uploadFile(
  serverId: string,
  dirPath: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  const form = new FormData()
  form.append("path", dirPath)
  form.append("file", file)
  await apiClient.post(`/api/servers/${serverId}/files/upload`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
}

export function getDownloadUrl(serverId: string, path: string): string {
  // Uses apiClient's base URL; token injected via interceptor so just needs path
  const base = (import.meta.env.VITE_API_URL as string) ?? ""
  return `${base}/api/servers/${serverId}/files/download?path=${encodeURIComponent(path)}`
}
