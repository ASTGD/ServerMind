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

// ── Observability (Phase 4) ───────────────────────────────────────────────────

export interface ActivityCall {
  created_at: string | null
  feature: string
  model: string
  skill: string | null
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cost_usd: number
  actions: number
  status: string
  user: string | null
  server: string | null
}

export interface ActivityData {
  period_start: string
  summary: { cost_usd: number; actions: number; calls: number }
  by_feature: { feature: string; cost_usd: number; calls: number }[]
  daily: { day: string; cost_usd: number; calls: number }[]
  recent: ActivityCall[]
}

/** Recent AI calls (the ledger) + this period's cost/actions summary. */
export async function getActivity(): Promise<ActivityData> {
  const { data } = await apiClient.get<ActivityData>("/api/dev/activity")
  return data
}

// ── Provider cost A/B (Claude vs OpenAI, re-priced over real ledger usage) ─────

export type OaTier = "top" | "mid" | "small"

export interface AbFeature {
  feature: string
  claude_usd: number
  openai_usd: number
  in: number
  out: number
  cache_read: number
  cache_write: number
  calls: number
}

export interface ProviderAb {
  period_start: string
  tiers: Record<OaTier, { label: string; in: number; out: number }>
  caveats: string[]
  totals: {
    claude_usd: number
    openai_usd: number
    in: number
    out: number
    cache_read: number
    cache_write: number
    cache_hit_pct: number
    delta_pct: number | null
  }
  by_feature: AbFeature[]
  model_tiers: Record<string, OaTier>
}

/** Re-price this period's real token usage on Claude vs OpenAI. Pass optional per-tier
 * OpenAI price overrides to plug in a real quote. No live calls — pure arithmetic. */
export async function getProviderAb(
  openai?: Partial<Record<OaTier, { in: number; out: number }>>,
): Promise<ProviderAb> {
  const { data } = await apiClient.post<ProviderAb>("/api/dev/provider-ab", { openai })
  return data
}
