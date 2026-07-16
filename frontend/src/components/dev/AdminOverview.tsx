import { useQuery } from "@tanstack/react-query"
import { Users, Server as ServerIcon, Zap, AlertTriangle } from "lucide-react"
import { getAdminOverview } from "@/api/dev"

function Tile({
  icon: Icon, label, value, sub, tone = "default",
}: {
  icon: typeof Users
  label: string
  value: string | number
  sub?: string
  tone?: "default" | "amber" | "red"
}) {
  const valueTone =
    tone === "red" ? "text-red-600 dark:text-red-400"
      : tone === "amber" ? "text-amber-600 dark:text-amber-400"
        : "text-foreground"
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Icon size={14} />
        <span className="text-xs">{label}</span>
      </div>
      <p className={`mt-1.5 text-[22px] font-semibold tabular-nums ${valueTone}`}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

/** Overview — the business at a glance.
 *
 *  Deliberately reports COST, not revenue or margin: revenue is WHMCS's fact and cost is
 *  ours, and syncing invoices here just to show one number would create a second source
 *  of truth for money (SAAS-LAUNCH-PLAN §5.1). WHMCS stays the authority for revenue.
 */
export default function AdminOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: getAdminOverview,
    refetchInterval: 60_000,
  })

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-[74px] animate-pulse rounded-lg border border-border bg-card" />
        ))}
      </div>
    )
  }

  const pro = data.users_by_plan.pro ?? 0
  const free = data.users_by_plan.free ?? 0
  const perAction = data.ai_actions > 0 ? data.ai_cost_usd / data.ai_actions : 0
  // The $0.05/action assumption underwrites the whole margin case (PRICING §9) — if the
  // real number drifts above it, the plan's economics are wrong and we want to see it here.
  const perActionTone = perAction > 0.05 ? "red" : perAction > 0.04 ? "amber" : "default"

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile icon={Users} label="Users" value={data.users_total} sub={`+${data.users_new_this_period} this month`} />
        <Tile icon={Users} label="Pro / Free" value={`${pro} / ${free}`} sub="plan mirrors WHMCS" />
        <Tile icon={Zap} label="Active (7d)" value={data.users_active_7d} sub="used Ally" />
        <Tile icon={ServerIcon} label="Servers" value={data.servers_total} sub="under management" />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile icon={Zap} label="AI cost (month)" value={`$${data.ai_cost_usd.toFixed(2)}`} sub="our real COGS" />
        <Tile icon={Zap} label="Actions" value={data.ai_actions} sub={`${data.ai_calls} model calls`} />
        <Tile
          icon={Zap}
          label="Cost / action"
          value={`$${perAction.toFixed(3)}`}
          sub="target ≤ $0.05"
          tone={perActionTone}
        />
        <Tile
          icon={AlertTriangle}
          label="Provider errors"
          value={data.ai_errors}
          tone={data.ai_errors > 0 ? "amber" : "default"}
          sub="this month"
        />
      </div>

      <p className="text-xs text-muted-foreground">
        Revenue, invoices and orders live in WHMCS — this shows what ServerAlly knows and
        WHMCS cannot: servers, Ally usage, and what the AI actually costs us. Period
        started {new Date(data.period_start).toLocaleDateString()}.
      </p>
    </div>
  )
}
