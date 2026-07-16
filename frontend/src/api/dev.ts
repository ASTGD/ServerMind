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

// ── Operator console (docs/SAAS-LAUNCH-PLAN.md §5) ───────────────────────────
// Support/ops only. WHMCS owns customers, orders and revenue; `plan` here is a
// read-only mirror of WHMCS's decision and is never edited from this surface.

export interface AdminOverview {
  period_start: string
  users_total: number
  users_by_plan: Record<string, number>
  users_new_this_period: number
  users_active_7d: number
  servers_total: number
  ai_cost_usd: number
  ai_actions: number
  ai_calls: number
  ai_errors: number
}

export interface AdminUser {
  id: string
  email: string
  name: string | null
  plan: string
  is_admin: boolean
  is_active: boolean
  is_verified: boolean
  created_at: string | null
  actions_used: number
  actions_limit: number
  servers_used: number
  servers_limit: number
  ai_cost_usd: number
}

export interface EntitlementEvent {
  created_at: string | null
  action: string
  email: string | null
  plan: string | null
  reference: string | null
  created: boolean | null
  forced: boolean | null
  ip: string | null
}

export interface AdminUserDetail extends AdminUser {
  totp_enabled: boolean
  preferred_language: string
  ally_mode: string
  servers: {
    id: string
    name: string
    host: string
    connection_type: string
    os_type: string | null
    status: string
    last_seen: string | null
  }[]
  missions: {
    id: string
    goal: string
    server_name: string | null
    status: string
    verified: boolean | null
    created_at: string | null
  }[]
  problems: {
    created_at: string | null
    status: string
    risk_level: string | null
    request: string
  }[]
  entitlements: EntitlementEvent[]
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const { data } = await apiClient.get<AdminOverview>("/api/dev/admin/overview")
  return data
}

export async function getAdminUsers(q?: string): Promise<AdminUser[]> {
  const { data } = await apiClient.get<AdminUser[]>("/api/dev/admin/users", { params: { q } })
  return data
}

export async function getAdminUser(id: string): Promise<AdminUserDetail> {
  const { data } = await apiClient.get<AdminUserDetail>(`/api/dev/admin/users/${id}`)
  return data
}

/** "Did billing land?" — every plan change WHMCS drove. */
export async function getEntitlementLog(): Promise<EntitlementEvent[]> {
  const { data } = await apiClient.get<EntitlementEvent[]>("/api/dev/admin/entitlements")
  return data
}
