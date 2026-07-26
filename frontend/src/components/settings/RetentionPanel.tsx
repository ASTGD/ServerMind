import { useQuery } from "@tanstack/react-query"
import { Archive, Infinity as InfinityIcon, ArrowUpRight } from "lucide-react"
import { getMyRetention } from "@/api/usage"
import { Button } from "@/components/ui"

function months(days: number): string {
  if (days >= 365) return days === 365 ? "1 year" : `${Math.round(days / 365)} years`
  if (days >= 60) return `${Math.round(days / 30)} months`
  if (days >= 28) return "1 month"
  return `${days} days`
}

/**
 * How long history is kept.
 *
 * The card adapts to whether plan limits are actually switched on, because they are not today:
 * telling a Free account "Pro keeps a year" while they already keep a year would be an upsell
 * built on something untrue.
 */
export default function RetentionPanel() {
  const { data } = useQuery({ queryKey: ["retention"], queryFn: getMyRetention })
  if (!data) return null

  const isPro = data.plan === "pro"
  const upgradeUrl = import.meta.env.VITE_UPGRADE_URL

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Archive size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">How long history is kept</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        {data.enforced
          ? "Charts and check history are trimmed after a while — storing them is the real cost behind this."
          : "Plan limits aren’t switched on yet, so you’re keeping the longest history we offer."}
      </p>

      <ul className="space-y-1.5">
        {data.kinds.map((k) => (
          <li key={k.kind} className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[13px] text-foreground">{k.label}</span>
            <span className="flex items-baseline gap-2">
              <span className="text-[13px] font-semibold">{months(k.days)}</span>
              {/* Only worth showing when the two actually differ for this account. */}
              {data.enforced && !isPro && k.pro_days > k.days && (
                <span className="text-[11px] text-muted-foreground">
                  Pro: {months(k.pro_days)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>

      {/* The reassurance that matters more than the numbers: retention never touches a record
          anyone reports on. */}
      <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2">
        <p className="flex items-start gap-1.5 text-[11.5px] text-muted-foreground">
          <InfinityIcon size={12} className="mt-0.5 shrink-0" />
          <span>
            <span className="font-medium text-foreground">Kept for as long as you have an
            account:</span> everything Ally did, your missions and their reports, security and
            malware scans, backup records, and what installed what. Only the minute-by-minute
            charts get trimmed.
          </span>
        </p>
      </div>

      {data.enforced && !isPro && upgradeUrl && (
        <div className="mt-3 flex justify-end">
          <Button size="sm" variant="outline" onClick={() => window.open(upgradeUrl, "_blank")}>
            Keep a year of history <ArrowUpRight size={13} />
          </Button>
        </div>
      )}
    </div>
  )
}
