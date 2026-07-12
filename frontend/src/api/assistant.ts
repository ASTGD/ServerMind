import { apiClient } from "./client"

export interface ThreadSummary {
  id: string
  title: string
  updated_at: string
  message_count: number
}

export interface ThreadMessage {
  role: "user" | "assistant"
  content: string
  /** A saved WORKSPACE message (finished mission / command output / artifact) — a
   *  serialized ChatMessageData so a reopened thread restores the Workspace, not just chat. */
  data?: unknown
}

export interface Thread {
  id: string
  title: string
  messages: ThreadMessage[]
  updated_at: string
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const { data } = await apiClient.get<ThreadSummary[]>("/api/assistant/threads")
  return data
}

export async function createThread(title?: string): Promise<Thread> {
  const { data } = await apiClient.post<Thread>("/api/assistant/threads", { title })
  return data
}

export async function getThread(id: string): Promise<Thread> {
  const { data } = await apiClient.get<Thread>(`/api/assistant/threads/${id}`)
  return data
}

export async function renameThread(id: string, title: string): Promise<void> {
  await apiClient.patch(`/api/assistant/threads/${id}`, { title })
}

export async function deleteThread(id: string): Promise<void> {
  await apiClient.delete(`/api/assistant/threads/${id}`)
}

export async function appendMessage(
  id: string,
  role: "user" | "assistant",
  content: string,
  data?: unknown,
): Promise<void> {
  await apiClient.post(`/api/assistant/threads/${id}/messages`, { role, content, data })
}
