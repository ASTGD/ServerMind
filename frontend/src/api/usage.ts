import { apiClient } from "./client"

/** This month's Ally-action usage for the signed-in user. */
export interface MyUsage {
  plan: string
  used: number
  limit: number
  /** ISO date the allowance resets (first of next month for now). */
  resets_at: string
  /** Whether the plan limits actually block (cloud) or usage is informational (self-hosted/dev). */
  enforced: boolean
  /** Meter #2 ("open features, two meters"): servers owned vs the plan's cap. */
  servers_used: number
  servers_limit: number
}

export async function getMyUsage(): Promise<MyUsage> {
  const res = await apiClient.get<MyUsage>("/api/usage/me")
  return res.data
}

export interface RetentionKind {
  kind: string
  label: string
  /** What THIS account keeps today. */
  days: number
  free_days: number
  pro_days: number
}

export interface MyRetention {
  /** False while plan limits are dormant — in which case everyone keeps the long window. */
  enforced: boolean
  plan: string
  kinds: RetentionKind[]
  /** Tables retention never touches: reports, forensics, audit trail, billing. */
  kept_forever: string[]
}

export async function getMyRetention(): Promise<MyRetention> {
  const res = await apiClient.get<MyRetention>("/api/usage/retention")
  return res.data
}

export interface FeatureEntitlement {
  allowed: boolean
  label: string
  /** The cheapest plan that includes it — used in the lock text. */
  required_plan: string
}

export interface MyEntitlements {
  plan: string
  plan_label: string
  /** False while plan limits are dormant — every feature reads as allowed. */
  enforced: boolean
  limits: {
    servers: number
    actions: number
    runbooks: number
    status_pages: number
    team_members: number
  }
  features: Record<string, FeatureEntitlement>
  never_gated: string[]
}

export async function getMyEntitlements(): Promise<MyEntitlements> {
  const res = await apiClient.get<MyEntitlements>("/api/usage/entitlements")
  return res.data
}
