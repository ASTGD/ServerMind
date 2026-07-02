import { apiClient } from "./client"

/** This month's Ally-action usage for the signed-in user. */
export interface MyUsage {
  plan: string
  used: number
  limit: number
  /** ISO date the allowance resets (first of next month for now). */
  resets_at: string
  /** Whether the quota wall actually blocks (cloud) or usage is informational (self-hosted/dev). */
  enforced: boolean
}

export async function getMyUsage(): Promise<MyUsage> {
  const res = await apiClient.get<MyUsage>("/api/usage/me")
  return res.data
}
