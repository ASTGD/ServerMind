import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Terminal, PlayCircle, Search, ScrollText } from "lucide-react"
import { listActivity } from "@/api/activity"
import { listServers } from "@/api/servers"
import type { ActivityItem, Server } from "@/types"
import { failureRemedy } from "@/lib/preflightRemedy"
import { cn } from "@/lib/utils"

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS: Record<string, { label: string; cls: string }> = {
  success: { label: "Success", cls: "bg-green-500/10 text-green-600 border-green-500/20" },
  failed: { label: "Failed", cls: "bg-red-500/10 text-red-600 border-red-500/20" },
  partial: { label: "Partial", cls: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
  blocked: { label: "Blocked", cls: "bg-red-500/10 text-red-600 border-red-500/20" },
  cancelled: { label: "Cancelled", cls: "bg-muted text-muted-foreground border-border" },
  running: { label: "Running", cls: "bg-blue-500/10 text-blue-600 border-blue-500/20" },
  pending_approval: { label: "Pending", cls: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
}

function StatusBadge({ status }: { status: string | null }) {
  const s = STATUS[status ?? ""] ?? { label: status ?? "—", cls: "bg-muted text-muted-foreground border-border" }
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", s.cls)}>
      {s.label}
    </span>
  )
}

function fmtDuration(ms: number | null): string | null {
  if (ms == null) return null
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s % 60)}s`
}

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

type KindFilter = "all" | "playbook" | "command"

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Logs() {
  const [kind, setKind] = useState<KindFilter>("all")
  const [q, setQ] = useState("")

  const { data: activity = [], isLoading } = useQuery<ActivityItem[]>({
    queryKey: ["activity"],
    queryFn: () => listActivity(100),
  })
  const { data: servers = [] } = useQuery<Server[]>({
    queryKey: ["servers"],
    queryFn: listServers,
  })

  const serverName = useMemo(() => {
    const map = new Map(servers.map((s) => [s.id, s.name]))
    return (id: string | null) => (id ? map.get(id) ?? "Unknown server" : "—")
  }, [servers])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return activity.filter((a) => {
      if (kind !== "all" && a.kind !== kind) return false
      if (!needle) return true
      return (
        a.title.toLowerCase().includes(needle) ||
        serverName(a.server_id).toLowerCase().includes(needle)
      )
    })
  }, [activity, kind, q, serverName])

  const tabs: { key: KindFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "playbook", label: "Playbooks" },
    { key: "command", label: "AI Commands" },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Activity Log</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Playbook runs and AI commands across your servers.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setKind(t.key)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                kind === t.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search activity…"
            className="w-64 rounded-lg border border-border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg border border-border bg-card" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20 text-center">
          <ScrollText size={34} className="mb-4 text-muted-foreground/50" />
          <p className="font-medium text-foreground">
            {activity.length === 0 ? "No activity yet" : "No matching activity"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {activity.length === 0
              ? "Run a playbook or chat with a server to see it logged here."
              : "Try a different filter or search term."}
          </p>
          {activity.length === 0 && (
            <Link
              to="/playbooks"
              className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Browse playbooks
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((a) => {
            const Icon = a.kind === "command" ? Terminal : PlayCircle
            const dur = fmtDuration(a.duration_ms)
            return (
              <div
                key={`${a.kind}-${a.id}`}
                className="flex items-center gap-3 rounded-lg border border-border bg-card p-4"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <Icon size={16} />
                </span>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{a.title}</p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                    <span>{a.kind === "command" ? "AI command" : "Playbook"}</span>
                    <span>·</span>
                    <Link
                      to={a.server_id ? `/servers/${a.server_id}` : "#"}
                      className="hover:text-foreground hover:underline"
                    >
                      {serverName(a.server_id)}
                    </Link>
                    {dur && (
                      <>
                        <span>·</span>
                        <span className="tabular-nums">{dur}</span>
                      </>
                    )}
                    {a.risk_level && a.risk_level !== "low" && (
                      <>
                        <span>·</span>
                        <span className="capitalize">{a.risk_level} risk</span>
                      </>
                    )}
                  </div>
                  {a.failure_reason && (
                    <p className="mt-1 text-xs leading-snug text-red-500/90">{a.failure_reason}</p>
                  )}
                  {failureRemedy(a.failure_reason) && (
                    <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
                      <span className="font-medium text-foreground">What to do:</span> {failureRemedy(a.failure_reason)}
                    </p>
                  )}
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1">
                  <StatusBadge status={a.status} />
                  <span className="text-xs text-muted-foreground">{timeAgo(a.created_at)}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
