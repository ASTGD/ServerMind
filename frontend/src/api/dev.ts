import { apiClient } from "./client"

/**
 * Dev Door API (docs/EVAL-DRIVEN-DEV.md) — admin-only. The dry-run plans a chat message
 * exactly as Ally would and returns the full Trace WITHOUT executing anything.
 */

export interface DryRunTrace {
  input: {
    message: string
    server: {
      id: string
      name: string
      os_type: string | null
      connection_type: string
    }
    ally_mode: string | null
    language: string
  }
  context: {
    skill: string | null
    skill_menu_offered: boolean
    has_live_snapshot: boolean
    has_scout: boolean
    has_server_profile: boolean
    has_memories: boolean
    other_servers: string | null
    use_skill_requested: string | null
  }
  prompt: {
    system: string
    volatile: string
  }
  output: {
    raw: string
    parsed: Record<string, unknown>
  }
  meta: {
    models: string[]
    calls: number
    input_tokens: number
    output_tokens: number
    cache_read_tokens: number
    cache_write_tokens: number
    cost_usd: number
    escalated: boolean
    retried_trimmed: boolean
  }
}

/** Plan a message as Ally would — returns the full trace, never executes a command. */
export async function dryRun(server_id: string, message: string): Promise<DryRunTrace> {
  const { data } = await apiClient.post<DryRunTrace>("/api/dev/dry-run", {
    server_id,
    message,
  })
  return data
}

// ── Eval runner + case capture (Phase 3) ──────────────────────────────────────

export const EVAL_CATEGORIES = [
  "skill-routing",
  "safety-block",
  "safety-confirm",
  "safety-allow",
  "readonly-allow",
  "readonly-deny",
] as const

export type EvalCategory = (typeof EVAL_CATEGORIES)[number]

export interface EvalRunResult {
  summary: { total: number; passed: number; ok: boolean }
  by_category: { category: string; passed: number; total: number }[]
  failures: {
    category: string
    input: string
    expected: string
    got: string
    error: string | null
    source: "corpus" | "captured"
  }[]
  captured: {
    id: string
    category: string
    input: string
    expected: string
    os: string
    note: string | null
    got: string
    passed: boolean
  }[]
}

export interface EvalCase {
  id: string
  category: string
  input: string
  expected: string
  os: string
  note: string | null
  created_at: string | null
}

export interface CaptureCaseBody {
  category: string
  input: string
  expected: string
  os?: string
  note?: string | null
}

/** Run the deterministic corpus + captured cases (offline, no AI cost). */
export async function runEvals(): Promise<EvalRunResult> {
  const { data } = await apiClient.get<EvalRunResult>("/api/dev/evals/run")
  return data
}

export async function listEvalCases(): Promise<EvalCase[]> {
  const { data } = await apiClient.get<EvalCase[]>("/api/dev/evals/cases")
  return data
}

export async function captureEvalCase(body: CaptureCaseBody): Promise<EvalCase> {
  const { data } = await apiClient.post<EvalCase>("/api/dev/evals/cases", body)
  return data
}

export async function deleteEvalCase(id: string): Promise<void> {
  await apiClient.delete(`/api/dev/evals/cases/${id}`)
}
