import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, ChevronRight } from "lucide-react"
import { getAllActiveRuns, type ActiveRunSummary } from "@/api/servers"
import RunLogModal from "@/components/playbooks/RunLogModal"

/** Compact "elapsed since" — e.g. 30s / 4m / 2h / 1d. */
function shortAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

/** Compact "what's running now" card for the dashboard right rail — every install
 * in progress across all servers, click-through to its live log. Auto-hides when
 * nothing is running (Update 17 Phase 3; compact rail layout Update 19 #3). */
export default function RunningTasks() {
  const [open, setOpen] = useState<ActiveRunSummary | null>(null)
  const { data: runs = [] } = useQuery({
    queryKey: ["active-runs-all"],
    queryFn: getAllActiveRuns,
    refetchInterval: 8000,
    refetchOnWindowFocus: true,
  })

  if (runs.length === 0) return null

  return (
    <>
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <Loader2 size={14} className="animate-spin text-primary" />
          <h2 className="text-sm font-semibold text-foreground">
            Running now <span className="text-muted-foreground">({runs.length})</span>
          </h2>
        </div>
        <div className="mt-3 max-h-64 space-y-0.5 overflow-y-auto">
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => setOpen(r)}
              title={`${r.title} on ${r.server_name}`}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent"
            >
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-primary" />
              <span className="min-w-0 flex-1 truncate text-foreground">
                {r.title} <span className="text-muted-foreground">· {r.server_name}</span>
              </span>
              {r.started_at && (
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {shortAgo(r.started_at)}
                </span>
              )}
              <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>
      </div>

      {open && (
        <RunLogModal
          serverId={open.server_id}
          runId={open.id}
          title={open.title}
          serverName={open.server_name}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  )
}
