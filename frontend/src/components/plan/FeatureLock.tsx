import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Lock, ArrowUpRight } from "lucide-react"
import { getMyEntitlements } from "@/api/usage"
import { Button } from "@/components/ui"

/**
 * Wraps a paid feature.
 *
 * Shows a lock naming the feature and the plan that includes it, INSTEAD of letting someone
 * fill in a form and get refused on submit. The allowed/not decision comes from the server
 * (`/api/usage/entitlements`), never from plan rules duplicated here — so a lock can never
 * disagree with the gate that actually refuses the request.
 */
export function useFeature(feature: string) {
  const { data } = useQuery({
    queryKey: ["entitlements"],
    queryFn: getMyEntitlements,
    staleTime: 5 * 60_000,
  })
  const entry = data?.features?.[feature]
  return {
    // Optimistic while loading: a brief flash of the real UI beats a flash of a false lock.
    allowed: entry?.allowed ?? true,
    label: entry?.label ?? feature,
    requiredPlan: entry?.required_plan ?? "Pro",
    planLabel: data?.plan_label,
    ready: !!data,
  }
}

export default function FeatureLock({ feature, children, compact = false }: {
  feature: string
  children: ReactNode
  compact?: boolean
}) {
  const { allowed, label, requiredPlan, planLabel } = useFeature(feature)
  if (allowed) return <>{children}</>

  const upgradeUrl = import.meta.env.VITE_UPGRADE_URL

  return (
    <div className={compact
      ? "flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-border px-3 py-2"
      : "rounded-xl border border-dashed border-border bg-muted/30 p-4"}>
      <span className="flex min-w-0 items-start gap-2">
        <Lock size={compact ? 13 : 15} className="mt-0.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0">
          <span className="block text-[13px] font-medium text-foreground">
            {label[0].toUpperCase() + label.slice(1)} is included in {requiredPlan}
          </span>
          {!compact && (
            <span className="mt-0.5 block text-[11.5px] text-muted-foreground">
              You’re on {planLabel ?? "Free"}. Anything you already set up keeps working —
              this only affects adding new ones.
            </span>
          )}
        </span>
      </span>
      {upgradeUrl && (
        <span className={compact ? "shrink-0" : "mt-3 flex"}>
          <Button size="sm" variant="outline" onClick={() => window.open(upgradeUrl, "_blank")}>
            Upgrade to {requiredPlan} <ArrowUpRight size={13} />
          </Button>
        </span>
      )}
    </div>
  )
}
