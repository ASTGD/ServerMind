import { apiClient } from "./client"

export type AiProvider = "anthropic" | "openai" | "gemini" | "openai_compatible" | "servermind"

export interface AiSettings {
  provider: AiProvider
  model: string
  base_url: string
  has_key: boolean
  source: "settings" | "env"
}

/** Current instance AI provider config (the key itself is never returned). */
export async function getAiSettings(): Promise<AiSettings> {
  const { data } = await apiClient.get<AiSettings>("/api/settings/ai")
  return data
}

export interface AiSettingsUpdate {
  provider: AiProvider
  api_key?: string // blank keeps the existing key
  model?: string
  base_url?: string
}

/** Save the AI provider config and apply it live. */
export async function updateAiSettings(body: AiSettingsUpdate): Promise<AiSettings> {
  const { data } = await apiClient.put<AiSettings>("/api/settings/ai", body)
  return data
}

export interface AiTestResult {
  ok: boolean
  reply?: string
  error?: string
}

/** Send a tiny prompt to confirm the configured key + model work. */
export async function testAiSettings(): Promise<AiTestResult> {
  const { data } = await apiClient.post<AiTestResult>("/api/settings/ai/test")
  return data
}
