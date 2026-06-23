import { apiClient } from "./client"
import type { AuditEntry } from "@/types"

/** The current user's recent security/account audit events (newest first). */
export async function listAudit(limit = 25): Promise<AuditEntry[]> {
  const { data } = await apiClient.get<AuditEntry[]>("/api/audit", { params: { limit } })
  return data
}
