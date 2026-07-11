import { useMemo } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ScrollText } from "lucide-react"
import { listActivity } from "@/api/activity"
import type { ActivityItem, Server } from "@/types"
import { cn } from "@/lib/utils"

type Tone = "accent" | "danger" | "warning" | "success" | "neutral"

const TONE_CLS: Record<Tone, string> = {
  accent: "bg-primary/10 text-primary",
  danger: "bg-red-500/10 text-red-600 dark:text-red-400",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  neutral: "bg-muted text-muted-foreground",
}

/** The status tag for one activity row — same semantics as Logs.tsx's badges,
 *  plus a "High risk" overlay for approved-but-risky actions (mirrors the
 *  fleet report's severity language). */
function tagFor(a: ActivityItem): { label: string; tone: Tone } {
  switch (a.status) {
    case "blocked":
      return { label: "Blocked", tone: "danger" }
    case "pending_approval":
      return { label: "Needs OK", tone: "accent" }
    case "failed":
      return { label: "Failed", tone: "danger" }
    case "cancelled":
      return { label: "Cancelled", tone: "neutral" }
    case "running":
      return { label: "Running", tone: "accent" }
    case "partial":
      return { label: "Partial", tone: "warning" }
  }
  if (a.risk_level === "high") return { label: "High risk", tone: "neutral" }
  return { label: "Success", tone: "success" }
}

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/** Compact top-5 activity feed for the Dashboard — the same unified commands +
 *  playbook-runs feed as the Logs page, condensed with status tags. */
export default function RecentActivity({ servers }: { servers: Server[] }) {
  const { data: activity = [], isLoading } = useQuery<ActivityItem[]>({
    queryKey: ["activity"],
    queryFn: () => listActivity(5),
  })

  const serverName = useMemo(() => {
    const map = new Map(servers.map((s) => [s.id, s.name]))
    return (id: string | null) => (id ? map.get(id) ?? "Unknown server" : null)
  }, [servers])

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2.5 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Recent activity</h2>
        <Link to="/logs" className="text-xs text-muted-foreground hover:text-foreground">
          View all
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-9 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
      ) : activity.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <ScrollText size={22} className="mb-2 text-muted-foreground/50" />
          <p className="text-xs text-muted-foreground">No activity yet.</p>
        </div>
      ) : (
        <div>
          {activity.map((a, i) => {
            const tag = tagFor(a)
            const name = serverName(a.server_id)
            return (
              <Link
                key={`${a.kind}-${a.id}`}
                to={a.server_id ? `/servers/${a.server_id}` : "/logs"}
                className={cn(
                  "-mx-1 flex items-center gap-2.5 rounded-md px-1 py-2 transition-colors hover:bg-muted/60",
                  i !== activity.length - 1 && "border-b border-border",
                )}
              >
                <span
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide",
                    TONE_CLS[tag.tone],
                  )}
                >
                  {tag.label}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-foreground">{a.title}</p>
                  {name && <p className="truncate text-[11px] text-muted-foreground">{name}</p>}
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(a.created_at)}</span>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
