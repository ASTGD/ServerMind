import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ArrowUpRight, ExternalLink, CalendarClock } from "lucide-react"
import { format } from "date-fns"
import { getMyUsage } from "@/api/usage"
import UpgradeModal from "@/components/layout/UpgradeModal"
import { Card, Badge, Button, buttonVariants } from "@/components/ui"
import { cn } from "@/lib/utils"

/** One usage meter — label, used/limit, and a fill bar (amber when nearly full). */
function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100))
  const nearLimit = pct >= 90
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums font-medium text-foreground">
          {used} <span className="font-normal text-muted-foreground">of {limit}</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            nearLimit ? "bg-warning" : "bg-brand-gradient-r",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/**
 * The customer's plan at a glance: plan badge, both usage meters (Ally actions +
 * servers), the allowance reset date, and the upgrade / manage-billing action.
 * Real invoices and payment live in WHMCS — this card only summarizes and links out.
 */
export default function SubscriptionCard() {
  const [showUpgrade, setShowUpgrade] = useState(false)
  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: getMyUsage, staleTime: 60_000 })
  const manageUrl = import.meta.env.VITE_UPGRADE_URL as string | undefined

  if (!usage) {
    return (
      <Card className="p-5">
        <div className="h-4 w-28 animate-pulse rounded bg-muted" />
        <div className="mt-4 space-y-3">
          <div className="h-8 animate-pulse rounded bg-muted" />
          <div className="h-8 animate-pulse rounded bg-muted" />
        </div>
      </Card>
    )
  }

  const isPro = usage.plan.toLowerCase() === "pro"

  return (
    <Card className="flex flex-col p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Subscription</h2>
        <Badge variant={isPro ? "brand" : "outline"}>{isPro ? "Pro" : "Free"} plan</Badge>
      </div>

      <div className="space-y-4">
        <Meter label="Ally actions this month" used={usage.used} limit={usage.limit} />
        <Meter label="Servers" used={usage.servers_used} limit={usage.servers_limit} />
      </div>

      <p className="mt-3.5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <CalendarClock size={13} className="shrink-0" />
        Actions reset {format(new Date(usage.resets_at), "MMM d, yyyy")}
      </p>

      <div className="mt-auto pt-4">
        {isPro ? (
          manageUrl && (
            <a
              href={manageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "w-full")}
            >
              <ExternalLink size={14} /> Manage billing
            </a>
          )
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowUpgrade(true)}
            className="w-full border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
          >
            <ArrowUpRight size={14} /> Upgrade to Pro
          </Button>
        )}
      </div>

      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} />}
    </Card>
  )
}
