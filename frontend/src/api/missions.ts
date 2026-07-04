import { apiClient } from "./client"
import type { MissionStep } from "@/components/chat/MissionProgress"

// ── Types ──────────────────────────────────────────────────────────────────

export type MissionStatus =
  | "running"
  | "awaiting_approval"
  | "blocked"
  | "complete"
  | "failed"
  | "stopped"
  | "interrupted"

export interface MissionSummary {
  id: string
  server_id: string | null
  server_name: string | null
  skill: string | null
  goal: string
  status: MissionStatus
  verified: boolean | null
  summary: string | null
  steps_used: number
  budget: number
  resumable: boolean
  created_at: string | null
  updated_at: string | null
}

/** A persisted step, as stored in the transcript (looser than the live MissionStep). */
export interface MissionStepRecord {
  server?: string
  description?: string
  cmd?: string
  exit_code?: number
  output_tail?: string
  note?: string
  verify?: boolean
}

export interface MissionDetail extends MissionSummary {
  steps: MissionStepRecord[]
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export async function listMissions(serverId?: string): Promise<MissionSummary[]> {
  const { data } = await apiClient.get<MissionSummary[]>("/api/missions", {
    params: serverId ? { server_id: serverId } : undefined,
  })
  return data
}

export async function getMission(id: string): Promise<MissionDetail> {
  const { data } = await apiClient.get<MissionDetail>(`/api/missions/${id}`)
  return data
}

/** Map a persisted step record to the live MissionStep shape used by MissionProgress. */
export function recordToStep(s: MissionStepRecord, index: number): MissionStep {
  return {
    index,
    cmd: s.cmd ?? "",
    description: s.description ?? "",
    running: false,
    exitCode: s.exit_code ?? 0,
    outputTail: s.output_tail ?? "",
    note: s.note ?? "",
    serverName: s.server,
    verifying: Boolean(s.verify),
  }
}
