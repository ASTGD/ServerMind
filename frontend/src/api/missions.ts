import { apiClient } from "./client"
import type { MissionStep, MissionResult } from "@/components/chat/MissionProgress"

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
  /** Owner-facing outcome card {subject, headline, found, did, left} — null until the
   *  mission produced one. Present on finished missions; this is what a Report renders. */
  result: MissionResult | null
  steps_used: number
  budget: number
  resumable: boolean
  /** Whether an "Explain this incident" narrative has already been generated. */
  has_incident_report?: boolean
  created_at: string | null
  updated_at: string | null
}

/** One entry in the incident timeline (a date/time + what happened, plain-language). */
export interface IncidentTimelineEntry {
  when: string
  what: string
}

/** The AI-generated incident narrative ("Explain this incident") — synthesized from the
 *  mission's durable transcript. Every field may be empty; render what's present. */
export interface IncidentReport {
  headline: string
  severity: "" | "low" | "medium" | "high" | "critical"
  how_they_got_in: string
  timeline: IncidentTimelineEntry[]
  impact: string
  done: string[]
  left: string[]
  caveat: string
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
  /** The AI incident narrative, if one has been generated (null otherwise). */
  incident_report?: IncidentReport | null
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

/** "Explain this incident" — generate (or fetch the cached) plain-language narrative for a
 *  finished mission. Cached server-side; pass refresh to regenerate. Costs 1 AI action. */
export async function generateIncidentReport(id: string, refresh = false): Promise<IncidentReport> {
  const { data } = await apiClient.post<IncidentReport>(
    `/api/missions/${id}/incident-report`,
    null,
    refresh ? { params: { refresh: true } } : undefined,
  )
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
