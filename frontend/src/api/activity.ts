import { apiClient } from "./client"
import type { ActivityItem } from "@/types"

/** Unified recent activity (AI commands + playbook/script runs) for the user. */
export async function listActivity(limit = 50): Promise<ActivityItem[]> {
  const { data } = await apiClient.get<ActivityItem[]>("/api/activity", {
    params: { limit },
  })
  return data
}
